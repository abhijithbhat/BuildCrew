import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
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

  static const String apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const String localLanUrl = String.fromEnvironment('LOCAL_LAN_URL');

  /// Validates API configuration at startup.
  /// In release mode, throws [StateError] if [API_BASE_URL] is empty or does not start with https://.
  static void validateStartupConfig() {
    if (kReleaseMode) {
      if (apiBaseUrl.isEmpty || !apiBaseUrl.startsWith('https://')) {
        throw StateError(
          'API_BASE_URL dart-define must be provided and start with https:// in release mode.',
        );
      }
    }
  }

  static ApiClient? _instance;
  static ApiClient get instance => _instance ??= ApiClient();

  final Dio dio;
  final Dio _retryDio;
  final Dio? refreshDio;
  final StorageService _storageService;
  final SupabaseClient? supabaseClient;

  SupabaseClient? get _supabase {
    if (supabaseClient != null) return supabaseClient;
    try {
      return Supabase.instance.client;
    } catch (_) {
      return null;
    }
  }

  Future<String?>? _refreshFuture;

  ApiClient({
    Dio? dio,
    this.refreshDio,
    Dio? retryDio,
    StorageService? storageService,
    this.supabaseClient,
  })  : _storageService = storageService ?? StorageService(),
        dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 8),
                receiveTimeout: const Duration(seconds: 20),
                sendTimeout: const Duration(seconds: 20),
                headers: {'Content-Type': 'application/json'},
              ),
            ),
        _retryDio = retryDio ??
            (dio != null
                ? (Dio(dio.options)..httpClientAdapter = dio.httpClientAdapter)
                : Dio(
                    BaseOptions(
                      connectTimeout: const Duration(seconds: 8),
                      receiveTimeout: const Duration(seconds: 20),
                      sendTimeout: const Duration(seconds: 20),
                      headers: {'Content-Type': 'application/json'},
                    ),
                  )) {
    validateStartupConfig();
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

  /// Base URLs with multi-endpoint fallback.
  /// In release mode (kReleaseMode), ONLY [apiBaseUrl] is used (throws [StateError] if invalid).
  /// In debug mode, uses local endpoints with optional [localLanUrl] dart-define.
  static List<String> get fallbackBaseUrls {
    if (kReleaseMode) {
      if (apiBaseUrl.isEmpty || !apiBaseUrl.startsWith('https://')) {
        throw StateError(
          'API_BASE_URL dart-define must be provided and start with https:// in release mode.',
        );
      }
      return [apiBaseUrl];
    }

    final urls = <String>[];
    if (apiBaseUrl.isNotEmpty) {
      urls.add(apiBaseUrl);
    }

    if (kIsWeb) {
      urls.addAll(['http://localhost:8000', 'http://127.0.0.1:8000']);
      return urls;
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
      urls.add('http://127.0.0.1:8000');
      if (localLanUrl.isNotEmpty) {
        urls.add(localLanUrl);
      }
      urls.add('http://10.0.2.2:8000');
      return urls;
    }

    if (localLanUrl.isNotEmpty) {
      urls.add(localLanUrl);
    }
    urls.addAll(['http://localhost:8000', 'http://127.0.0.1:8000']);
    return urls;
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

  /// Executes token refresh:
  /// - For OAuth users (Supabase currentSession != null): refreshes session via
  ///   Supabase.instance.client.auth.refreshSession() and persists returned tokens.
  /// - For email/password users: calls POST /auth/refresh on the backend.
  Future<String?> _executeTokenRefresh() async {
    // 1. Supabase OAuth refresh branch
    final client = _supabase;
    Session? currentOAuthSession;
    try {
      currentOAuthSession = client?.auth.currentSession;
    } catch (_) {
      currentOAuthSession = null;
    }

    if (currentOAuthSession != null && client != null) {
      debugPrint('ApiClient: Refreshing OAuth session via Supabase auth...');
      final authResponse = await client.auth.refreshSession();
      final newSession = authResponse.session;
      if (newSession != null && newSession.accessToken.isNotEmpty) {
        final newAccessToken = newSession.accessToken;
        final newRefreshToken = newSession.refreshToken ?? '';
        await _storageService.saveTokens(
          accessToken: newAccessToken,
          refreshToken: newRefreshToken,
        );
        debugPrint('ApiClient: Successfully refreshed Supabase OAuth session.');
        return newAccessToken;
      }
      throw Exception('Failed to refresh Supabase OAuth session: empty session');
    }

    // 2. Email/password users: backend POST /auth/refresh
    final storedRefreshToken = await _storageService.getRefreshToken();
    if (storedRefreshToken == null || storedRefreshToken.trim().isEmpty) {
      throw const AuthException('No refresh token stored', statusCode: '401');
    }

    // Use isolated Dio instance to prevent interceptor recursion
    final targetDio = refreshDio ??
        Dio(
          BaseOptions(
            connectTimeout: const Duration(seconds: 8),
            receiveTimeout: const Duration(seconds: 20),
            sendTimeout: const Duration(seconds: 20),
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
            e.type == DioExceptionType.sendTimeout ||
            (e.message != null &&
                (e.message!.contains('Connection refused') ||
                    e.message!.contains('No route to host') ||
                    e.message!.contains('SocketException')));
        final is5xx = e.response?.statusCode != null &&
            e.response!.statusCode! >= 500 &&
            e.response!.statusCode! < 600;
        if (isConnError || is5xx) {
          debugPrint('ApiClient: Connection/Server error on $baseUrl. Trying next fallback...');
          continue;
        }
        // Non-connection error (e.g. 401 INVALID_REFRESH_TOKEN) -> rethrow immediately
        rethrow;
      }
    }
    throw lastException ?? Exception('Failed to connect to backend for token refresh');
  }

  /// Determines if a token refresh error represents an authoritative session termination:
  /// - HTTP 400, 401, or 403 from POST /auth/refresh
  /// - Supabase AuthException indicating invalid/expired refresh token (and NOT AuthRetryableFetchException)
  /// - Missing stored refresh token
  /// Returns false for connection errors, timeouts, 5xx server errors, or Supabase AuthRetryableFetchException.
  bool isAuthoritativeRefreshFailure(dynamic error) {
    if (error == null) return false;

    // 1. Missing stored refresh token
    if (error is AuthException && error.message.toLowerCase().contains('no refresh token')) {
      return true;
    }
    final errorStr = error.toString().toLowerCase();
    if (errorStr.contains('no refresh token stored') ||
        errorStr.contains('no refresh token available')) {
      return true;
    }

    // 2. Supabase AuthRetryableFetchException is explicitly retryable / non-authoritative
    if (error is AuthRetryableFetchException) {
      return false;
    }

    // 3. Network or Timeout errors are non-authoritative
    if (error is TimeoutException) {
      return false;
    }
    if (errorStr.contains('connection refused') ||
        errorStr.contains('socketexception') ||
        errorStr.contains('failed host lookup') ||
        errorStr.contains('network is unreachable') ||
        errorStr.contains('connection timeout') ||
        errorStr.contains('receive timeout') ||
        errorStr.contains('send timeout') ||
        errorStr.contains('handshakeexception') ||
        errorStr.contains('timed out')) {
      return false;
    }

    // 4. DioException checks
    if (error is DioException) {
      final type = error.type;
      if (type == DioExceptionType.connectionError ||
          type == DioExceptionType.connectionTimeout ||
          type == DioExceptionType.receiveTimeout ||
          type == DioExceptionType.sendTimeout) {
        return false;
      }
      final status = error.response?.statusCode;
      if (status != null) {
        if (status >= 500 && status < 600) {
          return false;
        }
        if (status == 400 || status == 401 || status == 403) {
          return true;
        }
      }
      return false;
    }

    // 5. Supabase AuthException
    if (error is AuthException) {
      final statusStr = error.statusCode;
      if (statusStr != null) {
        final code = int.tryParse(statusStr);
        if (code != null && code >= 500 && code < 600) {
          return false;
        }
        if (code == 400 || code == 401 || code == 403) {
          return true;
        }
      }
      final msg = error.message.toLowerCase();
      if (msg.contains('invalid') ||
          msg.contains('expired') ||
          msg.contains('revoked') ||
          msg.contains('grant') ||
          msg.contains('not found') ||
          msg.contains('empty session') ||
          msg.contains('unauthorized')) {
        return true;
      }
      // Any other non-retryable AuthException from refreshSession is authoritative
      return true;
    }

    return false;
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
      if (_client.isAuthoritativeRefreshFailure(refreshErr)) {
        debugPrint('ApiClient: Token refresh failed authoritatively ($refreshErr). Forcing global logout.');
        await _client.handleForceLogout();
      } else {
        debugPrint('ApiClient: Token refresh failed with non-authoritative / network error ($refreshErr). Keeping tokens, skipping logout.');
      }
      return handler.next(err);
    }
  }
}
