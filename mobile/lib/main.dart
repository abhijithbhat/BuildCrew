import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
import 'screens/settings_screen.dart';
import 'screens/signup_screen.dart';
import 'screens/splash_screen.dart';
import 'screens/team_roles_screen.dart';
import 'services/api_client.dart';
import 'services/auth_service.dart';
import 'services/dashboard_repository.dart';
import 'services/session_router.dart';
import 'services/storage_service.dart';
import 'theme/app_colors.dart';

String get effectiveSupabaseUrl => ApiClient.supabaseUrl;
String get effectiveSupabaseKey => ApiClient.supabaseAnonKey;

Future<void>? supabaseInitFuture;
final ValueNotifier<bool> supabaseReadyNotifier = ValueNotifier<bool>(false);

Future<void> ensureSupabase() {
  return supabaseInitFuture ??= Supabase.initialize(
    url: ApiClient.supabaseUrl,
    // ignore: deprecated_member_use
    anonKey: ApiClient.supabaseAnonKey,
    authOptions: const FlutterAuthClientOptions(
      authFlowType: AuthFlowType.pkce,
    ),
  ).then((_) {
    supabaseReadyNotifier.value = true;
  }).catchError((Object e) {
    debugPrint('Supabase init error: $e');
    supabaseReadyNotifier.value = true;
  });
}

Future<String>? routeResolutionFuture;
Future<String> resolveAndPrefetch() {
  return routeResolutionFuture ??= () async {
    await ensureSupabase();
    final String route = await resolveStartRoute();
    if (route == '/home') {
      unawaited(DashboardRepository.instance.prefetch());
    }
    return route;
  }();
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // Validate API base URL in release mode at startup
  ApiClient.validateStartupConfig();

  runApp(const MyApp(
    initialRoute: '/login',
    showSplash: true,
    resolveSplashRoute: resolveAndPrefetch,
  ));

  WidgetsBinding.instance.addPostFrameCallback((_) {
    unawaited(SystemChrome.setPreferredOrientations([
      DeviceOrientation.portraitUp,
      DeviceOrientation.portraitDown,
    ]));
  });
}

class MyApp extends StatefulWidget {
  final StorageService? storageService;
  final AppLinks? appLinks;
  final String initialRoute;
  final bool showSplash;
  final Future<void>? supabaseReady;
  final SplashRouteResolver? resolveSplashRoute;

  const MyApp({
    super.key,
    this.storageService,
    this.appLinks,
    this.initialRoute = '/login',
    this.showSplash = false,
    this.supabaseReady,
    this.resolveSplashRoute,
  });

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  late final AppLinks _appLinks;
  StreamSubscription<Uri>? _linkSubscription;
  static String? _lastHandledUri;

  @override
  void initState() {
    super.initState();
    _appLinks = widget.appLinks ?? AppLinks();
    _initDeepLinks();
    if (widget.supabaseReady != null) {
      widget.supabaseReady!.whenComplete(() {
        if (mounted) _setupAuthListener();
      });
    } else if (supabaseInitFuture != null) {
      supabaseInitFuture!.whenComplete(() {
        if (mounted) _setupAuthListener();
      });
    } else if (supabaseReadyNotifier.value) {
      _setupAuthListener();
    } else {
      void onReady() {
        if (supabaseReadyNotifier.value) {
          supabaseReadyNotifier.removeListener(onReady);
          if (mounted) _setupAuthListener();
        }
      }
      supabaseReadyNotifier.addListener(onReady);
    }
  }

  void _setupAuthListener() {
    // Auth state listener setup hook
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
        final uriStr = initialUri.toString();
        if (_lastHandledUri != uriStr) {
          _lastHandledUri = uriStr;
          await _handleIncomingUri(initialUri);
        } else {
          debugPrint('Ignoring already-handled initial link on restart: $uriStr');
        }
      }
    } catch (e) {
      debugPrint('AppLinks initialization error: $e');
    }
  }

  Future<void> _handleIncomingUri(Uri uri) async {
    debugPrint('Received deep link: $uri');
    try {
      if (widget.supabaseReady != null) {
        try {
          await widget.supabaseReady;
        } catch (_) {}
      } else if (supabaseInitFuture != null) {
        try {
          await supabaseInitFuture;
        } catch (_) {}
      }
      // Custom scheme: com.abhijithbhat.buildcrew, host: login-callback
      if (uri.scheme == 'com.abhijithbhat.buildcrew' &&
          (uri.host == 'login-callback' || uri.path.contains('login-callback'))) {

        // ONLY trigger cancellation/failure if the provider explicitly returned an error!
        final errorParam = uri.queryParameters['error'] ??
            uri.queryParameters['error_description'];
        if (errorParam != null && errorParam.isNotEmpty) {
          debugPrint('OAuth callback returned explicit error: $errorParam');
          _notifyAuthFailed('Sign-in was cancelled');
          return;
        }

        // Check if session is already active (e.g. exchanged by Supabase internal handler)
        Session? session = Supabase.instance.client.auth.currentSession;
        if (session == null) {
          try {
            final response =
                await Supabase.instance.client.auth.getSessionFromUrl(uri);
            session = response.session;
          } catch (e) {
            debugPrint('getSessionFromUrl did not exchange code: $e');
            session = Supabase.instance.client.auth.currentSession;
          }
        }

        // If session is valid, save credentials and route to Home safely
        if (session != null) {
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

          if (!AuthService.isNavigatedToHome) {
            AuthService.setNavigatedToHome(true);
            ApiClient.navigatorKey.currentState?.pushNamedAndRemoveUntil(
              HomeScreen.routeName,
              (route) => false,
              arguments: name,
            );
          }
        }
      }
    } catch (e) {
      debugPrint('Deep link handling error: $e');
    }
  }

  void _notifyAuthFailed([String message = 'Sign-in was cancelled or failed']) {
    AuthService.setNavigatedToHome(false);
    ApiClient.navigatorKey.currentState?.pushNamedAndRemoveUntil(
      LoginScreen.routeName,
      (route) => false,
    );
    ApiClient.scaffoldMessengerKey.currentState?.showSnackBar(
      SnackBar(
        content: Text(
          message,
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
        ),
        backgroundColor: Colors.red.shade700,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
        ),
        duration: const Duration(seconds: 4),
      ),
    );
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
      scaffoldMessengerKey: ApiClient.scaffoldMessengerKey,
      title: 'BuildCrew',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.emeraldInk,
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: AppColors.champagne,
        chipTheme: ChipThemeData(
          selectedColor: AppColors.emeraldInk,
          checkmarkColor: AppColors.champagne,
          backgroundColor: Colors.white,
          labelStyle: const TextStyle(color: AppColors.bodyText),
          secondaryLabelStyle: const TextStyle(color: AppColors.champagne),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: const BorderSide(color: AppColors.inputBorder),
          ),
        ),
        switchTheme: SwitchThemeData(
          thumbColor: WidgetStateProperty.resolveWith((states) =>
              states.contains(WidgetState.selected)
                  ? AppColors.emeraldInk
                  : null),
          trackColor: WidgetStateProperty.resolveWith((states) =>
              states.contains(WidgetState.selected)
                  ? AppColors.emeraldInk.withValues(alpha: 0.5)
                  : null),
        ),
        checkboxTheme: CheckboxThemeData(
          fillColor: WidgetStateProperty.resolveWith((states) =>
              states.contains(WidgetState.selected)
                  ? AppColors.emeraldInk
                  : null),
          checkColor: WidgetStateProperty.all(AppColors.champagne),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.emeraldInk,
            foregroundColor: AppColors.champagne,
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.emeraldInk,
            side: const BorderSide(color: AppColors.inputBorder),
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            foregroundColor: AppColors.emeraldInk,
          ),
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: AppColors.emeraldInk,
          foregroundColor: AppColors.champagne,
        ),
        progressIndicatorTheme: const ProgressIndicatorThemeData(
          color: AppColors.emeraldInk,
        ),
      ),
      initialRoute:
          widget.showSplash ? SplashScreen.routeName : widget.initialRoute,
      builder: (context, child) => ColoredBox(
        color: AppColors.champagne,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: child,
          ),
        ),
      ),
      routes: {
        SplashScreen.routeName: (context) => SplashScreen(
              resolveRoute: widget.resolveSplashRoute ?? resolveStartRoute,
            ),
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
        SettingsScreen.routeName: (context) => const SettingsScreen(),
      },
    );
  }
}










