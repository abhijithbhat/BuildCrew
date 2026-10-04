import 'package:dio/dio.dart';

/// Maps DioException types, HTTP status codes (401, 403, 404, 409, 413, 415, 422, 429, 5xx),
/// and general exceptions to short, user-friendly messages.
String friendlyError(Object e) {
  if (e is DioException) {
    return _parseDioException(e);
  }

  // Handle String error (e.g. rethrown strings from services)
  if (e is String) {
    return _sanitizeString(e);
  }

  // Fallback for general exceptions
  final raw = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '').trim();
  return _sanitizeString(raw);
}

String _parseDioException(DioException e) {
  // If we have an HTTP response with a status code
  if (e.response != null) {
    final statusCode = e.response!.statusCode;
    final data = e.response!.data;

    // Check if backend returned a clean, user-safe message in detail or message
    String? backendDetail;
    if (data is Map) {
      final detail = data['detail'] ?? data['message'] ?? data['error'];
      if (detail is String && detail.trim().isNotEmpty && !detail.startsWith('<')) {
        backendDetail = detail.trim();
      } else if (detail is List && detail.isNotEmpty) {
        final messages = detail
            .map((item) => item is Map ? (item['msg'] ?? item.toString()) : item.toString())
            .where((msg) => msg.trim().isNotEmpty)
            .join('\n');
        if (messages.isNotEmpty) {
          backendDetail = messages;
        }
      }
    } else if (data is String &&
        data.trim().isNotEmpty &&
        !data.startsWith('<') &&
        !data.contains('<!DOCTYPE')) {
      backendDetail = data.trim();
    }

    // Map specific HTTP status codes
    if (statusCode != null) {
      switch (statusCode) {
        case 401:
          return backendDetail ?? 'Session expired or invalid credentials. Please log in again.';
        case 403:
          return backendDetail ?? 'You do not have permission to perform this action.';
        case 404:
          return backendDetail ?? 'The requested resource was not found.';
        case 409:
          return backendDetail ?? 'A conflict occurred with an existing resource.';
        case 413:
          return backendDetail ?? 'File size exceeds the 25 MB limit.';
        case 415:
          return backendDetail ?? 'Unsupported file format. Please upload an allowed file type.';
        case 422:
          return backendDetail ?? 'Invalid data provided. Please check your inputs.';
        case 429:
          return backendDetail ?? 'Too many requests. Please wait a moment and try again.';
        default:
          if (statusCode >= 500 && statusCode <= 599) {
            return backendDetail ?? 'Server error. Please try again later.';
          }
          if (backendDetail != null && backendDetail.isNotEmpty) {
            return backendDetail;
          }
          return 'Request failed with status $statusCode. Please try again.';
      }
    }

    if (backendDetail != null && backendDetail.isNotEmpty) {
      return backendDetail;
    }
  }

  // Handle DioException types
  switch (e.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
      return 'Connection timed out. Please check your network connection.';
    case DioExceptionType.connectionError:
      return 'Cannot connect to server. Please check your network connection.';
    case DioExceptionType.cancel:
      return 'Request was cancelled.';
    case DioExceptionType.badCertificate:
      return 'Security certificate error. Connection is not secure.';
    case DioExceptionType.badResponse:
      return 'Server error. Please try again later.';
    case DioExceptionType.unknown:
    default:
      if (e.message != null && e.message!.isNotEmpty) {
        return _sanitizeString(e.message!);
      }
      return 'Network connection error. Please try again.';
  }
}

String _sanitizeString(String raw) {
  final cleaned = raw.replaceFirst(RegExp(r'^Exception:\s*'), '').trim();
  if (cleaned.isEmpty || cleaned == 'Exception') {
    return 'Something went wrong. Please try again.';
  }
  if (cleaned.contains('SocketException') ||
      cleaned.contains('Connection refused') ||
      cleaned.contains('Network is unreachable') ||
      cleaned.contains('Failed host lookup')) {
    return 'Cannot connect to server. Please check your network connection.';
  }
  if (cleaned.contains('HandshakeException') || cleaned.contains('CERTIFICATE_VERIFY_FAILED')) {
    return 'Security certificate error. Unable to verify server.';
  }
  return cleaned;
}
