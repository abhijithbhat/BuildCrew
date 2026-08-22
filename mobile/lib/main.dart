import 'package:flutter/material.dart';

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
import 'screens/project_detail_screen.dart';
import 'screens/repo_status_screen.dart';
import 'screens/signup_screen.dart';
import 'screens/team_roles_screen.dart';
import 'services/storage_service.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  final StorageService? storageService;

  const MyApp({super.key, this.storageService});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BuildCrew',
      debugShowCheckedModeBanner: false,
      initialRoute: '/',
      routes: {
        '/': (context) => AuthWrapper(storageService: storageService),
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
    return const Scaffold(
      backgroundColor: Color(0xFF0B0F19),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.group_work_rounded,
              size: 56,
              color: Color(0xFF2563EB),
            ),
            SizedBox(height: 16),
            Text(
              'BuildCrew',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
                color: Colors.white,
                letterSpacing: 0.5,
              ),
            ),
            SizedBox(height: 24),
            SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF2563EB)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}









