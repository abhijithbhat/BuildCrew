import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/screens/splash_screen.dart';

void main() {
  Widget app(
    Future<String> Function() resolver, {
    Future<void> Function(String route)? before,
    Duration duration = const Duration(milliseconds: 300),
  }) {
    return MaterialApp(
      routes: <String, WidgetBuilder>{
        '/login': (_) => const Scaffold(body: Text('LOGIN PAGE')),
        '/home': (_) => const Scaffold(body: Text('HOME PAGE')),
      },
      home: SplashScreen(resolveRoute: resolver, beforeNavigate: before, duration: duration),
    );
  }

  testWidgets('routes to the resolved destination when the animation ends', (tester) async {
    await tester.pumpWidget(app(() async => '/home'));
    expect(find.byType(CustomPaint), findsWidgets);
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pumpAndSettle();
    expect(find.text('HOME PAGE'), findsOneWidget);
  });

  testWidgets('falls back to /login when the resolver throws', (tester) async {
    await tester.pumpWidget(app(() async => throw StateError('boom')));
    await tester.pump(const Duration(milliseconds: 350));
    await tester.pumpAndSettle();
    expect(find.text('LOGIN PAGE'), findsOneWidget);
  });

  testWidgets('waits for beforeNavigate (prefetched data) before leaving the splash', (tester) async {
    final Completer<void> gate = Completer<void>();
    await tester.pumpWidget(app(() async => '/home', before: (String route) => gate.future));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pump();
    expect(find.text('HOME PAGE'), findsNothing);

    gate.complete();
    await tester.pumpAndSettle();
    expect(find.text('HOME PAGE'), findsOneWidget);
  });

  testWidgets('uses a short animation when the system asks to reduce motion', (tester) async {
    tester.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(disableAnimations: true);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);

    await tester.pumpWidget(app(() async => '/home', duration: const Duration(seconds: 5)));
    await tester.pump(const Duration(milliseconds: 450));
    await tester.pumpAndSettle();
    expect(find.text('HOME PAGE'), findsOneWidget);
  });
}
