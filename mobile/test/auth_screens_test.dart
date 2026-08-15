import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/screens/forgot_password_screen.dart';
import 'package:mobile/screens/home_screen.dart';
import 'package:mobile/screens/login_screen.dart';
import 'package:mobile/screens/otp_screen.dart';
import 'package:mobile/screens/signup_screen.dart';

void main() {
  group('LoginScreen Tests', () {
    testWidgets('renders all login elements, fields, and action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          routes: {
            LoginScreen.routeName: (context) => const LoginScreen(),
            SignupScreen.routeName: (context) => const SignupScreen(),
            '/forgot-password': (context) => const ForgotPasswordScreen(),
          },
          initialRoute: LoginScreen.routeName,
        ),
      );

      expect(find.text('Login'), findsWidgets);
      expect(find.text('Welcome Back'), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(2)); // Email & Password
      expect(find.text('Email'), findsOneWidget);
      expect(find.text('Password'), findsOneWidget);
      expect(find.text('Forgot Password?'), findsOneWidget);
      expect(find.text("Don't have an account?"), findsOneWidget);
      expect(find.widgetWithText(TextButton, 'Sign Up'), findsOneWidget);
      expect(find.widgetWithText(ElevatedButton, 'Login'), findsOneWidget);
    });

    testWidgets('validates required fields only upon submit button tap', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: LoginScreen(),
        ),
      );

      // Typing before tapping button should NOT trigger validation error
      await tester.enterText(find.byType(TextFormField).first, 'invalid-email');
      await tester.pump();
      expect(find.text('Please enter a valid email address'), findsNothing);

      // Submit with invalid email and empty password
      await tester.tap(find.widgetWithText(ElevatedButton, 'Login'));
      await tester.pumpAndSettle();

      expect(find.text('Please enter a valid email address'), findsOneWidget);
      expect(find.text('Password is required'), findsOneWidget);
    });

    testWidgets('toggles password visibility icon', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: LoginScreen(),
        ),
      );

      expect(find.byIcon(Icons.visibility), findsOneWidget);
      await tester.tap(find.byIcon(Icons.visibility));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.visibility_off), findsOneWidget);
    });

    testWidgets('navigates to signup and forgot password screens', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          routes: {
            LoginScreen.routeName: (context) => const LoginScreen(),
            SignupScreen.routeName: (context) => const SignupScreen(),
            '/forgot-password': (context) => const ForgotPasswordScreen(),
          },
          initialRoute: LoginScreen.routeName,
        ),
      );

      // Tap Forgot Password
      final forgotBtn = find.text('Forgot Password?');
      await tester.ensureVisible(forgotBtn);
      await tester.tap(forgotBtn);
      await tester.pumpAndSettle();
      expect(find.text('Forgot Password'), findsWidgets);

      // Go back to login
      await tester.pageBack();
      await tester.pumpAndSettle();

      // Tap Sign Up button
      final signupBtn = find.widgetWithText(TextButton, 'Sign Up');
      await tester.ensureVisible(signupBtn);
      await tester.tap(signupBtn);
      await tester.pumpAndSettle();
      expect(find.text('Create Account'), findsOneWidget);
    });
  });

  group('SignupScreen Tests', () {
    testWidgets('renders all signup elements and validates inputs', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: SignupScreen(),
        ),
      );

      expect(find.text('Create Account'), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(3)); // Name, Email, Password
      expect(find.text('Full Name'), findsOneWidget);
      expect(find.text('Email'), findsOneWidget);
      expect(find.text('Password'), findsOneWidget);

      // Tap submit with empty form
      await tester.tap(find.byType(ElevatedButton));
      await tester.pumpAndSettle();

      expect(find.text('Full name is required'), findsOneWidget);
      expect(find.text('Email is required'), findsOneWidget);
      expect(find.text('Password is required'), findsOneWidget);
    });
  });

  group('OtpScreen Tests', () {
    testWidgets('renders OTP verification header and widgets', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: OtpScreen(),
        ),
      );

      expect(find.text('Email Verification'), findsOneWidget);
      expect(find.text('Verify Your Email'), findsOneWidget);
      expect(find.widgetWithText(ElevatedButton, 'Verify Code'), findsOneWidget);
      expect(find.byType(TextField), findsNWidgets(6)); // 6-digit boxes
    });
  });

  group('ForgotPasswordScreen Tests', () {
    testWidgets('renders step 1 request OTP form and validates email', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: ForgotPasswordScreen(),
        ),
      );

      expect(find.text('Forgot Password'), findsWidgets);
      expect(find.text('Reset Your Password'), findsOneWidget);
      expect(find.byType(TextFormField), findsOneWidget); // Email field
      expect(find.widgetWithText(ElevatedButton, 'Send Reset Code'), findsOneWidget);

      // Tap submit with empty email
      await tester.tap(find.widgetWithText(ElevatedButton, 'Send Reset Code'));
      await tester.pumpAndSettle();

      expect(find.text('Email is required'), findsOneWidget);
    });
  });

  group('HomeScreen Tests', () {
    testWidgets('renders greeting, health check button, and navigation actions', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: HomeScreen(userName: 'Alice Developer'),
        ),
      );

      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Welcome, Alice Developer'), findsOneWidget);
      expect(find.text('Check Backend Health'), findsOneWidget);
      expect(find.text('My Projects'), findsOneWidget);
      expect(find.text('Join Project with Code'), findsOneWidget);
      expect(find.text('Create New Project'), findsOneWidget);
      expect(find.text('Logout'), findsOneWidget);
    });
  });
}
