import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';
import 'package:mobile/services/storage_service.dart';

class FakeStorageService extends StorageService {
  @override
  Future<String?> getAccessToken() async => null;
  @override
  Future<Map<String, String?>> getContributionDraft() async => {};
}

void main() {
  testWidgets('App smoke test - renders initial screen', (WidgetTester tester) async {
    await tester.pumpWidget(MyApp(storageService: FakeStorageService()));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.text('Login'), findsWidgets);
  });
}

