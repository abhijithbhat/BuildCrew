import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/screens/add_contribution_screen.dart';
import 'package:mobile/screens/my_contributions_screen.dart';
import 'package:mobile/services/project_service.dart';
import 'package:mobile/services/storage_service.dart';

class FakeStorageService extends StorageService {
  final String? userId;
  final String? userName;

  FakeStorageService({this.userId = 'user-alex', this.userName = 'Alex Developer'});

  @override
  Future<String?> getUserId() async => userId;

  @override
  Future<String?> getUserName() async => userName;
}

class FakeMyContributionsProjectService extends ProjectService {
  List<Contribution> mockContributions = [];
  bool shouldThrow = false;
  String? lastFetchedProjectId;
  String? lastFetchedContributor;
  String? lastDeletedId;

  @override
  Future<List<Contribution>> listContributions(
    String projectId, {
    String? status,
    String? contributor,
    String? category,
  }) async {
    if (shouldThrow) {
      throw 'Failed to load personal contributions from server.';
    }
    lastFetchedProjectId = projectId;
    lastFetchedContributor = contributor;
    return mockContributions;
  }

  @override
  Future<bool> deleteContribution(String contributionId, {String? projectId}) async {
    if (shouldThrow) {
      throw 'Failed to delete contribution from server.';
    }
    lastDeletedId = contributionId;
    mockContributions.removeWhere((c) => c.id == contributionId);
    return true;
  }
}

void main() {
  late FakeMyContributionsProjectService fakeProjectService;
  late FakeStorageService fakeStorageService;

  final sampleContributions = [
    Contribution(
      id: 'contrib-1',
      contributor: 'user-alex',
      project: 'proj-123',
      title: 'feat: implement JWT token refresh flow',
      category: 'code',
      sourceType: 'github_commit',
      verificationStatus: 'source-verified',
      contributorName: 'Alex Developer',
      createdAt: DateTime.parse('2026-08-20T10:00:00Z'),
    ),
    Contribution(
      id: 'contrib-2',
      contributor: 'user-alex',
      project: 'proj-123',
      title: 'Figma Design System UI Tokens',
      category: 'design',
      description: 'Created 40+ color and typography tokens in Figma.',
      sourceType: 'manual',
      evidenceLink: 'https://figma.com/file/tokens123',
      verificationStatus: 'self-declared',
      contributorName: 'Alex Developer',
      createdAt: DateTime.parse('2026-08-21T11:00:00Z'),
    ),
    Contribution(
      id: 'contrib-3',
      contributor: 'user-alex',
      project: 'proj-123',
      title: 'Technical Architecture RFC Document',
      category: 'documentation',
      description: 'Drafted RFC for multi-endpoint mobile sync.',
      sourceType: 'manual',
      evidenceLink: 'https://storage.supabase.co/evidence/alex/rfc.pdf',
      verificationStatus: 'self-declared',
      contributorName: 'Alex Developer',
      createdAt: DateTime.parse('2026-08-21T14:00:00Z'),
    ),
  ];

  setUp(() {
    fakeProjectService = FakeMyContributionsProjectService();
    fakeStorageService = FakeStorageService();
  });

  Widget buildTestWidget({
    String? projectId,
    FakeMyContributionsProjectService? projectService,
    FakeStorageService? storageService,
  }) {
    return MaterialApp(
      routes: {
        AddContributionScreen.routeName: (context) => const Scaffold(
          body: Text('Add Contribution Screen Mock'),
        ),
      },
      home: MyContributionsScreen(
        projectId: projectId ?? 'proj-123',
        projectService: projectService ?? fakeProjectService,
        storageService: storageService ?? fakeStorageService,
      ),
    );
  }

  group('MyContributionsScreen Layout Tests', () {
    testWidgets('renders header, user subtitle, stats cards, search input, and filter chips', (tester) async {
      fakeProjectService.mockContributions = sampleContributions;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Title & Subtitle
      expect(find.text('My Contributions'), findsOneWidget);
      expect(find.text('Personal Log • Alex Developer'), findsOneWidget);

      // Stats Summary Cards
      expect(find.text('Total Logs'), findsOneWidget);
      expect(find.text('3'), findsOneWidget); // 3 total contributions
      expect(find.text('Non-Code Impact'), findsOneWidget);
      expect(find.text('2'), findsOneWidget); // 2 manual non-code

      // Search Bar
      expect(find.byKey(const Key('my_contributions_search_input')), findsOneWidget);

      // Category filter chips
      expect(find.text('All Impact'), findsOneWidget);
      expect(find.text('Code & Commits'), findsOneWidget);
      expect(find.text('UI/UX Design'), findsWidgets);
      expect(find.text('Documentation'), findsWidgets);

      // FAB & Refresh Button
      expect(find.byKey(const Key('my_contributions_add_fab')), findsOneWidget);
      expect(find.byKey(const Key('my_contributions_refresh_btn')), findsOneWidget);
    });

    testWidgets('renders empty state when user has zero contributions', (tester) async {
      fakeProjectService.mockContributions = [];

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('No contributions logged yet'), findsOneWidget);
      expect(find.byKey(const Key('my_contributions_empty_add_btn')), findsOneWidget);
    });
  });

  group('MyContributionsScreen Wiring & Real Data Tests', () {
    testWidgets('fetches and displays contributions side-by-side (GitHub commit + manual non-code)', (tester) async {
      fakeProjectService.mockContributions = sampleContributions;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Verify backend service was queried with project ID and scoped to current user
      expect(fakeProjectService.lastFetchedProjectId, 'proj-123');
      expect(fakeProjectService.lastFetchedContributor, 'user-alex');

      // Check GitHub commit card rendered with Source Verified badge
      expect(find.text('feat: implement JWT token refresh flow'), findsOneWidget);
      expect(find.text('Git Commit'), findsOneWidget);
      expect(find.text('Source Verified'), findsOneWidget);

      // Check Figma Design Card rendered with Self Declared badge and evidence link
      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);
      expect(find.text('UI/UX Design'), findsWidgets);
      expect(find.text('Self Declared'), findsWidgets);
      expect(find.text('https://figma.com/file/tokens123'), findsOneWidget);

      // Scroll to Documentation Card and verify
      await tester.scrollUntilVisible(
        find.text('Technical Architecture RFC Document'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();

      expect(find.text('Technical Architecture RFC Document'), findsOneWidget);
      expect(find.text('https://storage.supabase.co/evidence/alex/rfc.pdf'), findsOneWidget);
    });

    testWidgets('filters contributions dynamically when user types in search field', (tester) async {
      fakeProjectService.mockContributions = sampleContributions;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Type 'Figma' in search bar
      await tester.enterText(
        find.byKey(const Key('my_contributions_search_input')),
        'Figma',
      );
      await tester.pumpAndSettle();

      // Only Figma card visible
      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);
      expect(find.text('feat: implement JWT token refresh flow'), findsNothing);
      expect(find.text('Technical Architecture RFC Document'), findsNothing);
    });

    testWidgets('filters contributions when tapping category filter chips', (tester) async {
      fakeProjectService.mockContributions = sampleContributions;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Tap 'UI/UX Design' chip
      await tester.tap(find.text('UI/UX Design').first);
      await tester.pumpAndSettle();

      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);
      expect(find.text('feat: implement JWT token refresh flow'), findsNothing);
      expect(find.text('Technical Architecture RFC Document'), findsNothing);
    });

    testWidgets('displays error banner and handles retry on network failure', (tester) async {
      fakeProjectService.shouldThrow = true;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Error banner visible
      expect(find.textContaining('Failed to load personal contributions'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      // Fix error and tap retry
      fakeProjectService.shouldThrow = false;
      fakeProjectService.mockContributions = sampleContributions;

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();

      // Successfully loaded
      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);
    });

    testWidgets('tapping FAB opens AddContributionScreen', (tester) async {
      fakeProjectService.mockContributions = sampleContributions;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('my_contributions_add_fab')));
      await tester.pumpAndSettle();

      expect(find.text('Add Contribution Screen Mock'), findsOneWidget);
    });

    testWidgets('tapping stat cards toggles filters and mutually exclusive selection cleanly', (tester) async {
      fakeProjectService.mockContributions = sampleContributions;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // All contributions visible initially
      expect(find.text('feat: implement JWT token refresh flow'), findsOneWidget);
      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);

      // Tap Non-Code Impact stat card
      await tester.tap(find.text('Non-Code Impact'));
      await tester.pumpAndSettle();

      // Code commit is hidden, manual non-code deliverable is visible
      expect(find.text('feat: implement JWT token refresh flow'), findsNothing);
      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);

      // Tap Verified / Declared stat card -> cycles to source-verified
      await tester.tap(find.text('Verified / Declared'));
      await tester.pumpAndSettle();

      // Only source-verified code commit is visible, manual non-code is hidden
      expect(find.text('feat: implement JWT token refresh flow'), findsOneWidget);
      expect(find.text('Figma Design System UI Tokens'), findsNothing);

      // Tap Total Logs stat card -> resets to all
      await tester.tap(find.text('Total Logs'));
      await tester.pumpAndSettle();

      expect(find.text('feat: implement JWT token refresh flow'), findsOneWidget);
      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);
    });

    testWidgets('long pressing a manual contribution prompts confirmation and deletes it', (tester) async {
      fakeProjectService.mockContributions = List.from(sampleContributions);

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Figma Design System UI Tokens'), findsOneWidget);

      // Long press Figma Design card
      await tester.longPress(find.text('Figma Design System UI Tokens'));
      await tester.pumpAndSettle();

      // Verify deletion confirmation dialog is shown
      expect(find.text('Delete Impact Log?'), findsOneWidget);
      expect(find.text('Delete Log'), findsOneWidget);

      // Tap 'Delete Log'
      await tester.tap(find.text('Delete Log'));
      await tester.pumpAndSettle();

      // Verify delete was triggered
      expect(fakeProjectService.lastDeletedId, 'contrib-2');
      expect(find.text('Impact log deleted successfully.'), findsOneWidget);
      expect(find.text('Figma Design System UI Tokens'), findsNothing);
    });
  });
}
