import 'package:mobile/services/storage_service.dart';

/// In-memory StorageService for tests (no platform channels).
class MemStorage extends StorageService {
  MemStorage({this.userId = 'u1', this.userName});

  final String? userId;
  final String? userName;
  final Map<String, String> kv = <String, String>{};

  @override
  Future<String?> getUserId() async => userId;

  @override
  Future<String?> getUserName() async => userName;

  @override
  Future<String?> readString(String key) async => kv[key];

  @override
  Future<void> writeString(String key, String value) async {
    kv[key] = value;
  }

  @override
  Future<void> deleteString(String key) async {
    kv.remove(key);
  }
}
