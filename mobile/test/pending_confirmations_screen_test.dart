import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/screens/pending_confirmations_screen.dart';
import 'package:mobile/services/project_service.dart';

class FakePendingConfirmationsProjectService extends ProjectService {
  List<ConfirmationRequest> mockRequests = [];
  bool shouldThrow = false;
  String? lastConfirmedId;
  String? lastDisputedId;

  @override
  Future<List<ConfirmationRequest>> getPendingConfirmations() async {
    if (shouldThrow) {
      throw 'Failed to load pending confirmations from server.';
    }
    return mockRequests;
  }

  @override
  Future<Contribution> confirmContribution(String contributionId) async {
    if (shouldThrow) {
      throw 'Failed to confirm contribution.';
    }
    lastConfirmedId = contributionId;
    mockRequests.removeWhere((r) => r.contributionId == contributionId);
    return Contribution(
      id: contributionId,
      contributor: 'user-teammate',
      project: 'proj-123',
      title: 'Confirmed Deliverable',
      verificationStatus: 'peer-confirmed',
      disputeState: 'none',
      createdAt: DateTime.now(),
    );
  }

  @override
  Future<Contribution> disputeContribution(String contributionId) async {
    if (shouldThrow) {
      throw 'Failed to dispute contribution.';
    }
    lastDisputedId = contributionId;
    mockRequests.removeWhere((r) => r.contributionId == contributionId);
    return Contribution(
      id: contributionId,
      contributor: 'user-teammate',
      project: 'proj-123',
      title: 'Disputed Deliverable',
      verificationStatus: 'needs-review',
      disputeState: 'disputed',
      visibility: 'private',
      createdAt: DateTime.now(),
    );
  }
}

void main() {
  late FakePendingConfirmationsProjectService fakeProjectService;

  final sampleRequests = [
    ConfirmationRequest(
      id: 'req-1',
      contributionId: 'contrib-1',
      projectId: 'proj-mobile',
      requestedBy: 'user-sara',
      reviewerId: 'user-alex',
      status: 'pending',
      contributionTitle: 'Figma Mobile App Mockups',
      projectName: 'BuildCrew Mobile',
      contributorName: 'Sara Designer',
      category: 'design',
      description: 'Completed 20+ mobile UI screens with full prototype interactions.',
      evidenceLink: 'https://figma.com/file/mobile-mockups',
      createdAt: DateTime.parse('2026-08-25T10:00:00Z'),
    ),
    ConfirmationRequest(
      id: 'req-2',
      contributionId: 'contrib-2',
      projectId: 'proj-mobile',
      requestedBy: 'user-bob',
      reviewerId: 'user-alex',
      status: 'pending',
      contributionTitle: 'CI/CD GitHub Actions Pipeline',
      projectName: 'BuildCrew Mobile',
      contributorName: 'Bob DevOps',
      category: 'infrastructure',
      description: 'Automated test and lint workflow on push to main.',
      evidenceLink: 'https://github.com/buildcrew/actions',
      createdAt: DateTime.parse('2026-08-25T11:00:00Z'),
    ),
  ];

  setUp(() {
    fakeProjectService = FakePendingConfirmationsProjectService();
  });

  Widget buildTestWidget() {
    return MaterialApp(
      home: PendingConfirmationsScreen(
        projectService: fakeProjectService,
      ),
    );
  }

  group('PendingConfirmationsScreen Widget Tests', () {
    testWidgets('renders empty state when there are no pending confirmation requests', (tester) async {
      fakeProjectService.mockRequests = [];

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('pending_confirmations_empty')), findsOneWidget);
      expect(find.text('All Caught Up!'), findsOneWidget);
      expect(find.text('0'), findsOneWidget);
    });

    testWidgets('renders loaded pending confirmation cards with contributor details and evidence', (tester) async {
      fakeProjectService.mockRequests = List.from(sampleRequests);

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('pending_confirmations_list')), findsOneWidget);
      expect(find.text('2'), findsOneWidget);

      // Card 1
      expect(find.text('Sara Designer'), findsOneWidget);
      expect(find.text('Figma Mobile App Mockups'), findsOneWidget);
      expect(find.text('in BuildCrew Mobile'), findsNWidgets(2));
      expect(find.text('DESIGN'), findsOneWidget);
      expect(find.text('https://figma.com/file/mobile-mockups'), findsOneWidget);

      // Card 2
      expect(find.text('Bob DevOps'), findsOneWidget);
      expect(find.text('CI/CD GitHub Actions Pipeline'), findsOneWidget);
      expect(find.text('INFRASTRUCTURE'), findsOneWidget);
    });

    testWidgets('filters requests dynamically when user types in search field', (tester) async {
      fakeProjectService.mockRequests = List.from(sampleRequests);

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('Figma Mobile App Mockups'), findsOneWidget);
      expect(find.text('CI/CD GitHub Actions Pipeline'), findsOneWidget);

      // Search for Bob
      await tester.enterText(find.byType(TextField), 'Bob');
      await tester.pumpAndSettle();

      expect(find.text('Figma Mobile App Mockups'), findsNothing);
      expect(find.text('CI/CD GitHub Actions Pipeline'), findsOneWidget);

      // Clear search
      await tester.enterText(find.byType(TextField), '');
      await tester.pumpAndSettle();

      expect(find.text('Figma Mobile App Mockups'), findsOneWidget);
      expect(find.text('CI/CD GitHub Actions Pipeline'), findsOneWidget);
    });

    testWidgets('tapping Peer Confirm calls confirmContribution and removes item with success banner', (tester) async {
      fakeProjectService.mockRequests = List.from(sampleRequests);

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      final confirmBtn = find.byKey(const Key('confirm_btn_req-1'));
      expect(confirmBtn, findsOneWidget);

      await tester.tap(confirmBtn);
      await tester.pumpAndSettle();

      expect(fakeProjectService.lastConfirmedId, 'contrib-1');
      expect(find.text('Confirmed "Figma Mobile App Mockups"!'), findsOneWidget);
      expect(find.text('Figma Mobile App Mockups'), findsNothing);
      expect(find.text('CI/CD GitHub Actions Pipeline'), findsOneWidget);
    });

    testWidgets('tapping Dispute opens confirmation dialog and disputes deliverable on confirm', (tester) async {
      fakeProjectService.mockRequests = List.from(sampleRequests);

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      final disputeBtn = find.byKey(const Key('dispute_btn_req-2'));
      expect(disputeBtn, findsOneWidget);

      await tester.ensureVisible(disputeBtn);
      await tester.pumpAndSettle();
      await tester.tap(disputeBtn);
      await tester.pumpAndSettle();

      // Verify dispute dialog is open
      expect(find.text('Dispute Deliverable?'), findsOneWidget);
      expect(
        find.textContaining('Its status will become "Needs Review"'),
        findsOneWidget,
      );

      // Tap confirm dispute button
      await tester.tap(find.byKey(const Key('confirm_dispute_dialog_btn')));
      await tester.pumpAndSettle();

      expect(fakeProjectService.lastDisputedId, 'contrib-2');
      expect(
        find.text('Disputed "CI/CD GitHub Actions Pipeline". Set to Needs Review.'),
        findsOneWidget,
      );
      expect(find.text('CI/CD GitHub Actions Pipeline'), findsNothing);
      expect(find.text('Figma Mobile App Mockups'), findsOneWidget);
    });

    testWidgets('displays error state and retries on load failure', (tester) async {
      fakeProjectService.shouldThrow = true;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('pending_confirmations_error')), findsOneWidget);
      expect(find.text('Failed to load requests'), findsOneWidget);

      // Now fix error and retry
      fakeProjectService.shouldThrow = false;
      fakeProjectService.mockRequests = List.from(sampleRequests);

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('pending_confirmations_list')), findsOneWidget);
      expect(find.text('Sara Designer'), findsOneWidget);
    });
  });
}
