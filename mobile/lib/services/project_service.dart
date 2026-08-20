import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../models/contribution.dart';
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

  /// Regenerate a fresh invite code (revoking the previous code) for a project (Team Lead only).
  Future<Map<String, dynamic>> regenerateInviteCode(String projectId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _postWithFallback(
        '/projects/$projectId/invite/regenerate',
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

  /// Declare or update project role agreement via POST /projects/{projectId}/role.
  Future<Map<String, dynamic>> declareRole({
    required String projectId,
    required String declaredRole,
    String? responsibilities,
    DateTime? deadline,
  }) async {
    try {
      final options = await _getAuthOptions();
      final response = await _postWithFallback(
        '/projects/$projectId/role',
        {
          'declared_role': declaredRole.trim(),
          if (responsibilities != null && responsibilities.trim().isNotEmpty)
            'responsibilities': responsibilities.trim(),
          if (deadline != null) 'deadline': deadline.toIso8601String(),
        },
        options: options,
      );
      return response.data as Map<String, dynamic>;
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// List declared roles for a project via GET /projects/{projectId}/roles.
  Future<List<Map<String, dynamic>>> listProjectRoles(String projectId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _getWithFallback(
        '/projects/$projectId/roles',
        options: options,
      );
      final data = response.data as Map<String, dynamic>;
      final list = data['roles'] as List<dynamic>? ??
          data['role_agreements'] as List<dynamic>? ??
          [];
      final createdBy = data['created_by']?.toString() ?? data['lead_user_id']?.toString();
      final totalMembers = data['total_members'] as int?;
      final declaredCount = data['declared_count'] as int?;
      return list.map((item) {
        final map = Map<String, dynamic>.from(item as Map<String, dynamic>);
        if (createdBy != null && !map.containsKey('project_created_by')) {
          map['project_created_by'] = createdBy;
        }
        if (totalMembers != null) {
          map['total_members'] = totalMembers;
        }
        if (declaredCount != null) {
          map['declared_count'] = declaredCount;
        }
        return map;
      }).toList();
    } catch (e) {
      throw _parseDioError(e);
    }

  }

  /// Get raw declared roles payload including metadata (created_by, project_id).
  Future<Map<String, dynamic>> getProjectRolesData(String projectId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _getWithFallback(
        '/projects/$projectId/roles',
        options: options,
      );
      return response.data as Map<String, dynamic>;
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// Execute DELETE with multi-endpoint fallback.
  Future<Response> _deleteWithFallback(
    String path, {
    Options? options,
  }) async {
    DioException? lastException;
    for (final baseUrl in fallbackBaseUrls) {
      try {
        _dio.options.baseUrl = baseUrl;
        debugPrint('ProjectService: Attempting DELETE to $baseUrl$path');
        return await _dio.delete(path, options: options);
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

  /// Permanently delete / dismantle a project (Team Lead only) via DELETE /projects/{projectId}.
  Future<Map<String, dynamic>> deleteProject(String projectId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _deleteWithFallback(
        '/projects/$projectId',
        options: options,
      );
      return response.data as Map<String, dynamic>;
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// Leave a project (Teammate only) via POST /projects/{projectId}/leave.
  Future<Map<String, dynamic>> leaveProject(String projectId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _postWithFallback(
        '/projects/$projectId/leave',
        {},
        options: options,
      );
      return response.data as Map<String, dynamic>;
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// Generate contribution drafts from GitHub via POST /projects/{projectId}/generate-draft.
  Future<DraftGenerationResult> generateDraft(String projectId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _postWithFallback(
        '/projects/$projectId/generate-draft',
        {},
        options: options,
      );
      final data = response.data as Map<String, dynamic>;
      return DraftGenerationResult.fromJson(data);
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// List all contributions for a project via GET /projects/{projectId}/contributions.
  Future<List<Contribution>> listContributions(
    String projectId, {
    String? status,
    String? contributor,
    String? category,
  }) async {
    try {
      final options = await _getAuthOptions();
      final queryParams = <String, dynamic>{
        if (status != null && status.trim().isNotEmpty) 'status': status.trim(),
        if (contributor != null && contributor.trim().isNotEmpty) 'contributor': contributor.trim(),
        if (category != null && category.trim().isNotEmpty) 'category': category.trim(),
      };
      
      String queryString = '';
      if (queryParams.isNotEmpty) {
        queryString = '?${queryParams.entries.map((e) => '${e.key}=${Uri.encodeComponent(e.value.toString())}').join('&')}';
      }

      final response = await _getWithFallback(
        '/projects/$projectId/contributions$queryString',
        options: options,
      );
      final data = response.data as Map<String, dynamic>;
      final list = data['contributions'] as List<dynamic>? ?? [];
      return list
          .map((item) => Contribution.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (e) {
      throw _parseDioError(e);
    }
  }

  /// Remove a teammate from a project (Team Lead only) via DELETE /projects/{projectId}/members/{userId}.
  Future<Map<String, dynamic>> removeMember(String projectId, String userId) async {
    try {
      final options = await _getAuthOptions();
      final response = await _deleteWithFallback(
        '/projects/$projectId/members/$userId',
        options: options,
      );
      return response.data as Map<String, dynamic>;
    } catch (e) {
      throw _parseDioError(e);
    }
  }
}




