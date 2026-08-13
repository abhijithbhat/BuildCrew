import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

class HealthService {
  final Dio _dio;

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

  HealthService({Dio? dio, String? baseUrl})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 5),
                receiveTimeout: const Duration(seconds: 5),
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
