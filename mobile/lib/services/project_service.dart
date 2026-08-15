import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../models/project.dart';
import 'storage_service.dart';

class ProjectService {
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

  ProjectService({Dio? dio, StorageService? storageService})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 10),
                headers: {'Content-Type': 'application/json'},
              ),
            ),
        _storageService = storageService ?? StorageService();

  /// Retrieve the authentication headers with the stored JWT token.
  Future<Options> _getAuthOptions() async {
    final token = await _storageService.getAccessToken();
    if (token == null || token.isEmpty) {
      throw 'User is not authenticated. Please log in first.';
    }
    return Options(
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );
  }

  /// Extracts exact error details from response or exception.
  String _parseDioError(dynamic error) {
    if (error is DioException) {
      if (error.response != null && error.response!.data != null) {
        final data = error.response!.data;
        if (data is Map<String, dynamic>) {
          if (data.containsKey('detail')) {
            final detail = data['detail'];
            if (detail is List && detail.isNotEmpty) {
              return detail.map((e) => e['msg'] ?? e.toString()).join('\n');
            }
            return detail.toString();
          }
          if (data.containsKey('message')) {
            return data['message'].toString();
          }
        }
        return 'Server returned error: ${error.response!.statusCode}';
      }
      if (error.type == DioExceptionType.connectionTimeout ||
          error.type == DioExceptionType.receiveTimeout) {
        return 'Connection timed out. Please check your backend server.';
      }
      if (error.type == DioExceptionType.connectionError) {
        return 'Could not connect to backend server. Please verify network.';
      }
      return error.message ?? 'A network error occurred.';
    }
    return error.toString();
  }

  /// Execute POST with multi-endpoint fallback across ADB USB, Wi-Fi, and Emulator.
  Future<Response> _postWithFallback(
    String path,
    Map<String, dynamic> data, {
    Options? options,
  }) async {
    DioException? lastException;
    for (final baseUrl in fallbackBaseUrls) {
      try {
        _dio.options.baseUrl = baseUrl;
        debugPrint('ProjectService: Attempting POST to $baseUrl$path');
        return await _dio.post(path, data: data, options: options);
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
          debugPrint('FAILED endpoint $baseUrl$path. Retrying next...');
          continue;
        }
        rethrow;
      }
    }
    throw lastException ?? 'Cannot connect to backend server.';
  }

  /// Execute GET with multi-endpoint fallback.
  Future<Response> _getWithFallback(
    String path, {
    Options? options,
  }) async {
    DioException? lastException;
    for (final baseUrl in fallbackBaseUrls) {
      try {
        _dio.options.baseUrl = baseUrl;
        debugPrint('ProjectService: Attempting GET to $baseUrl$path');
        return await _dio.get(path, options: options);
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
          debugPrint('FAILED endpoint $baseUrl$path. Retrying next...');
          continue;
        }
        rethrow;
      }
    }
    throw lastException ?? 'Cannot connect to backend server.';
  }

  /// Create a new project via POST /projects.
  Future<Project> createProject({
    required String name,
    String? description,
  }) async {
    try {
      final options = await _getAuthOptions();
      final response = await _postWithFallback(
        '/projects',
        {
          'name': name.trim(),
          if (description != null && description.trim().isNotEmpty)
            'description': description.trim(),
        },
        options: options,
      );

      final data = response.data as Map<String, dynamic>;
      final projectJson = data['project'] as Map<String, dynamic>? ?? data;
      return Project.fromJson(projectJson);
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// List all projects for current user via GET /projects.
  Future<List<Project>> listProjects() async {
    try {
      final options = await _getAuthOptions();
      final response = await _getWithFallback('/projects', options: options);
      final data = response.data as Map<String, dynamic>;
      final list = data['projects'] as List<dynamic>? ?? [];
      return list
          .map((item) => Project.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// Generate a shareable invite code via POST /projects/{id}/invite.
  Future<Map<String, dynamic>> generateInviteCode(String projectId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _postWithFallback(
        '/projects/$projectId/invite',
        {},
        options: options,
      );
      return response.data as Map<String, dynamic>;
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// Join a project using an invite code via POST /projects/join.
  Future<Map<String, dynamic>> joinProject(String inviteCode) async {
    try {
      final options = await _getAuthOptions();
      final response = await _postWithFallback(
        '/projects/join',
        {'invite_code': inviteCode.trim().toUpperCase()},
        options: options,
      );
      return response.data as Map<String, dynamic>;
    } catch (e) {
      throw _parseDioError(e);
    }
  }
}
