import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api_client.dart';
import 'storage_service.dart';

class GitHubService {
  final Dio _dio;
  final StorageService _storageService;

  static List<String> get fallbackBaseUrls => ApiClient.fallbackBaseUrls;

  GitHubService({Dio? dio, StorageService? storageService})
      : _storageService = storageService ?? StorageService(),
        _dio = dio ?? ApiClient.instance.dio;

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
        if (data is Map) {
          final detail = data['detail'] ?? data['message'] ?? data['error'];
          if (detail != null) {
            if (detail is List && detail.isNotEmpty) {
              return detail
                  .map((e) => e is Map ? (e['msg'] ?? e.toString()) : e.toString())
                  .join('\n');
            }
            return detail.toString();
          }
        } else if (data is String && data.trim().isNotEmpty && !data.startsWith('<')) {
          return data.trim();
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

    final endpoints = <String>[
      if (ApiClient.activeBaseUrl.isNotEmpty && fallbackBaseUrls.contains(ApiClient.activeBaseUrl))
        ApiClient.activeBaseUrl,
      ...fallbackBaseUrls.where((u) => u != ApiClient.activeBaseUrl),
    ];

    for (final baseUrl in endpoints) {
      try {
        final response = await requestFn(baseUrl, options);
        if (response.data != null) {
          ApiClient.activeBaseUrl = baseUrl;
          return response.data!;
        }
      } on DioException catch (e) {
        lastError = e;
        // Only fallback on connection/network failures, never on 4xx/5xx HTTP responses
        final isConnError = e.type == DioExceptionType.connectionError ||
            e.type == DioExceptionType.connectionTimeout ||
            e.type == DioExceptionType.receiveTimeout ||
            e.type == DioExceptionType.sendTimeout ||
            (e.message != null &&
                (e.message!.contains('Connection refused') ||
                    e.message!.contains('No route to host') ||
                    e.message!.contains('SocketException')));
        if (isConnError) {
          debugPrint('GitHubService fallback failed on $baseUrl due to connection error. Retrying next...');
          continue;
        }
        // If the server answered with an HTTP status code (4xx, 5xx),
        // we reached the server! Do not fallback to another URL.
        ApiClient.activeBaseUrl = baseUrl;
        throw _parseDioError(e);
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
    final url = data['url'] as String?;
    if (url == null || url.isEmpty) {
      throw "Couldn't start GitHub connection. Try again.";
    }
    return url;
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

  /// Explicitly link an installation to a project, or link existing lead installation without a GitHub trip.
  Future<Map<String, dynamic>> linkInstallation(
    String projectId, {
    String? installationId,
    String? repoFullName,
  }) async {
    final payload = <String, dynamic>{};
    if (installationId != null &&
        installationId.isNotEmpty &&
        installationId != 'auto' &&
        installationId != '0') {
      payload['installation_id'] = installationId;
    }
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
    final urlString = await getInstallUrl(projectId);
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

  /// List all repositories granted to this installation.
  Future<Map<String, dynamic>> getInstallationRepositories(String projectId) async {
    return await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.get(
        '$baseUrl/projects/$projectId/github/repositories',
        options: options,
      ),
    );
  }

  /// Switch the active linked repository for this project.
  Future<Map<String, dynamic>> selectRepository(String projectId, String repoFullName) async {
    return await _executeWithFallback<Map<String, dynamic>>(
      (baseUrl, options) => _dio.post(
        '$baseUrl/projects/$projectId/github/select-repository',
        data: {'repo_full_name': repoFullName},
        options: options,
      ),
    );
  }
}

