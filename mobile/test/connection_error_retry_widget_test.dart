import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/widgets/connection_error_retry_widget.dart';

void main() {
  testWidgets('ConnectionErrorRetryWidget full view renders title, message and fires onRetry', (WidgetTester tester) async {
    bool retryTapped = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConnectionErrorRetryWidget(
            title: "Couldn't connect to server",
            message: "Can't reach the server. Please check your network and try again.",
            onRetry: () {
              retryTapped = true;
            },
          ),
        ),
      ),
    );

    expect(find.text("Couldn't connect to server"), findsOneWidget);
    expect(find.text("Can't reach the server. Please check your network and try again."), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);

    await tester.tap(find.text('Retry'));
    expect(retryTapped, isTrue);
  });

  testWidgets('ConnectionErrorRetryWidget compact mode renders banner and fires onRetry', (WidgetTester tester) async {
    bool retryTapped = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ConnectionErrorRetryWidget(
            message: "Cannot connect to server. Check your connection.",
            isCompact: true,
            onRetry: () {
              retryTapped = true;
            },
          ),
        ),
      ),
    );

    expect(find.text("Cannot connect to server. Check your connection."), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);

    await tester.tap(find.text('Retry'));
    expect(retryTapped, isTrue);
  });
}
