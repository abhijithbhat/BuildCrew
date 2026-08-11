import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'storage_service.dart';

class AuthService {
  final Dio _dio;
  final StorageService _storageService;

  static String get defaultBaseUrl => 'http://127.0.0.1:8000';

  AuthService({Dio? dio, String? baseUrl, StorageService? storageService})
      : _dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: baseUrl ?? defaultBaseUrl,
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 10),
                headers: {'Content-Type': 'application/json'},
              ),
            ),
        _storageService = storageService ?? StorageService();

  /// Calls POST /auth/login with email and password.
  /// Securely stores returned access_token and refresh_token.
  /// Returns the full response map on success.
  /// Throws a user-friendly error string on failure.
  Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _dio.post(
        '/auth/login',
        data: {
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
          e.type == DioExceptionType.receiveTimeout) {
        throw 'Connection timed out. Please check your network.';
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
      final response = await _dio.post(
        '/auth/signup',
        data: {
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
          e.type == DioExceptionType.receiveTimeout) {
        throw 'Connection timed out. Please check your network.';
      }
      throw e.message ?? 'Sign up failed. Please try again.';
    } catch (e) {
      debugPrint('SIGNUP ERROR: $e');
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

