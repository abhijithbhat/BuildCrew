import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'screens/add_contribution_screen.dart';
import 'screens/connect_repository_screen.dart';
import 'screens/create_project_screen.dart';
import 'screens/declare_role_screen.dart';
import 'screens/forgot_password_screen.dart';
import 'screens/home_screen.dart';
import 'screens/invite_teammate_screen.dart';
import 'screens/join_project_screen.dart';
import 'screens/login_screen.dart';
import 'screens/my_contributions_screen.dart';
import 'screens/my_projects_screen.dart';
import 'screens/otp_screen.dart';
import 'screens/pending_confirmations_screen.dart';
import 'screens/project_detail_screen.dart';
import 'screens/publish_selection_screen.dart';
import 'screens/repo_status_screen.dart';
import 'screens/signup_screen.dart';
import 'screens/splash_screen.dart';
import 'screens/team_roles_screen.dart';
import 'services/api_client.dart';
import 'services/storage_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    await Supabase.initialize(
      url: 'https://bidfjrgytnqexwsdnwlt.supabase.co',
      publishableKey:
          'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJpZGZqcmd5dG5xZXh3c2Rud2x0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU0NzUzMDUsImV4cCI6MjEwMTA1MTMwNX0.uc2X-32-KNLx6iv-Ib0ACwZz0uMvR-EEok4qDKww1zE',
    );
  } catch (e) {
    debugPrint('Supabase initialize error: $e');
  }

  runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  final StorageService? storageService;
  final AppLinks? appLinks;

  const MyApp({super.key, this.storageService, this.appLinks});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  late final AppLinks _appLinks;
  StreamSubscription<Uri>? _linkSubscription;

  @override
  void initState() {
    super.initState();
    _appLinks = widget.appLinks ?? AppLinks();
    _initDeepLinks();
  }

  Future<void> _initDeepLinks() async {
    try {
      // 1. Listen for incoming URIs while the app is running (foreground or background)
      _linkSubscription = _appLinks.uriLinkStream.listen(
        (uri) {
          _handleIncomingUri(uri);
        },
        onError: (err) {
          debugPrint('AppLinks uriLinkStream error: $err');
        },
      );

      // 2. Check for incoming URI when the app is launched cold
      final initialUri = await _appLinks.getInitialLink();
      if (initialUri != null) {
        await _handleIncomingUri(initialUri);
      }
    } catch (e) {
      debugPrint('AppLinks initialization error: $e');
    }
  }

  Future<void> _handleIncomingUri(Uri uri) async {
    debugPrint('Received deep link: $uri');
    try {
      // Custom scheme: com.abhijithbhat.buildcrew, host: login-callback
      if (uri.scheme == 'com.abhijithbhat.buildcrew' &&
          (uri.host == 'login-callback' || uri.path.contains('login-callback'))) {
        final response =
            await Supabase.instance.client.auth.getSessionFromUrl(uri);
        final session = response.session;
        final storage = widget.storageService ?? StorageService();
        await storage.saveTokens(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken ?? '',
        );
        final user = session.user;
        final email = user.email ?? '';
        final name = (user.userMetadata?['full_name'] as String?) ??
            (user.userMetadata?['name'] as String?) ??
            (user.userMetadata?['user_name'] as String?) ??
            (email.isNotEmpty ? email : 'User');
        await storage.saveUserInfo(
          userId: user.id,
          email: email,
          name: name,
        );
        ApiClient.navigatorKey.currentState?.pushNamedAndRemoveUntil(
          HomeScreen.routeName,
          (route) => false,
          arguments: name,
        );
      }
    } catch (e) {
      debugPrint('Supabase getSessionFromUrl error: $e');
    }
  }

  @override
  void dispose() {
    _linkSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: ApiClient.navigatorKey,
      title: 'BuildCrew',
      debugShowCheckedModeBanner: false,
      initialRoute: '/',
      routes: {
        '/': (context) => AuthWrapper(storageService: widget.storageService),
        LoginScreen.routeName: (context) => const LoginScreen(),
        SignupScreen.routeName: (context) => const SignupScreen(),
        '/otp': (context) => const OtpScreen(),
        '/forgot-password': (context) => const ForgotPasswordScreen(),
        HomeScreen.routeName: (context) => const HomeScreen(),
        MyProjectsScreen.routeName: (context) => const MyProjectsScreen(),
        CreateProjectScreen.routeName: (context) => const CreateProjectScreen(),
        InviteTeammateScreen.routeName: (context) => const InviteTeammateScreen(),
        JoinProjectScreen.routeName: (context) => const JoinProjectScreen(),
        ProjectDetailScreen.routeName: (context) => const ProjectDetailScreen(),
        DeclareRoleScreen.routeName: (context) => const DeclareRoleScreen(),
        TeamRolesScreen.routeName: (context) => const TeamRolesScreen(),
        ConnectRepositoryScreen.routeName: (context) => const ConnectRepositoryScreen(),
        RepoStatusScreen.routeName: (context) => const RepoStatusScreen(),
        AddContributionScreen.routeName: (context) => const AddContributionScreen(),
        MyContributionsScreen.routeName: (context) => const MyContributionsScreen(),
        PendingConfirmationsScreen.routeName: (context) => const PendingConfirmationsScreen(),
        PublishSelectionScreen.routeName: (context) => const PublishSelectionScreen(),
        SplashScreen.routeName: (context) => const SplashScreen(),
      },
    );
  }
}

class AuthWrapper extends StatefulWidget {
  final StorageService? storageService;

  const AuthWrapper({super.key, this.storageService});

  @override
  State<AuthWrapper> createState() => _AuthWrapperState();
}

class _AuthWrapperState extends State<AuthWrapper> {
  late final StorageService _storageService;

  @override
  void initState() {
    super.initState();
    _storageService = widget.storageService ?? StorageService();
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    try {
      final token = await _storageService.getAccessToken();
      if (!mounted) return;

      if (token != null && token.isNotEmpty) {
        final name = await _storageService.getUserName() ?? await _storageService.getUserEmail();
        final draft = await _storageService.getContributionDraft();
        if (!mounted) return;

        if (draft.isNotEmpty && draft['projectId'] != null && draft['projectId']!.isNotEmpty) {
          Navigator.pushReplacementNamed(
            context,
            HomeScreen.routeName,
            arguments: name ?? 'User',
          );
          Navigator.pushNamed(
            context,
            MyProjectsScreen.routeName,
          );
          Navigator.pushNamed(
            context,
            ProjectDetailScreen.routeName,
            arguments: {'projectId': draft['projectId']},
          );
          Navigator.pushNamed(
            context,
            AddContributionScreen.routeName,
            arguments: {'projectId': draft['projectId']},
          );
          return;
        }

        Navigator.pushReplacementNamed(
          context,
          HomeScreen.routeName,
          arguments: name ?? 'User',
        );
      } else {
        Navigator.pushReplacementNamed(context, LoginScreen.routeName);
      }
    } catch (_) {
      if (mounted) {
        Navigator.pushReplacementNamed(context, LoginScreen.routeName);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return const SplashScreen(message: 'Verifying session...');
  }
}









