import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

class HealthService {
  final Dio _dio;

  static String get defaultBaseUrl => 'http://127.0.0.1:8000';

  HealthService({Dio? dio, String? baseUrl})
      : _dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: baseUrl ?? defaultBaseUrl,
                connectTimeout: const Duration(seconds: 5),
                receiveTimeout: const Duration(seconds: 5),
              ),
            );

  Future<Map<String, dynamic>?> checkHealth() async {
    try {
      final response = await _dio.get('/health');
      // ignore: avoid_print
      print('HEALTH CHECK SUCCESS: ${response.data}');
      debugPrint('HEALTH CHECK SUCCESS: ${response.data}');
      if (response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
      return {'data': response.data};
    } on DioException catch (e) {
      // ignore: avoid_print
      print('HEALTH CHECK ERROR (DioException): ${e.message}');
      debugPrint('HEALTH CHECK ERROR (DioException): ${e.message}');
      rethrow;
    } catch (e) {
      // ignore: avoid_print
      print('HEALTH CHECK ERROR: $e');
      debugPrint('HEALTH CHECK ERROR: $e');
      rethrow;
    }
  }
}
