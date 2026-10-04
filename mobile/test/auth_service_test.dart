import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/services/api_client.dart';
import 'package:mobile/services/auth_service.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

class FakeAuthStorageService extends StorageService {
  String? savedAccessToken;
  String? savedRefreshToken;
  String? savedUserId;
  String? savedEmail;
  String? savedName;

  @override
  Future<void> saveTokens({
    required String accessToken,
    String? refreshToken,
  }) async {
    savedAccessToken = accessToken;
    savedRefreshToken = refreshToken;
  }

  @override
  Future<void> saveUserInfo({
    String? userId,
    String? email,
    String? name,
  }) async {
    savedUserId = userId;
    savedEmail = email;
    savedName = name;
  }
}

class FakeAuthGoTrueClient extends Fake implements GoTrueClient {
  final _controller = StreamController<AuthState>.broadcast();
  Session? _currentSession;

  @override
  Session? get currentSession => _currentSession;

  @override
  Stream<AuthState> get onAuthStateChange => _controller.stream;

  void emitAuthState(AuthChangeEvent event, Session? session) {
    _currentSession = session;
    _controller.add(AuthState(event, session));
  }

  void close() {
    _controller.close();
  }
}

class FakeAuthSupabaseClient extends Fake implements SupabaseClient {
  @override
  final GoTrueClient auth;

  FakeAuthSupabaseClient(this.auth);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeAuthStorageService fakeStorage;
  late FakeAuthGoTrueClient fakeGoTrue;
  late FakeAuthSupabaseClient fakeSupabase;

  setUp(() {
    AuthService.resetStaticState();
    fakeStorage = FakeAuthStorageService();
    fakeGoTrue = FakeAuthGoTrueClient();
    fakeSupabase = FakeAuthSupabaseClient(fakeGoTrue);
  });

  tearDown(() {
    AuthService.resetStaticState();
    fakeGoTrue.close();
  });

  User createTestUser({
    String id = 'test-user-id',
    String email = 'user@example.com',
    String name = 'Test User',
  }) {
    return User(
      id: id,
      appMetadata: {},
      userMetadata: {'full_name': name},
      aud: 'authenticated',
      createdAt: DateTime.now().toIso8601String(),
      email: email,
    );
  }

  Session createTestSession({
    required User user,
    String accessToken = 'access-token-123',
    String refreshToken = 'refresh-token-456',
  }) {
    return Session(
      accessToken: accessToken,
      refreshToken: refreshToken,
      tokenType: 'bearer',
      user: user,
    );
  }

  testWidgets('onAuthStateChange signedIn saves tokens and user info, and navigates once', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: ApiClient.navigatorKey,
        initialRoute: '/login',
        routes: {
          '/login': (_) => const Scaffold(body: Text('Login')),
          '/home': (_) => const Scaffold(body: Text('Home')),
        },
      ),
    );

    final authService = AuthService(
      storageService: fakeStorage,
      supabaseClient: fakeSupabase,
    );

    final user = createTestUser(name: 'Alice Dev');
    final session = createTestSession(user: user, accessToken: 'jwt-alice', refreshToken: 'ref-alice');

    // Emit signedIn event
    fakeGoTrue.emitAuthState(AuthChangeEvent.signedIn, session);
    await tester.pumpAndSettle();

    expect(fakeStorage.savedAccessToken, 'jwt-alice');
    expect(fakeStorage.savedRefreshToken, 'ref-alice');
    expect(fakeStorage.savedUserId, 'test-user-id');
    expect(fakeStorage.savedEmail, 'user@example.com');
    expect(fakeStorage.savedName, 'Alice Dev');
    expect(AuthService.isNavigatedToHome, isTrue);

    // Emit signedIn a second time -> should NOT navigate again
    final session2 = createTestSession(user: user, accessToken: 'jwt-alice-2', refreshToken: 'ref-alice-2');
    fakeGoTrue.emitAuthState(AuthChangeEvent.signedIn, session2);
    await tester.pumpAndSettle();

    // Tokens updated in storage, but navigation remained single
    expect(fakeStorage.savedAccessToken, 'jwt-alice-2');
    expect(fakeStorage.savedRefreshToken, 'ref-alice-2');
    expect(AuthService.isNavigatedToHome, isTrue);

    authService.dispose();
  });

  testWidgets('onAuthStateChange tokenRefreshed writes tokens to StorageService without navigating', (tester) async {
    final authService = AuthService(
      storageService: fakeStorage,
      supabaseClient: fakeSupabase,
    );

    final user = createTestUser(name: 'Bob Dev');
    final refreshedSession = createTestSession(
      user: user,
      accessToken: 'refreshed-access-token',
      refreshToken: 'refreshed-refresh-token',
    );

    expect(AuthService.isNavigatedToHome, isFalse);

    // Emit tokenRefreshed
    fakeGoTrue.emitAuthState(AuthChangeEvent.tokenRefreshed, refreshedSession);
    await tester.pumpAndSettle();

    // Verify tokens were written to storage
    expect(fakeStorage.savedAccessToken, 'refreshed-access-token');
    expect(fakeStorage.savedRefreshToken, 'refreshed-refresh-token');
    expect(fakeStorage.savedUserId, 'test-user-id');
    // Navigation to home did not occur
    expect(AuthService.isNavigatedToHome, isFalse);

    authService.dispose();
  });

  testWidgets('onAuthStateChange userUpdated writes tokens and user info to StorageService without navigating', (tester) async {
    final authService = AuthService(
      storageService: fakeStorage,
      supabaseClient: fakeSupabase,
    );

    final updatedUser = createTestUser(name: 'Charlie Updated', email: 'charlie@new.com');
    final updatedSession = createTestSession(
      user: updatedUser,
      accessToken: 'updated-user-token',
      refreshToken: 'updated-refresh-token',
    );

    expect(AuthService.isNavigatedToHome, isFalse);

    // Emit userUpdated
    fakeGoTrue.emitAuthState(AuthChangeEvent.userUpdated, updatedSession);
    await tester.pumpAndSettle();

    // Verify tokens and profile were written to storage
    expect(fakeStorage.savedAccessToken, 'updated-user-token');
    expect(fakeStorage.savedRefreshToken, 'updated-refresh-token');
    expect(fakeStorage.savedEmail, 'charlie@new.com');
    expect(fakeStorage.savedName, 'Charlie Updated');
    // Navigation to home did not occur
    expect(AuthService.isNavigatedToHome, isFalse);

    authService.dispose();
  });

  testWidgets('onAuthStateChange signedOut resets navigation state', (tester) async {
    final authService = AuthService(
      storageService: fakeStorage,
      supabaseClient: fakeSupabase,
    );

    AuthService.setNavigatedToHome(true);
    expect(AuthService.isNavigatedToHome, isTrue);

    // Emit signedOut
    fakeGoTrue.emitAuthState(AuthChangeEvent.signedOut, null);
    await tester.pumpAndSettle();

    expect(AuthService.isNavigatedToHome, isFalse);

    authService.dispose();
  });
}
