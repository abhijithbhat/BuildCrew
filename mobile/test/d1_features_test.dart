import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/screens/pending_confirmations_screen.dart';
import 'package:mobile/screens/my_contributions_screen.dart';
import 'package:mobile/screens/team_ledger_screen.dart';
import 'package:mobile/services/project_service.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:mobile/widgets/dispute_bottom_sheet.dart';
import 'package:mobile/widgets/request_confirmation_modal.dart';
import 'package:mobile/widgets/contribution_card.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/screens/project_detail_screen.dart';

class FakeStorageService extends StorageService {
  final String? userId;
  final String? userName;

  FakeStorageService({this.userId = 'user-me', this.userName = 'Me'});

  @override
  Future<String?> getUserId() async => userId;

  @override
  Future<String?> getUserName() async => userName;
}

class MockD1ProjectService extends ProjectService {
  List<ConfirmationRequest> pendingRequests = [];
  List<Contribution> contributions = [];
  List<LedgerEntry> ledgerEntries = [];
  List<Map<String, dynamic>> projectRoles = [];

  String? lastConfirmedId;
  String? lastDisputedId;
  String? lastDisputeReason;
  String? lastWithdrawnId;
  String? lastReopenedId;
  String? lastRequestedContributionId;
  List<String>? lastRequestedReviewerIds;

  @override
  Future<List<ConfirmationRequest>> getPendingConfirmations() async {
    return pendingRequests;
  }

  @override
  Future<Contribution> confirmContribution(String contributionId) async {
    lastConfirmedId = contributionId;
    return Contribution(
      id: contributionId,
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Confirmed Deliverable',
      verificationStatus: 'confirmed',
    );
  }

  @override
  Future<Contribution> disputeContribution(
    String contributionId, {
    String? reason,
  }) async {
    lastDisputedId = contributionId;
    lastDisputeReason = reason;
    return Contribution(
      id: contributionId,
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Disputed Deliverable',
      verificationStatus: 'needs-review',
      disputeState: 'disputed',
      disputeReason: reason,
    );
  }

  @override
  Future<Contribution> withdrawDispute(String contributionId) async {
    lastWithdrawnId = contributionId;
    return Contribution(
      id: contributionId,
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Withdrawn Deliverable',
      verificationStatus: 'pending',
      disputeState: 'none',
    );
  }

  @override
  Future<Contribution> reopenContribution(String contributionId) async {
    lastReopenedId = contributionId;
    return Contribution(
      id: contributionId,
      contributor: 'user-1',
      project: 'proj-1',
      title: 'Reopened Deliverable',
      verificationStatus: 'pending',
      disputeState: 'none',
    );
  }

  @override
  Future<List<Contribution>> listContributions(
    String projectId, {
    String? status,
    String? contributor,
    String? category,
  }) async {
    return contributions;
  }

  @override
  Future<List<ConfirmationRequest>> requestConfirmation({
    required String contributionId,
    List<String>? reviewerIds,
  }) async {
    lastRequestedContributionId = contributionId;
    lastRequestedReviewerIds = reviewerIds;
    return [];
  }

  @override
  Future<List<Map<String, dynamic>>> listProjectRoles(String projectId) async {
    return projectRoles;
  }

  @override
  Future<List<LedgerEntry>> getProjectLedger(String projectId) async {
    return ledgerEntries;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late MockD1ProjectService mockService;

  setUp(() {
    mockService = MockD1ProjectService();
  });

  group('Requirement 1: Dispute Bottom Sheet & Confirm line', () {
    testWidgets('Dispute bottom sheet allows optional reason up to 280 chars', (tester) async {
      String? submittedReason;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () async {
                  submittedReason = await DisputeBottomSheet.show(
                    context: ctx,
                    deliverableTitle: 'Figma UI Prototype',
                  );
                },
                child: const Text('Open Dispute Sheet'),
              ),
            ),
          ),
        ),
      );

      // Open bottom sheet
      await tester.tap(find.text('Open Dispute Sheet'));
      await tester.pumpAndSettle();

      // Verify bottom sheet title and deliverable title
      expect(find.text('Dispute Deliverable'), findsOneWidget);
      expect(find.text('Figma UI Prototype'), findsOneWidget);

      // Enter a reason
      final reasonField = find.byKey(const Key('dispute_reason_field'));
      expect(reasonField, findsOneWidget);
      await tester.enterText(reasonField, 'Missing auth flow screens');
      await tester.pumpAndSettle();

      // Submit dispute
      await tester.tap(find.byKey(const Key('confirm_dispute_dialog_btn')));
      await tester.pumpAndSettle();

      expect(submittedReason, 'Missing auth flow screens');
    });

    testWidgets('Confirm line shows on pending items and confirm calls confirmContribution', (tester) async {
      mockService.pendingRequests = [
        ConfirmationRequest(
          id: 'req-1',
          contributionId: 'contrib-1',
          projectId: 'proj-1',
          requestedBy: 'user-author',
          reviewerId: 'user-me',
          status: 'pending',
          contributionTitle: 'Marketing Strategy Deck',
          projectName: 'Acme Launch',
          contributorName: 'Alex Author',
          category: 'presentation',
        ),
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: PendingConfirmationsScreen(
            projectService: mockService,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify exact one-line confirmation note is displayed
      expect(
        find.text('Your name will appear next to this item if the author publishes it.'),
        findsOneWidget,
      );

      // Tap confirm button
      final confirmBtn = find.byKey(const Key('confirm_btn_req-1'));
      expect(confirmBtn, findsOneWidget);
      await tester.tap(confirmBtn);
      await tester.pumpAndSettle();

      expect(mockService.lastConfirmedId, 'contrib-1');
    });
  });

  group('Requirement 2: My Contributions Needs-Review, Copy, and Orphan Reopen', () {
    testWidgets('Needs-review shows Disputed by <name>: <reason>, replacement copy, and Reopen only when orphaned', (tester) async {
      final activeDisputeContrib = Contribution(
        id: 'contrib-active',
        contributor: 'user-me',
        project: 'proj-1',
        title: 'Backend Auth API',
        verificationStatus: 'needs-review',
        disputeState: 'disputed',
        disputedByName: 'Sarah Lead',
        disputeReason: 'Token validation logic is flawed',
        isDisputeOrphaned: false,
        canReopen: false,
      );

      final orphanedDisputeContrib = Contribution(
        id: 'contrib-orphaned',
        contributor: 'user-me',
        project: 'proj-1',
        title: 'Database Migration v2',
        verificationStatus: 'needs-review',
        disputeState: 'disputed',
        disputedByName: 'Dave Former',
        disputeReason: 'Legacy column mismatch',
        isDisputeOrphaned: true,
        canReopen: true,
      );

      mockService.contributions = [activeDisputeContrib, orphanedDisputeContrib];

      await tester.pumpWidget(
        MaterialApp(
          home: MyContributionsScreen(
            projectId: 'proj-1',
            projectService: mockService,
            storageService: FakeStorageService(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. Shows 'Disputed by <name>: <reason>' on first item
      expect(
        find.text('Disputed by Sarah Lead: Token validation logic is flawed'),
        findsOneWidget,
      );
      expect(
        find.text('Ask Sarah Lead to withdraw the dispute, or delete this item and log a corrected one.'),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('reopen_btn_contrib-active')),
        findsNothing,
      );

      // Scroll down to reveal second item
      await tester.drag(find.byType(SingleChildScrollView).first, const Offset(0, -400));
      await tester.pumpAndSettle();

      expect(
        find.text('Disputed by Dave Former: Legacy column mismatch'),
        findsOneWidget,
      );
      expect(
        find.text('Ask Dave Former to withdraw the dispute, or delete this item and log a corrected one.'),
        findsOneWidget,
      );

      // Ensure old copy is gone
      expect(
        find.textContaining('hidden from your public passport until resolved'),
        findsNothing,
      );

      // 3. 'Reopen' shown ONLY when server says dispute is orphaned
      final reopenOrphanBtn = find.byKey(const Key('reopen_btn_contrib-orphaned'));
      expect(reopenOrphanBtn, findsOneWidget);

      // Tap Reopen
      await tester.tap(reopenOrphanBtn);
      await tester.pumpAndSettle();

      expect(mockService.lastReopenedId, 'contrib-orphaned');
    });
  });

  group('Requirement 3: Pending Confirmations Withdraw Dispute', () {
    testWidgets('Item disputed by current user shows Withdraw my dispute button and calls withdrawDispute', (tester) async {
      mockService.pendingRequests = [
        ConfirmationRequest(
          id: 'req-disp-1',
          contributionId: 'contrib-disp-1',
          projectId: 'proj-1',
          requestedBy: 'user-teammate',
          reviewerId: 'user-me',
          status: 'disputed',
          contributionTitle: 'UI Icon Set Deliverable',
          projectName: 'Acme Mobile',
          contributorName: 'Lisa Designer',
        ),
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: PendingConfirmationsScreen(
            projectService: mockService,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Withdraw button is shown
      final withdrawBtn = find.byKey(const Key('withdraw_dispute_btn_req-disp-1'));
      expect(withdrawBtn, findsOneWidget);
      expect(find.text('Withdraw my dispute'), findsOneWidget);

      // Tapping Withdraw my dispute calls withdrawDispute
      await tester.tap(withdrawBtn);
      await tester.pumpAndSettle();

      expect(mockService.lastWithdrawnId, 'contrib-disp-1');
      expect(find.text('Withdrew dispute for "UI Icon Set Deliverable".'), findsOneWidget);
    });
  });

  group('Requirement 4: request_confirmation_modal Preselection, Toggle & Broadcast', () {
    testWidgets('Preselects ALL teammates, displays Ask the whole team (N), and omits reviewer_ids on broadcast', (tester) async {
      mockService.projectRoles = [
        {
          'user_id': 'user-1',
          'profile': {'display_name': 'Teammate One'},
          'declared_role': 'Frontend Engineer',
        },
        {
          'user_id': 'user-2',
          'profile': {'display_name': 'Teammate Two'},
          'declared_role': 'Backend Engineer',
        },
        {
          'user_id': 'user-3',
          'profile': {'display_name': 'Teammate Three'},
          'declared_role': 'UI Designer',
        },
      ];

      final testContrib = Contribution(
        id: 'contrib-req-test',
        contributor: 'user-me',
        project: 'proj-1',
        title: 'New Feature Specs',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RequestConfirmationModalContent(
              contribution: testContrib,
              projectId: 'proj-1',
              projectService: mockService,
              currentUserId: 'user-me',
              onSuccess: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. All 3 teammates are preselected
      expect(find.text('Teammates (3/3 selected)'), findsOneWidget);

      // 2. CTA button says 'Ask the whole team (3)'
      final submitBtn = find.byKey(const Key('submit_request_confirmation_btn'));
      expect(submitBtn, findsOneWidget);
      expect(find.text('Ask the whole team (3)'), findsOneWidget);

      // 3. When submitting with everyone selected, reviewer_ids is omitted (null)
      await tester.tap(submitBtn);
      await tester.pumpAndSettle();

      expect(mockService.lastRequestedContributionId, 'contrib-req-test');
      expect(mockService.lastRequestedReviewerIds, isNull);
    });

    testWidgets('Deselect All toggle clears selection, changes CTA, and allows custom subset selection', (tester) async {
      mockService.projectRoles = [
        {
          'user_id': 'user-1',
          'profile': {'display_name': 'Teammate One'},
          'declared_role': 'Frontend Engineer',
        },
        {
          'user_id': 'user-2',
          'profile': {'display_name': 'Teammate Two'},
          'declared_role': 'Backend Engineer',
        },
        {
          'user_id': 'user-3',
          'profile': {'display_name': 'Teammate Three'},
          'declared_role': 'UI Designer',
        },
      ];

      final testContrib = Contribution(
        id: 'contrib-req-test',
        contributor: 'user-me',
        project: 'proj-1',
        title: 'New Feature Specs',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RequestConfirmationModalContent(
              contribution: testContrib,
              projectId: 'proj-1',
              projectService: mockService,
              currentUserId: 'user-me',
              onSuccess: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Deselect All'), findsOneWidget);
      await tester.tap(find.text('Deselect All'));
      await tester.pumpAndSettle();

      expect(find.text('Teammates (0/3 selected)'), findsOneWidget);
      expect(find.text('Select All'), findsOneWidget);

      // Select just 1 teammate
      await tester.tap(find.byKey(const Key('reviewer_checkbox_user-1')));
      await tester.pumpAndSettle();

      expect(find.text('Teammates (1/3 selected)'), findsOneWidget);
      expect(find.text('Ask 1 teammate'), findsOneWidget);

      // Submit sends only user-1
      final submitBtn = find.byKey(const Key('submit_request_confirmation_btn'));
      await tester.tap(submitBtn);
      await tester.pumpAndSettle();

      expect(mockService.lastRequestedReviewerIds, ['user-1']);
    });
  });

  group('Requirements 5 & 6: Team Ledger Screen & Remind Teammates', () {
    testWidgets('Team Ledger groups by teammate, shows proof tags, and review button opens review flow', (tester) async {
      mockService.ledgerEntries = [
        LedgerEntry(
          id: 'ledger-1',
          contributorId: 'user-alice',
          contributorName: 'Alice Dev',
          title: 'GraphQL API Setup',
          category: 'code',
          verificationStatus: 'source-verified',
          confirmations: [],
          waitingOnMe: false,
        ),
        LedgerEntry(
          id: 'ledger-2',
          contributorId: 'user-bob',
          contributorName: 'Bob Designer',
          title: 'Color Palette Guide',
          category: 'design',
          verificationStatus: 'peer-confirmed',
          confirmations: [
            ConfirmationVoteInfo(name: 'Alice'),
            ConfirmationVoteInfo(name: 'Charlie'),
          ],
          waitingOnMe: true,
        ),
        LedgerEntry(
          id: 'ledger-3',
          contributorId: 'user-bob',
          contributorName: 'Bob Designer',
          title: 'Typography System',
          category: 'design',
          verificationStatus: 'pending',
          confirmations: [],
          waitingOnMe: true,
        ),
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: TeamLedgerScreen(
            projectId: 'proj-1',
            projectName: 'Acme App',
            projectService: mockService,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Groups by teammate
      expect(find.text('Alice Dev'), findsOneWidget);
      expect(find.text('Bob Designer'), findsOneWidget);

      // Proof tags
      expect(find.text('GitHub-verified'), findsOneWidget);
      expect(find.text('Confirmed by Alice, Charlie'), findsOneWidget);
      expect(find.text('Waiting for review'), findsOneWidget);

      // Review button shown for waitingOnMe
      final reviewBtn = find.byKey(const Key('ledger_review_btn_ledger-2'));
      expect(reviewBtn, findsOneWidget);

      // Tap Review button opens bottom sheet
      await tester.tap(reviewBtn);
      await tester.pumpAndSettle();

      expect(find.text('Review Deliverable'), findsOneWidget);
      expect(
        find.text('Your name will appear next to this item if the author publishes it.'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('ledger_review_confirm_btn')), findsOneWidget);
      expect(find.byKey(const Key('ledger_review_dispute_btn')), findsOneWidget);

      // Tap Peer Confirm in sheet
      await tester.tap(find.byKey(const Key('ledger_review_confirm_btn')));
      await tester.pumpAndSettle();

      expect(mockService.lastConfirmedId, 'ledger-2');
    });

    testWidgets('Remind teammates copies reminder text to clipboard for author self-declared items', (tester) async {
      String? copiedText;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall methodCall) async {
          if (methodCall.method == 'Clipboard.setData') {
            copiedText = (methodCall.arguments as Map)['text'] as String?;
            return null;
          }
          return null;
        },
      );

      final authorSelfDeclaredContrib = Contribution(
        id: 'contrib-self-1',
        contributor: 'user-me',
        project: 'Alpha Project',
        title: 'User Research Interview Notes',
        sourceType: 'self_declared',
        verificationStatus: 'self-declared',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ContributionCard(
              contribution: authorSelfDeclaredContrib,
              isContributor: true,
              projectName: 'Alpha Project',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final remindBtn = find.byKey(const Key('remind_teammates_btn_contrib-self-1'));
      expect(remindBtn, findsOneWidget);
      expect(find.text('Remind teammates'), findsOneWidget);

      await tester.tap(remindBtn);
      await tester.pumpAndSettle();

      expect(
        copiedText,
        'BuildCrew: please review my contribution "User Research Interview Notes" in Alpha Project',
      );
    });

    testWidgets('ProjectDetailScreen opens Team Ledger via action chip and AppBar button', (tester) async {
      mockService.ledgerEntries = [
        LedgerEntry(
          id: 'ledger-item-1',
          contributorId: 'user-bob',
          contributorName: 'Bob Builder',
          title: 'Infrastructure Deployment',
          category: 'devops',
          verificationStatus: 'peer-confirmed',
          confirmations: [ConfirmationVoteInfo(name: 'Alice')],
          waitingOnMe: false,
        ),
      ];

      final project = Project(
        id: 'proj-123',
        name: 'Ledger Nav Test',
        description: 'Testing Ledger Navigation',
        role: 'owner',
      );

      await tester.pumpWidget(
        MaterialApp(
          routes: {
            ProjectDetailScreen.routeName: (context) => ProjectDetailScreen(
                  projectService: mockService,
                  storageService: FakeStorageService(),
                ),
          },
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.pushNamed(
                context,
                ProjectDetailScreen.routeName,
                arguments: project,
              ),
              child: const Text('Go to Details'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Go to Details'));
      await tester.pumpAndSettle();

      // Verify the Team Ledger button in AppBar
      final appbarLedgerBtn = find.byKey(const Key('project_appbar_team_ledger_btn'));
      expect(appbarLedgerBtn, findsOneWidget);

      await tester.tap(appbarLedgerBtn);
      await tester.pumpAndSettle();

      // TeamLedgerScreen rendered
      expect(find.text('Team Ledger'), findsWidgets);
      expect(find.text('Bob Builder'), findsOneWidget);
      expect(find.text('Infrastructure Deployment'), findsOneWidget);

      // Pop back to ProjectDetailScreen
      await tester.pageBack();
      await tester.pumpAndSettle();

      // Scroll down to contribution stream and tap Team Ledger chip
      await tester.drag(find.byType(ListView), const Offset(0, -400));
      await tester.pumpAndSettle();

      final chipLedgerBtn = find.byKey(const Key('project_detail_team_ledger_btn'));
      expect(chipLedgerBtn, findsOneWidget);

      await tester.tap(chipLedgerBtn);
      await tester.pumpAndSettle();

      expect(find.text('Bob Builder'), findsOneWidget);
    });
  });
}
