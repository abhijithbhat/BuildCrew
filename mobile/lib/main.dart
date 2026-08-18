import 'package:flutter/material.dart';

import 'screens/create_project_screen.dart';
import 'screens/declare_role_screen.dart';
import 'screens/forgot_password_screen.dart';
import 'screens/home_screen.dart';
import 'screens/invite_teammate_screen.dart';
import 'screens/join_project_screen.dart';
import 'screens/login_screen.dart';
import 'screens/my_projects_screen.dart';
import 'screens/otp_screen.dart';
import 'screens/project_detail_screen.dart';
import 'screens/signup_screen.dart';
import 'screens/team_roles_screen.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BuildCrew',
      debugShowCheckedModeBanner: false,
      initialRoute: LoginScreen.routeName,
      routes: {
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
      },
    );
  }
}






