import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class StorageService {
  final FlutterSecureStorage _storage;
  final Map<String, String> _inMemoryFallback = {};

  static const String _keyAccessToken = 'access_token';
  static const String _keyRefreshToken = 'refresh_token';
  static const String _keyUserId = 'user_id';
  static const String _keyUserEmail = 'user_email';
  static const String _keyUserName = 'user_name';

  StorageService({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  /// Save access token (and optional refresh token) securely.
  Future<void> saveTokens({
    required String accessToken,
    String? refreshToken,
  }) async {
    try {
      await _storage.write(key: _keyAccessToken, value: accessToken);
      if (refreshToken != null) {
        await _storage.write(key: _keyRefreshToken, value: refreshToken);
      }
    } catch (_) {
      _inMemoryFallback[_keyAccessToken] = accessToken;
      if (refreshToken != null) {
        _inMemoryFallback[_keyRefreshToken] = refreshToken;
      }
    }
  }

  /// Save user profile identifiers securely.
  Future<void> saveUserInfo({
    String? userId,
    String? email,
    String? name,
  }) async {
    try {
      if (userId != null && userId.isNotEmpty) {
        await _storage.write(key: _keyUserId, value: userId);
      }
      if (email != null && email.isNotEmpty) {
        await _storage.write(key: _keyUserEmail, value: email);
      }
      if (name != null && name.isNotEmpty) {
        await _storage.write(key: _keyUserName, value: name);
      }
    } catch (_) {
      if (userId != null && userId.isNotEmpty) {
        _inMemoryFallback[_keyUserId] = userId;
      }
      if (email != null && email.isNotEmpty) {
        _inMemoryFallback[_keyUserEmail] = email;
      }
      if (name != null && name.isNotEmpty) {
        _inMemoryFallback[_keyUserName] = name;
      }
    }
  }

  /// Retrieve the stored access token.
  Future<String?> getAccessToken() async {
    try {
      return await _storage.read(key: _keyAccessToken);
    } catch (_) {
      return _inMemoryFallback[_keyAccessToken];
    }
  }

  /// Retrieve the stored refresh token.
  Future<String?> getRefreshToken() async {
    try {
      return await _storage.read(key: _keyRefreshToken);
    } catch (_) {
      return _inMemoryFallback[_keyRefreshToken];
    }
  }

  /// Retrieve the stored user ID.
  Future<String?> getUserId() async {
    try {
      return await _storage.read(key: _keyUserId);
    } catch (_) {
      return _inMemoryFallback[_keyUserId];
    }
  }

  /// Retrieve the stored user email.
  Future<String?> getUserEmail() async {
    try {
      return await _storage.read(key: _keyUserEmail);
    } catch (_) {
      return _inMemoryFallback[_keyUserEmail];
    }
  }

  /// Retrieve the stored user name.
  Future<String?> getUserName() async {
    try {
      return await _storage.read(key: _keyUserName);
    } catch (_) {
      return _inMemoryFallback[_keyUserName];
    }
  }

  /// Delete stored auth tokens and user info (for logout).
  Future<void> clearTokens() async {
    try {
      await _storage.delete(key: _keyAccessToken);
      await _storage.delete(key: _keyRefreshToken);
      await _storage.delete(key: _keyUserId);
      await _storage.delete(key: _keyUserEmail);
      await _storage.delete(key: _keyUserName);
    } catch (_) {
      _inMemoryFallback.clear();
    }
  }
}
