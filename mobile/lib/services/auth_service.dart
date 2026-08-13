import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'storage_service.dart';

class AuthService {
  final Dio _dio;
  final StorageService _storageService;

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

  AuthService({Dio? dio, StorageService? storageService})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 10),
                headers: {'Content-Type': 'application/json'},
              ),
            ),
        _storageService = storageService ?? StorageService();

  /// Execute POST with automatic fallback across available network interfaces.
  Future<Response> _postWithFallback(String path, Map<String, dynamic> data) async {
    DioException? lastException;
    for (final baseUrl in fallbackBaseUrls) {
      try {
        _dio.options.baseUrl = baseUrl;
        debugPrint('ATTEMPTING REQUEST to $baseUrl$path');
        return await _dio.post(path, data: data);
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

      if (accessToken != null) {
        await _storageService.saveTokens(
          accessToken: accessToken,
          refreshToken: refreshToken,
        );
      }

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

  /// Calls POST /auth/signup with email and password.
  /// Stores tokens if session is present in the response.
  /// Returns the full response map on success.
  /// Throws a user-friendly error string on failure.
  Future<Map<String, dynamic>> signup({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _postWithFallback(
        '/auth/signup',
        {
          'email': email,
          'password': password,
        },
      );
      debugPrint('SIGNUP SUCCESS: ${response.data}');

      final data = response.data as Map<String, dynamic>;
      final session = data['session'];
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

  /// Calls POST /auth/verify-otp with email, token, and optional type ('signup' or 'recovery').
  /// Stores access and refresh tokens if present in response.
  Future<Map<String, dynamic>> verifyOtp({
    required String email,
    required String token,
    String type = 'signup',
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
      if (accessToken != null) {
        await _storageService.saveTokens(
          accessToken: accessToken,
          refreshToken: refreshToken,
        );
      }
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

  /// Retrieve stored access token from FlutterSecureStorage.
  Future<String?> getStoredAccessToken() async {
    return await _storageService.getAccessToken();
  }

  /// Clear tokens securely from storage on logout.
  Future<void> logout() async {
    await _storageService.clearTokens();
  }
}

