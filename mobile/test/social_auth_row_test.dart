import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/widgets/social_auth_row.dart';

void main() {
  Widget host({VoidCallback? onGoogle, VoidCallback? onGitHub, bool googleLoading = false}) {
    return MaterialApp(
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: SocialAuthRow(
            onGoogle: onGoogle,
            onGitHub: onGitHub,
            isGoogleLoading: googleLoading,
          ),
        ),
      ),
    );
  }

  testWidgets('Google and GitHub sit side by side with equal width and 48dp+ height', (tester) async {
    await tester.pumpWidget(host(onGoogle: () {}, onGitHub: () {}));
    final Rect g = tester.getRect(find.byKey(const Key('social_google_btn')));
    final Rect h = tester.getRect(find.byKey(const Key('social_github_btn')));
    expect((g.width - h.width).abs(), lessThan(0.5));
    expect((g.top - h.top).abs(), lessThan(0.5));
    expect(g.height, greaterThanOrEqualTo(48));
    expect(find.text('Google'), findsOneWidget);
    expect(find.text('GitHub'), findsOneWidget);
  });

  testWidgets('taps reach the right callbacks', (tester) async {
    int google = 0;
    int github = 0;
    await tester.pumpWidget(host(onGoogle: () => google++, onGitHub: () => github++));
    await tester.tap(find.byKey(const Key('social_google_btn')));
    await tester.tap(find.byKey(const Key('social_github_btn')));
    expect(google, 1);
    expect(github, 1);
  });

  testWidgets('a loading button shows a spinner and ignores taps', (tester) async {
    int google = 0;
    await tester.pumpWidget(host(onGoogle: () => google++, onGitHub: null, googleLoading: true));
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    await tester.tap(find.byKey(const Key('social_google_btn')));
    expect(google, 0);
  });
}
