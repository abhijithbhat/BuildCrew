import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'storage_service.dart';

/// Where the app should start: '/home' when a session or stored token exists,
/// otherwise '/login'. Used by main() and by the animated splash screen.
Future<String> resolveStartRoute({StorageService? storage}) async {
  try {
    final String? token = await (storage ?? StorageService()).getAccessToken();
    Session? session;
    try {
      session = Supabase.instance.client.auth.currentSession;
    } catch (_) {
      session = null;
    }
    if (session != null || (token != null && token.isNotEmpty)) {
      return '/home';
    }
  } catch (e) {
    debugPrint('resolveStartRoute error: $e');
  }
  return '/login';
}
