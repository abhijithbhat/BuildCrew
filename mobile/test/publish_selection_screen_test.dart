import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/screens/publish_selection_screen.dart';
import 'package:mobile/services/project_service.dart';

import 'package:mobile/services/storage_service.dart';

class MockPublishProjectService extends ProjectService {
  final List<String> publishedIds = [];
  final List<String> unpublishedIds = [];
  bool shouldFailPublish = false;
  bool shouldFailUnpublish = false;
  List<Contribution> mockContributions = [];

  @override
  Future<List<Contribution>> listContributions(
    String projectId, {
    String? status,
    String? contributor,
    String? category,
  }) async {
    return mockContributions;
  }

  @override
  Future<Contribution> publishContribution(String contributionId) async {
    if (shouldFailPublish) {
      throw 'Only confirmed contributions can be published to your passport.';
    }
    publishedIds.add(contributionId);
    return Contribution(
      id: contributionId,
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Published Item',
      verificationStatus: 'confirmed',
      visibility: 'public',
    );
  }

  @override
  Future<Contribution> unpublishContribution(String contributionId) async {
    if (shouldFailUnpublish) {
      throw 'Failed to unpublish contribution: server error.';
    }
    unpublishedIds.add(contributionId);
    return Contribution(
      id: contributionId,
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Unpublished Item',
      verificationStatus: 'confirmed',
      visibility: 'private',
    );
  }
}

class MockStorageService extends StorageService {
  @override
  Future<String?> getUserId() async => 'user-1';
  @override
  Future<String?> getAccessToken() async => 'mock-jwt-token';
}

void main() {
  final sampleConfirmedContributions = [
    Contribution(
      id: 'c-1',
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Solidity Smart Contract Implementation',
      category: 'code',
      description: 'ERC-20 token smart contracts and test suite',
      verificationStatus: 'confirmed',
      visibility: 'public',
      dateRange: '2026-08-01 - 2026-08-15',
    ),
    Contribution(
      id: 'c-2',
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Design System & UI Components',
      category: 'design',
      description: 'Figma components and design tokens',
      verificationStatus: 'peer-confirmed',
      visibility: 'private',
      dateRange: '2026-08-16 - 2026-08-20',
    ),
    Contribution(
      id: 'c-3',
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Unconfirmed Draft Feature',
      category: 'code',
      description: 'Draft not yet peer-reviewed',
      verificationStatus: 'pending',
      visibility: 'private',
    ),
    Contribution(
      id: 'c-4',
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Disputed Deliverable',
      category: 'code',
      description: 'Deliverable under review',
      verificationStatus: 'needs-review',
      disputeState: 'disputed',
      visibility: 'public',
    ),
  ];

  Widget createTestWidget({
    List<Contribution>? contributions,
    ProjectService? projectService,
    StorageService? storageService,
    ValueChanged<Set<String>>? onSelectionChanged,
    VoidCallback? onSave,
  }) {
    return MaterialApp(
      home: PublishSelectionScreen(
        projectId: 'proj-1',
        projectName: 'Alpha Engine',
        initialContributions: contributions,
        projectService: projectService ?? MockPublishProjectService(),
        storageService: storageService ?? MockStorageService(),
        onSelectionChanged: onSelectionChanged,
        onSave: onSave,
      ),
    );
  }

  testWidgets('renders screen title, header banner and summary stats',
      (tester) async {
    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
    ));
    await tester.pumpAndSettle();

    expect(find.text('Select What to Publish'), findsOneWidget);
    expect(find.text('Passport Visibility • Alpha Engine'), findsOneWidget);
    expect(find.text('Public Passport Visibility'), findsOneWidget);
    expect(find.textContaining('1 Published'), findsOneWidget);
    expect(find.textContaining('1 Private'), findsOneWidget);
    expect(find.textContaining('2 Confirmed'), findsOneWidget);
  });

  testWidgets(
      'displays ONLY confirmed deliverables with checkboxes (excludes unconfirmed/disputed)',
      (tester) async {
    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
    ));
    await tester.pumpAndSettle();

    // Confirmed items must appear
    expect(find.text('Solidity Smart Contract Implementation'), findsOneWidget);
    expect(find.text('Design System & UI Components'), findsOneWidget);

    // Unconfirmed / disputed must NOT appear
    expect(find.text('Unconfirmed Draft Feature'), findsNothing);
    expect(find.text('Disputed Deliverable'), findsNothing);

    // Checkboxes exist for c-1 and c-2
    expect(find.byKey(const Key('publish_checkbox_c-1')), findsOneWidget);
    expect(find.byKey(const Key('publish_checkbox_c-2')), findsOneWidget);
  });

  testWidgets(
      'checking an unchecked box optimistically selects it and calls publishContribution',
      (tester) async {
    final mockService = MockPublishProjectService();
    Set<String>? currentSelection;

    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
      projectService: mockService,
      onSelectionChanged: (set) => currentSelection = set,
    ));
    await tester.pumpAndSettle();

    // Initially c-2 is private (unselected), c-1 is public (selected)
    expect(find.text('1 of 2 selected'), findsOneWidget);

    // Tap c-2 checkbox to publish
    await tester.tap(find.byKey(const Key('publish_checkbox_c-2')));
    await tester.pumpAndSettle();

    // Verify service was called with c-2
    expect(mockService.publishedIds, contains('c-2'));
    expect(find.text('2 of 2 selected'), findsOneWidget);
    expect(currentSelection?.contains('c-2'), isTrue);
  });

  testWidgets(
      'unchecking a checked box optimistically unselects it and calls unpublishContribution',
      (tester) async {
    final mockService = MockPublishProjectService();
    Set<String>? currentSelection;

    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
      projectService: mockService,
      onSelectionChanged: (set) => currentSelection = set,
    ));
    await tester.pumpAndSettle();

    // Initially c-1 is public (selected)
    expect(find.text('1 of 2 selected'), findsOneWidget);

    // Tap c-1 card to unpublish
    await tester.tap(find.text('Solidity Smart Contract Implementation'));
    await tester.pumpAndSettle();

    // Verify service was called with c-1
    expect(mockService.unpublishedIds, contains('c-1'));
    expect(find.text('0 of 2 selected'), findsOneWidget);
    expect(currentSelection?.contains('c-1'), isFalse);
  });

  testWidgets(
      'rollback on publish error: reverts checkbox to unchecked and displays error snackbar',
      (tester) async {
    final mockService = MockPublishProjectService()..shouldFailPublish = true;

    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
      projectService: mockService,
    ));
    await tester.pumpAndSettle();

    // Tap c-2 to publish
    await tester.tap(find.byKey(const Key('publish_checkbox_c-2')));
    await tester.pumpAndSettle();

    // Checkbox must revert back to unchecked (1 of 2 selected)
    expect(find.text('1 of 2 selected'), findsOneWidget);

    // Red error snackbar displayed with backend guard detail
    expect(find.byType(SnackBar), findsOneWidget);
    expect(
      find.textContaining('Only confirmed contributions can be published to your passport.'),
      findsOneWidget,
    );
  });

  testWidgets(
      'rollback on unpublish error: reverts checkbox to checked and displays error snackbar',
      (tester) async {
    final mockService = MockPublishProjectService()..shouldFailUnpublish = true;

    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
      projectService: mockService,
    ));
    await tester.pumpAndSettle();

    // Tap c-1 to unpublish
    await tester.tap(find.byKey(const Key('publish_checkbox_c-1')));
    await tester.pumpAndSettle();

    // Checkbox must revert back to checked (1 of 2 selected)
    expect(find.text('1 of 2 selected'), findsOneWidget);
    expect(find.byType(SnackBar), findsOneWidget);
    expect(
      find.textContaining('Failed to unpublish contribution'),
      findsOneWidget,
    );
  });

  testWidgets(
      'fetches confirmed contributions automatically from ProjectService.listContributions when initialContributions is null',
      (tester) async {
    final mockService = MockPublishProjectService()
      ..mockContributions = sampleConfirmedContributions;

    await tester.pumpWidget(createTestWidget(
      contributions: null, // trigger auto fetch
      projectService: mockService,
    ));
    await tester.pumpAndSettle();

    expect(find.text('Solidity Smart Contract Implementation'), findsOneWidget);
    expect(find.text('Design System & UI Components'), findsOneWidget);
    expect(find.text('1 of 2 selected'), findsOneWidget);
  });

  testWidgets('Select All calls publish for all unselected items', (tester) async {
    final mockService = MockPublishProjectService();

    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
      projectService: mockService,
    ));
    await tester.pumpAndSettle();

    // Tap Select All
    await tester.tap(find.byKey(const Key('publish_toggle_all_btn')));
    await tester.pumpAndSettle();

    expect(mockService.publishedIds, contains('c-2'));
    expect(find.text('2 of 2 selected'), findsOneWidget);
  });

  testWidgets('Deselect All calls unpublish for all selected items',
      (tester) async {
    final mockService = MockPublishProjectService();

    // Start with all selected
    final allSelected = [
      Contribution(
        id: 'c-1',
        contributor: 'user-1',
        project: 'proj-1',
        title: 'Solidity Smart Contract Implementation',
        verificationStatus: 'confirmed',
        visibility: 'public',
      ),
      Contribution(
        id: 'c-2',
        contributor: 'user-1',
        project: 'proj-1',
        title: 'Design System & UI Components',
        verificationStatus: 'peer-confirmed',
        visibility: 'public',
      ),
    ];

    await tester.pumpWidget(createTestWidget(
      contributions: allSelected,
      projectService: mockService,
    ));
    await tester.pumpAndSettle();

    expect(find.text('Deselect All'), findsOneWidget);

    // Tap Deselect All
    await tester.tap(find.byKey(const Key('publish_toggle_all_btn')));
    await tester.pumpAndSettle();

    expect(mockService.unpublishedIds, contains('c-1'));
    expect(mockService.unpublishedIds, contains('c-2'));
    expect(find.text('0 of 2 selected'), findsOneWidget);
  });

  testWidgets('search query filters confirmed contributions', (tester) async {
    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
    ));
    await tester.pumpAndSettle();

    await tester.enterText(
        find.byKey(const Key('publish_search_field')), 'Solidity');
    await tester.pumpAndSettle();

    expect(find.text('Solidity Smart Contract Implementation'), findsOneWidget);
    expect(find.text('Design System & UI Components'), findsNothing);

    // Clear search
    await tester.enterText(
        find.byKey(const Key('publish_search_field')), '');
    await tester.pumpAndSettle();

    expect(find.text('Solidity Smart Contract Implementation'), findsOneWidget);
    expect(find.text('Design System & UI Components'), findsOneWidget);
  });

  testWidgets('renders empty state when no confirmed contributions exist',
      (tester) async {
    await tester.pumpWidget(createTestWidget(contributions: []));
    await tester.pumpAndSettle();

    expect(find.text('No Confirmed Deliverables'), findsOneWidget);
    expect(find.text('0 of 0 selected'), findsOneWidget);
  });

  testWidgets('tapping Save Passport calls onSave callback and shows snackbar',
      (tester) async {
    bool onSaveCalled = false;
    await tester.pumpWidget(createTestWidget(
      contributions: sampleConfirmedContributions,
      onSave: () => onSaveCalled = true,
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('publish_save_button')));
    await tester.pumpAndSettle();

    expect(onSaveCalled, isTrue);
    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.textContaining('Updated passport: 1 deliverables published.'),
        findsOneWidget);
  });
}
