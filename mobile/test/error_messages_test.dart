import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/utils/error_messages.dart';

void main() {
  group('friendlyError tests', () {
    test('maps connection timeout', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        type: DioExceptionType.connectionTimeout,
      );
      expect(friendlyError(err), 'Connection timed out. Please check your network connection.');
    });

    test('maps connection error', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        type: DioExceptionType.connectionError,
      );
      expect(friendlyError(err), 'Cannot connect to server. Please check your network connection.');
    });

    test('maps HTTP 401 with default message', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 401,
          data: null,
        ),
      );
      expect(friendlyError(err), 'Session expired or invalid credentials. Please log in again.');
    });

    test('maps HTTP 401 with backend detail', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 401,
          data: {'detail': 'Invalid email or password.'},
        ),
      );
      expect(friendlyError(err), 'Invalid email or password.');
    });

    test('maps HTTP 403', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 403,
          data: null,
        ),
      );
      expect(friendlyError(err), 'You do not have permission to perform this action.');
    });

    test('maps HTTP 404', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 404,
          data: null,
        ),
      );
      expect(friendlyError(err), 'The requested resource was not found.');
    });

    test('maps HTTP 409', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 409,
          data: null,
        ),
      );
      expect(friendlyError(err), 'A conflict occurred with an existing resource.');
    });

    test('maps HTTP 413', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 413,
          data: null,
        ),
      );
      expect(friendlyError(err), 'File size exceeds the 25 MB limit.');
    });

    test('maps HTTP 415', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 415,
          data: null,
        ),
      );
      expect(friendlyError(err), 'Unsupported file format. Please upload an allowed file type.');
    });

    test('maps HTTP 422 with list details', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 422,
          data: {
            'detail': [
              {'msg': 'Password must be at least 12 characters long'}
            ]
          },
        ),
      );
      expect(friendlyError(err), 'Password must be at least 12 characters long');
    });

    test('maps HTTP 429', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 429,
          data: null,
        ),
      );
      expect(friendlyError(err), 'Too many requests. Please wait a moment and try again.');
    });

    test('maps HTTP 500 default', () {
      final err = DioException(
        requestOptions: RequestOptions(path: '/test'),
        response: Response(
          requestOptions: RequestOptions(path: '/test'),
          statusCode: 500,
          data: null,
        ),
      );
      expect(friendlyError(err), 'Server error. Please try again later.');
    });

    test('sanitizes general Exception string', () {
      final ex = Exception('Something went sideways');
      expect(friendlyError(ex), 'Something went sideways');
    });

    test('sanitizes SocketException string', () {
      final ex = Exception('SocketException: Connection refused (OS Error: Connection refused, errno = 111)');
      expect(friendlyError(ex), 'Cannot connect to server. Please check your network connection.');
    });
  });
}
