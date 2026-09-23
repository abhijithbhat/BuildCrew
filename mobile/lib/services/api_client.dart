import 'dart:async';
import 'dart:io' show Platform;
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'storage_service.dart';

/// Central API Client providing a shared Dio instance with automatic silent
/// token refresh via [QueuedInterceptor].
class ApiClient {
  /// Global navigator key to allow background interceptor to navigate on force-logout.
  static final GlobalKey<NavigatorState> navigatorKey =
      GlobalKey<NavigatorState>();

  /// Global scaffold messenger key to display snackbars across the app.
  static final GlobalKey<ScaffoldMessengerState> scaffoldMessengerKey =
      GlobalKey<ScaffoldMessengerState>();

  /// Global stream broadcasting force-logout events (e.g. when refresh token expires).
  static final StreamController<void> onForceLogout =
      StreamController<void>.broadcast();

  static ApiClient? _instance;
  static ApiClient get instance => _instance ??= ApiClient();

  final Dio dio;
  final Dio _retryDio;
  final Dio? refreshDio;
  final StorageService _storageService;

  Future<String?>? _refreshFuture;

  ApiClient({
    Dio? dio,
    this.refreshDio,
    Dio? retryDio,
    StorageService? storageService,
  })  : _storageService = storageService ?? StorageService(),
        dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 10),
                headers: {'Content-Type': 'application/json'},
              ),
            ),
        _retryDio = retryDio ??
            (dio != null
                ? (Dio(dio.options)..httpClientAdapter = dio.httpClientAdapter)
                : Dio(
                    BaseOptions(
                      connectTimeout: const Duration(seconds: 10),
                      receiveTimeout: const Duration(seconds: 10),
                      headers: {'Content-Type': 'application/json'},
                    ),
                  )) {
    this.dio.interceptors.add(_AuthRefreshInterceptor(this));
  }

  static String? _activeBaseUrl;

  /// Override or reset instance for unit testing.
  @visibleForTesting
  static void setInstance(ApiClient? client) {
    _instance = client;
    _activeBaseUrl = null;
  }

  /// Current active base URL or last successful fallback URL.
  static String get activeBaseUrl {
    if (_activeBaseUrl != null && _activeBaseUrl!.trim().isNotEmpty) {
      return _activeBaseUrl!.trim();
    }
    if (_instance != null && _instance!.dio.options.baseUrl.trim().isNotEmpty) {
      return _instance!.dio.options.baseUrl.trim();
    }
    return fallbackBaseUrls.first;
  }

  static set activeBaseUrl(String url) {
    if (url.trim().isNotEmpty) {
      _activeBaseUrl = url.trim();
      if (_instance != null) {
        _instance!.dio.options.baseUrl = url.trim();
      }
    }
  }

  /// Base URLs with multi-endpoint fallback across ADB USB, Wi-Fi, and Emulator.
  static List<String> get fallbackBaseUrls {
    if (kIsWeb) return ['http://localhost:8000', 'http://127.0.0.1:8000'];
    if (Platform.isAndroid) {
      return [
        'http://127.0.0.1:8000',
        'http://192.168.0.112:8000',
        'http://10.0.2.2:8000',
      ];
    }
    return ['http://localhost:8000', 'http://127.0.0.1:8000'];
  }

  /// Refresh token with concurrency management:
  /// If a refresh is already in flight, awaits that same in-flight refresh.
  Future<String?> refreshToken() async {
    if (_refreshFuture != null) {
      return await _refreshFuture;
    }

    _refreshFuture = _executeTokenRefresh();
    try {
      final newToken = await _refreshFuture;
      return newToken;
    } finally {
      _refreshFuture = null;
    }
  }

  /// Executes the actual POST /auth/refresh call using an unintercepted Dio instance.
  Future<String?> _executeTokenRefresh() async {
    final storedRefreshToken = await _storageService.getRefreshToken();
    if (storedRefreshToken == null || storedRefreshToken.trim().isEmpty) {
      throw Exception('No refresh token stored');
    }

    // Use isolated Dio instance to prevent interceptor recursion
    final targetDio = refreshDio ??
        Dio(
          BaseOptions(
            connectTimeout: const Duration(seconds: 10),
            receiveTimeout: const Duration(seconds: 10),
            headers: {'Content-Type': 'application/json'},
          ),
        );

    final customRefreshDio = refreshDio;
    final urls = (customRefreshDio != null && customRefreshDio.options.baseUrl.isNotEmpty)
        ? [customRefreshDio.options.baseUrl]
        : fallbackBaseUrls;

    DioException? lastException;
    for (final baseUrl in urls) {
      try {
        targetDio.options.baseUrl = baseUrl;
        debugPrint('ApiClient: Attempting token refresh via $baseUrl/auth/refresh');
        final response = await targetDio.post(
          '/auth/refresh',
          data: {'refresh_token': storedRefreshToken.trim()},
        );

        if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
          activeBaseUrl = baseUrl;
          final data = response.data as Map<String, dynamic>;
          final newAccessToken = data['access_token']?.toString();
          final newRefreshToken = data['refresh_token']?.toString();

          if (newAccessToken != null && newAccessToken.isNotEmpty) {
            // Save both new tokens together to flutter_secure_storage
            await _storageService.saveTokens(
              accessToken: newAccessToken,
              refreshToken: newRefreshToken ?? storedRefreshToken,
            );
            debugPrint('ApiClient: Successfully refreshed session in background.');
            return newAccessToken;
          }
        }
        throw Exception('Invalid token refresh response from backend');
      } on DioException catch (e) {
        lastException = e;
        final isConnError = e.type == DioExceptionType.connectionError ||
            e.type == DioExceptionType.connectionTimeout ||
            e.type == DioExceptionType.receiveTimeout ||
            (e.message != null &&
                (e.message!.contains('Connection refused') ||
                    e.message!.contains('No route to host') ||
                    e.message!.contains('SocketException')));
        if (isConnError) {
          debugPrint('ApiClient: Connection error on $baseUrl. Trying next fallback...');
          continue;
        }
        // Non-connection error (e.g. 401 INVALID_REFRESH_TOKEN) -> rethrow immediately
        rethrow;
      }
    }
    throw lastException ?? Exception('Failed to connect to backend for token refresh');
  }

  /// Clears stored tokens, broadcasts global logout event, and routes to /login.
  Future<void> handleForceLogout() async {
    try {
      await _storageService.clearTokens();
    } catch (_) {}
    onForceLogout.add(null);
    navigatorKey.currentState?.pushNamedAndRemoveUntil(
      '/login',
      (route) => false,
    );
  }
}

/// QueuedInterceptor that catches 401 Unauthorized responses, refreshes the JWT
/// in the background, and seamlessly retries the original request.
class _AuthRefreshInterceptor extends QueuedInterceptor {
  final ApiClient _client;

  _AuthRefreshInterceptor(this._client);

  @override
  void onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    // Only intercept 401 Unauthorized
    if (err.response?.statusCode != 401) {
      return handler.next(err);
    }

    final path = err.requestOptions.path;
    // Exclude the refresh call itself and auth public routes to avoid infinite loop
    if (path.contains('/auth/refresh') ||
        path.contains('/auth/login') ||
        path.contains('/auth/signup') ||
        path.contains('/auth/verify-otp') ||
        path.contains('/auth/forgot-password') ||
        path.contains('/auth/reset-password')) {
      return handler.next(err);
    }

    // If this request was already a retry attempt, do not loop again
    if (err.requestOptions.extra['is_retry'] == true) {
      await _client.handleForceLogout();
      return handler.next(err);
    }

    try {
      // Check if a preceding queued request already refreshed the token
      final currentToken = await _client._storageService.getAccessToken();
      final requestToken = (err.requestOptions.headers['Authorization'] as String?)
          ?.replaceFirst('Bearer ', '')
          .trim();

      String? newAccessToken;
      if (currentToken != null &&
          currentToken.isNotEmpty &&
          requestToken != null &&
          requestToken.isNotEmpty &&
          currentToken != requestToken) {
        // Token was already refreshed by a prior request in the queue!
        newAccessToken = currentToken;
      } else {
        // Perform refresh or await in-flight refresh
        newAccessToken = await _client.refreshToken();
      }

      if (newAccessToken == null || newAccessToken.isEmpty) {
        throw Exception('Failed to obtain new access token');
      }

      // Clone original request options and attach fresh token
      final requestOptions = err.requestOptions;
      requestOptions.headers['Authorization'] = 'Bearer $newAccessToken';
      requestOptions.extra['is_retry'] = true;

      // Retry original request with the new access token using _retryDio to prevent deadlock
      final response = await _client._retryDio.fetch(requestOptions);
      return handler.resolve(response);
    } catch (refreshErr) {
      debugPrint('ApiClient: Token refresh failed ($refreshErr). Forcing global logout.');
      await _client.handleForceLogout();
      return handler.next(err);
    }
  }
}
