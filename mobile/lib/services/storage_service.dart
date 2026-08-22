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
      await clearContributionDraft();
    } catch (_) {
      _inMemoryFallback.clear();
    }
  }

  static const String _keyDraftProjectId = 'draft_project_id';
  static const String _keyDraftTitle = 'draft_title';
  static const String _keyDraftCategory = 'draft_category';
  static const String _keyDraftDesc = 'draft_desc';
  static const String _keyDraftLink = 'draft_link';

  /// Save active contribution draft state (e.g. before camera intent).
  Future<void> saveContributionDraft({
    required String projectId,
    String? title,
    String? category,
    String? description,
    String? link,
  }) async {
    try {
      await _storage.write(key: _keyDraftProjectId, value: projectId);
      if (title != null) await _storage.write(key: _keyDraftTitle, value: title);
      if (category != null) await _storage.write(key: _keyDraftCategory, value: category);
      if (description != null) await _storage.write(key: _keyDraftDesc, value: description);
      if (link != null) await _storage.write(key: _keyDraftLink, value: link);
    } catch (_) {
      _inMemoryFallback[_keyDraftProjectId] = projectId;
      if (title != null) _inMemoryFallback[_keyDraftTitle] = title;
      if (category != null) _inMemoryFallback[_keyDraftCategory] = category;
      if (description != null) _inMemoryFallback[_keyDraftDesc] = description;
      if (link != null) _inMemoryFallback[_keyDraftLink] = link;
    }
  }

  /// Retrieve active contribution draft state.
  Future<Map<String, String?>> getContributionDraft() async {
    try {
      final pid = await _storage.read(key: _keyDraftProjectId);
      if (pid == null || pid.isEmpty) return {};
      final title = await _storage.read(key: _keyDraftTitle);
      final category = await _storage.read(key: _keyDraftCategory);
      final desc = await _storage.read(key: _keyDraftDesc);
      final link = await _storage.read(key: _keyDraftLink);
      return {
        'projectId': pid,
        'title': title,
        'category': category,
        'description': desc,
        'link': link,
      };
    } catch (_) {
      final pid = _inMemoryFallback[_keyDraftProjectId];
      if (pid == null || pid.isEmpty) return {};
      return {
        'projectId': pid,
        'title': _inMemoryFallback[_keyDraftTitle],
        'category': _inMemoryFallback[_keyDraftCategory],
        'description': _inMemoryFallback[_keyDraftDesc],
        'link': _inMemoryFallback[_keyDraftLink],
      };
    }
  }

  /// Clear active contribution draft state.
  Future<void> clearContributionDraft() async {
    try {
      await _storage.delete(key: _keyDraftProjectId);
      await _storage.delete(key: _keyDraftTitle);
      await _storage.delete(key: _keyDraftCategory);
      await _storage.delete(key: _keyDraftDesc);
      await _storage.delete(key: _keyDraftLink);
    } catch (_) {
      _inMemoryFallback.remove(_keyDraftProjectId);
      _inMemoryFallback.remove(_keyDraftTitle);
      _inMemoryFallback.remove(_keyDraftCategory);
      _inMemoryFallback.remove(_keyDraftDesc);
      _inMemoryFallback.remove(_keyDraftLink);
    }
  }
}
