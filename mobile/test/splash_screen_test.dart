import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/screens/splash_screen.dart';

void main() {
  group('SplashScreen Widget Tests', () {
    testWidgets('renders brand title, tagline, logo emblem, and progress indicator',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: SplashScreen(),
        ),
      );

      // Verify app title and tagline
      expect(find.text('BuildCrew'), findsOneWidget);
      expect(find.text('AUTONOMOUS WORKSPACE'), findsOneWidget);

      // Verify groups logo icon
      expect(find.byIcon(Icons.groups_rounded), findsOneWidget);

      // Verify default loading message and indicator
      expect(find.text('Initializing workspace...'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      // Verify trust footer
      expect(
        find.text('Peer-Verified Deliverables • Cryptographic Trust'),
        findsOneWidget,
      );
      expect(find.text('v1.0.0'), findsOneWidget);
    });

    testWidgets('displays custom status message when provided',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: SplashScreen(message: 'Verifying session...'),
        ),
      );

      expect(find.text('Verifying session...'), findsOneWidget);
      expect(find.text('Initializing workspace...'), findsNothing);
    });
  });
}
