import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';
import 'storage_service.dart';

class GitHubService {
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

  GitHubService({Dio? dio, StorageService? storageService})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 10),
                headers: {'Content-Type': 'application/json'},
              ),
            ),
        _storageService = storageService ?? StorageService();

  Future<Options> _getAuthOptions() async {
    final token = await _storageService.getAccessToken();
    if (token == null || token.isEmpty) {
      // In dev mode, provide mock token
      return Options(
        headers: {
          'Authorization': 'Bearer mock-dev-access-token-lead@example.com',
          'Content-Type': 'application/json',
        },
      );
    }
    return Options(
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );
  }

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
        return 'Server error: ${error.response!.statusCode}';
      }
      return 'Network connection failed. Please check your backend connection.';
    }
    return error.toString();
  }

  /// Helper for executing requests with automatic multi-endpoint fallback.
  Future<T> _executeWithFallback<T>(
    Future<Response<T>> Function(String baseUrl, Options authOptions) requestFn,
  ) async {
    final options = await _getAuthOptions();
    dynamic lastError;

    for (final baseUrl in fallbackBaseUrls) {
      try {
        final response = await requestFn(baseUrl, options);
        if (response.data != null) {
          return response.data!;
        }
      } catch (e) {
        lastError = e;
        debugPrint('GitHubService fallback failed on $baseUrl: $e');
      }
    }
    throw _parseDioError(lastError);
  }

  /// Retrieve the GitHub App installation URL for a project.
  Future<String> getInstallUrl(String projectId) async {
    final data = await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.get(
        '$baseUrl/projects/$projectId/github/install-url',
        options: options,
      ),
    );
    return data['url'] as String? ??
        'https://github.com/apps/BuildCrew-App/installations/new?state=$projectId';
  }

  /// Retrieve connected GitHub repository status for a project.
  Future<Map<String, dynamic>> getInstallation(String projectId) async {
    return await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.get(
        '$baseUrl/projects/$projectId/github/installation',
        options: options,
      ),
    );
  }

  /// Explicitly link an installation to a project.
  Future<Map<String, dynamic>> linkInstallation(
    String projectId,
    String installationId, {
    String? repoFullName,
  }) async {
    final payload = <String, dynamic>{
      'installation_id': installationId,
    };
    if (repoFullName != null && repoFullName.isNotEmpty) {
      payload['repo_full_name'] = repoFullName;
    }

    return await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.post(
        '$baseUrl/projects/$projectId/github/install',
        data: payload,
        options: options,
      ),
    );
  }

  /// Disconnect GitHub repository from a project (Team Lead only).
  Future<bool> unlinkInstallation(String projectId) async {
    final data = await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.delete(
        '$baseUrl/projects/$projectId/github/installation',
        options: options,
      ),
    );
    return data['success'] == true;
  }

  /// Fetch repository commit history.
  Future<List<Map<String, dynamic>>> getCommits(
    String projectId, {
    int perPage = 20,
    String? branch,
  }) async {
    final queryParams = <String, dynamic>{
      'per_page': perPage,
    };
    if (branch != null && branch.isNotEmpty) {
      queryParams['branch'] = branch;
    }


    final data = await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.get(
        '$baseUrl/projects/$projectId/github/commits',
        queryParameters: queryParams,
        options: options,
      ),
    );
    final rawList = data['commits'] as List<dynamic>? ?? [];
    return rawList.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  /// Fetch repository pull requests.
  Future<List<Map<String, dynamic>>> getPullRequests(
    String projectId, {
    String state = 'all',
    int perPage = 20,
  }) async {
    final data = await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.get(
        '$baseUrl/projects/$projectId/github/pulls',
        queryParameters: {'state': state, 'per_page': perPage},
        options: options,
      ),
    );
    final rawList = data['pulls'] as List<dynamic>? ?? [];
    return rawList.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  /// Fetch repository issues.
  Future<List<Map<String, dynamic>>> getIssues(
    String projectId, {
    String state = 'all',
    int perPage = 20,
  }) async {
    final data = await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.get(
        '$baseUrl/projects/$projectId/github/issues',
        queryParameters: {'state': state, 'per_page': perPage},
        options: options,
      ),
    );
    final rawList = data['issues'] as List<dynamic>? ?? [];
    return rawList.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  /// Opens the GitHub App installation flow directly in the browser.
  Future<bool> launchInstallFlow(String projectId) async {
    String urlString;
    try {
      urlString = await getInstallUrl(projectId);
    } catch (e) {
      debugPrint('Could not fetch dynamic install URL, using fallback: $e');
      urlString =
          'https://github.com/apps/BuildCrew-App/installations/new?state=$projectId';
    }

    final uri = Uri.parse(urlString);

    try {
      if (await canLaunchUrl(uri)) {
        return await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    } catch (_) {}

    // Direct attempt without canLaunchUrl check (handles certain Android OEM security sandboxes)
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e) {
      debugPrint('Launch externalApplication failed: $e, trying platformDefault');
      try {
        return await launchUrl(uri, mode: LaunchMode.platformDefault);
      } catch (err) {
        debugPrint('Failed to launch URL with any mode: $err');
        return false;
      }
    }
  }
}

