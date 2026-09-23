import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'api_client.dart';
import 'storage_service.dart';

class AuthService {
  final Dio _dio;
  final StorageService _storageService;
  final SupabaseClient? supabaseClient;
  static StreamSubscription<AuthState>? _staticAuthSubscription;
  static bool _navigatedToHome = false;

  static bool get isNavigatedToHome => _navigatedToHome;
  static void setNavigatedToHome(bool value) {
    _navigatedToHome = value;
  }

  SupabaseClient get supabase => supabaseClient ?? Supabase.instance.client;

  static List<String> get fallbackBaseUrls {
    if (kIsWeb) return ['http://localhost:8000'];
    if (defaultTargetPlatform == TargetPlatform.android) {
      return [
        'http://127.0.0.1:8000',
        'http://192.168.0.112:8000',
        'http://10.0.2.2:8000',
      ];
    }
    return ['http://localhost:8000', 'http://127.0.0.1:8000'];
  }

  AuthService({
    Dio? dio,
    StorageService? storageService,
    this.supabaseClient,
  })  : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 10),
                headers: {'Content-Type': 'application/json'},
              ),
            ),
        _storageService = storageService ?? StorageService() {
    _initAuthStateListener();
  }

  /// Sets up onAuthStateChange listener that saves credentials and navigates
  /// to the home screen once a session is established.
  void _initAuthStateListener() {
    if (_staticAuthSubscription != null) return;
    try {
      _staticAuthSubscription = supabase.auth.onAuthStateChange.listen((data) async {
        final session = data.session;
        if (data.event == AuthChangeEvent.signedOut) {
          _navigatedToHome = false;
        } else if (data.event == AuthChangeEvent.signedIn && session != null) {
          if (_navigatedToHome) return;
          _navigatedToHome = true;
          debugPrint('Supabase Auth session established: ${session.user.id}');
          final accessToken = session.accessToken;
          final refreshToken = session.refreshToken ?? '';
          await _storageService.saveTokens(
            accessToken: accessToken,
            refreshToken: refreshToken,
          );

          final user = session.user;
          final email = user.email ?? '';
          final name = (user.userMetadata?['full_name'] as String?) ??
              (user.userMetadata?['name'] as String?) ??
              (user.userMetadata?['user_name'] as String?) ??
              (email.isNotEmpty ? email : 'User');

          await _storageService.saveUserInfo(
            userId: user.id,
            email: email,
            name: name,
          );

          ApiClient.navigatorKey.currentState?.pushNamedAndRemoveUntil(
            '/home',
            (route) => false,
            arguments: name,
          );
        }
      });
    } catch (e) {
      debugPrint('Supabase onAuthStateChange listener initialization skipped: $e');
    }
  }

  /// Signs in using Google OAuth via Supabase.
  Future<bool> signInWithGoogle() async {
    return await supabase.auth.signInWithOAuth(
      OAuthProvider.google,
      redirectTo: 'com.abhijithbhat.buildcrew://login-callback',
      authScreenLaunchMode: LaunchMode.externalApplication,
    );
  }

  /// Signs in using GitHub OAuth via Supabase.
  Future<bool> signInWithGitHub() async {
    return await supabase.auth.signInWithOAuth(
      OAuthProvider.github,
      redirectTo: 'com.abhijithbhat.buildcrew://login-callback',
      authScreenLaunchMode: LaunchMode.externalApplication,
    );
  }

  /// Execute POST with automatic fallback across available network interfaces.
  Future<Response> _postWithFallback(String path, Map<String, dynamic> data) async {
    DioException? lastException;
    for (final baseUrl in fallbackBaseUrls) {
      try {
        _dio.options.baseUrl = baseUrl;
        debugPrint('ATTEMPTING REQUEST to $baseUrl$path');
        final response = await _dio.post(path, data: data);
        ApiClient.activeBaseUrl = baseUrl;
        return response;
      } on DioException catch (e) {
        lastException = e;
        // Only fallback on connection failures, not 4xx/5xx HTTP response errors
        final isConnError = e.type == DioExceptionType.connectionError ||
            e.type == DioExceptionType.connectionTimeout ||
            e.type == DioExceptionType.receiveTimeout ||
            (e.message != null &&
                (e.message!.contains('Connection refused') ||
                    e.message!.contains('No route to host') ||
                    e.message!.contains('SocketException')));
        if (isConnError) {
          debugPrint('FAILED endpoint $baseUrl$path due to connection error. Retrying next...');
          continue;
        }
        rethrow;
      }
    }
    throw lastException ?? 'Cannot connect to backend server. Please check your network.';
  }

  /// Calls POST /auth/login with email and password.
  /// Securely stores returned access_token and refresh_token.
  /// Returns the full response map on success.
  /// Throws a user-friendly error string on failure.
  Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _postWithFallback(
        '/auth/login',
        {
          'email': email,
          'password': password,
        },
      );
      debugPrint('LOGIN SUCCESS: ${response.data}');

      final data = response.data as Map<String, dynamic>;
      final accessToken = data['access_token'] as String?;
      final refreshToken = data['refresh_token'] as String?;
      final user = data['user'] as Map<String, dynamic>?;
      final dName = (user?['display_name'] as String?) ?? (user?['name'] as String?);

      if (accessToken != null) {
        await _storageService.saveTokens(
          accessToken: accessToken,
          refreshToken: refreshToken,
        );
      }

      await _storageService.saveUserInfo(
        userId: user?['id'] as String?,
        email: (user?['email'] as String?) ?? email,
        name: dName,
      );

      return data;
    } on DioException catch (e) {
      debugPrint('LOGIN ERROR (DioException): ${e.message}, response=${e.response?.data}');
      if (e.response?.data != null) {
        final data = e.response!.data;
        if (data is Map) {
          if (data.containsKey('detail')) throw data['detail'].toString();
          if (data.containsKey('message')) throw data['message'].toString();
          if (data.containsKey('error')) throw data['error'].toString();
        } else if (data is String && data.isNotEmpty) {
          throw data;
        }
      }
      if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.receiveTimeout ||
          e.type == DioExceptionType.connectionError) {
        throw 'Cannot connect to server. Please check server IP / network.';
      }
      throw e.message ?? 'Login failed. Please try again.';
    } catch (e) {
      debugPrint('LOGIN ERROR: $e');
      if (e is String) rethrow;
      throw 'An unexpected error occurred.';
    }
  }

  /// Calls POST /auth/signup with email, password, and optional name.
  /// Stores tokens if session is present in the response.
  /// Returns the full response map on success.
  /// Throws a user-friendly error string on failure.
  Future<Map<String, dynamic>> signup({
    required String email,
    required String password,
    String? name,
  }) async {
    try {
      final response = await _postWithFallback(
        '/auth/signup',
        {
          'email': email,
          'password': password,
          if (name != null && name.trim().isNotEmpty) 'name': name.trim(),
        },
      );
      debugPrint('SIGNUP SUCCESS: ${response.data}');

      final data = response.data as Map<String, dynamic>;
      final session = data['session'];
      final user = data['user'] as Map<String, dynamic>?;
      final dName = (user?['display_name'] as String?) ?? (user?['name'] as String?) ?? name;

      if (session != null && session is Map<String, dynamic>) {
        final accessToken = session['access_token'] as String?;
        final refreshToken = session['refresh_token'] as String?;
        if (accessToken != null) {
          await _storageService.saveTokens(
            accessToken: accessToken,
            refreshToken: refreshToken,
          );
        }
      }

      await _storageService.saveUserInfo(
        userId: user?['id'] as String?,
        email: (user?['email'] as String?) ?? email,
        name: dName,
      );

      return data;
    } on DioException catch (e) {
      debugPrint('SIGNUP ERROR (DioException): ${e.message}, response=${e.response?.data}');
      if (e.response?.data != null) {
        final data = e.response!.data;
        if (data is Map) {
          if (data.containsKey('detail')) throw data['detail'].toString();
          if (data.containsKey('message')) throw data['message'].toString();
          if (data.containsKey('error')) throw data['error'].toString();
        } else if (data is String && data.isNotEmpty) {
          throw data;
        }
      }
      if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.receiveTimeout ||
          e.type == DioExceptionType.connectionError) {
        throw 'Cannot connect to server. Please check server IP / network.';
      }
      throw e.message ?? 'Sign up failed. Please try again.';
    } catch (e) {
      debugPrint('SIGNUP ERROR: $e');
      if (e is String) rethrow;
      throw 'An unexpected error occurred.';
    }
  }

  /// Calls POST /auth/verify-otp with email, token, optional type, and optional displayName.
  /// Stores access and refresh tokens if present in response.
  Future<Map<String, dynamic>> verifyOtp({
    required String email,
    required String token,
    String type = 'signup',
    String? displayName,
  }) async {
    try {
      final response = await _postWithFallback(
        '/auth/verify-otp',
        {
          'email': email,
          'token': token,
          'type': type,
        },
      );
      debugPrint('VERIFY OTP SUCCESS: ${response.data}');
      final data = response.data as Map<String, dynamic>;
      final accessToken = data['access_token'] as String?;
      final refreshToken = data['refresh_token'] as String?;
      final user = data['user'] as Map<String, dynamic>?;
      final dName = (user?['display_name'] as String?) ?? (user?['name'] as String?) ?? displayName;

      if (accessToken != null) {
        await _storageService.saveTokens(
          accessToken: accessToken,
          refreshToken: refreshToken,
        );
      }

      await _storageService.saveUserInfo(
        userId: user?['id'] as String?,
        email: (user?['email'] as String?) ?? email,
        name: dName,
      );

      return data;


    } on DioException catch (e) {
      if (e.response?.data != null) {
        final data = e.response!.data;
        if (data is Map && data.containsKey('detail')) throw data['detail'].toString();
      }
      throw e.message ?? 'OTP Verification failed. Please try again.';
    } catch (e) {
      if (e is String) rethrow;
      throw 'An unexpected error occurred.';
    }
  }

  /// Calls POST /auth/forgot-password with email.
  Future<Map<String, dynamic>> forgotPassword({required String email}) async {
    try {
      final response = await _postWithFallback(
        '/auth/forgot-password',
        {'email': email},
      );
      debugPrint('FORGOT PASSWORD SUCCESS: ${response.data}');
      return response.data as Map<String, dynamic>;
    } on DioException catch (e) {
      if (e.response?.data != null) {
        final data = e.response!.data;
        if (data is Map && data.containsKey('detail')) throw data['detail'].toString();
      }
      throw e.message ?? 'Password reset request failed.';
    } catch (e) {
      if (e is String) rethrow;
      throw 'An unexpected error occurred.';
    }
  }

  /// Calls POST /auth/reset-password with email, OTP token, and new password.
  Future<Map<String, dynamic>> resetPassword({
    required String email,
    required String token,
    required String newPassword,
  }) async {
    try {
      final response = await _postWithFallback(
        '/auth/reset-password',
        {
          'email': email,
          'token': token,
          'new_password': newPassword,
        },
      );
      debugPrint('RESET PASSWORD SUCCESS: ${response.data}');
      return response.data as Map<String, dynamic>;
    } on DioException catch (e) {
      if (e.response?.data != null) {
        final data = e.response!.data;
        if (data is Map && data.containsKey('detail')) throw data['detail'].toString();
      }
      throw e.message ?? 'Password reset failed.';
    } catch (e) {
      if (e is String) rethrow;
      throw 'An unexpected error occurred.';
    }
  }

  /// Calls POST /auth/refresh with refresh token to get a new session.
  Future<Map<String, dynamic>> refreshToken({String? refreshToken}) async {
    final token = refreshToken ?? await _storageService.getRefreshToken();
    if (token == null || token.trim().isEmpty) {
      throw 'No refresh token available';
    }
    try {
      final response = await _postWithFallback(
        '/auth/refresh',
        {'refresh_token': token.trim()},
      );
      final data = response.data as Map<String, dynamic>;
      final newAccessToken = data['access_token']?.toString();
      final newRefreshToken = data['refresh_token']?.toString();
      if (newAccessToken != null && newAccessToken.isNotEmpty) {
        await _storageService.saveTokens(
          accessToken: newAccessToken,
          refreshToken: newRefreshToken ?? token,
        );
      }
      return data;
    } on DioException catch (e) {
      if (e.response?.data != null) {
        final data = e.response!.data;
        if (data is Map && data.containsKey('detail')) throw data['detail'].toString();
      }
      throw e.message ?? 'Token refresh failed.';
    } catch (e) {
      if (e is String) rethrow;
      throw 'An unexpected error occurred.';
    }
  }

  /// Retrieve stored access token from FlutterSecureStorage.
  Future<String?> getStoredAccessToken() async {
    return await _storageService.getAccessToken();
  }

  /// Clear tokens securely from storage on logout.
  Future<void> logout() async {
    _navigatedToHome = false;
    try {
      await supabase.auth.signOut();
    } catch (_) {}
    await _storageService.clearTokens();
  }

  /// Cancels any active Supabase auth state subscription.
  void dispose() {
    _staticAuthSubscription?.cancel();
    _staticAuthSubscription = null;
    _navigatedToHome = false;
  }
}

