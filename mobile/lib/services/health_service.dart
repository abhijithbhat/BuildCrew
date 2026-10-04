import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'api_client.dart';

class HealthService {
  final Dio _dio;

  static List<String> get fallbackBaseUrls => ApiClient.fallbackBaseUrls;

  HealthService({Dio? dio, String? baseUrl})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 8),
                receiveTimeout: const Duration(seconds: 20),
                sendTimeout: const Duration(seconds: 20),
              ),
            );

  Future<Map<String, dynamic>?> checkHealth() async {
    DioException? lastException;
    for (final baseUrl in fallbackBaseUrls) {
      try {
        _dio.options.baseUrl = baseUrl;
        final response = await _dio.get('/health');
        debugPrint('HEALTH CHECK SUCCESS via $baseUrl: ${response.data}');
        if (response.data is Map<String, dynamic>) {
          return response.data as Map<String, dynamic>;
        }
        return {'data': response.data};
      } on DioException catch (e) {
        lastException = e;
        debugPrint('HEALTH CHECK FAILED via $baseUrl: ${e.message}. Retrying...');
        continue;
      }
    }
    throw lastException ?? Exception('Backend health check failed across all endpoints.');
  }
}
