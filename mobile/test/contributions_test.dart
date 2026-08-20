import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/widgets/contribution_card.dart';

void main() {
  group('Contribution Model Tests', () {
    test('Correctly deserializes from JSON with source-verified status', () {
      final json = {
        'id': 'contrib-123',
        'contributor': 'user-456',
        'project': 'proj-789',
        'title': 'feat: implement contribution stream',
        'category': 'code',
        'description': 'Added reactive Flutter widgets and FastAPI router',
        'date_range': '2026-08-20',
        'source_type': 'github_commit',
        'evidence_link': 'https://github.com/BuildCrew-Org/buildcrew/commit/abc1234',
        'verification_status': 'source-verified',
        'confirmed_by': null,
        'visibility': 'public',
        'dispute_state': 'none',
        'created_at': '2026-08-20T12:00:00Z',
        'contributor_name': 'Vishwajith Bhat',
      };

      final contribution = Contribution.fromJson(json);

      expect(contribution.id, 'contrib-123');
      expect(contribution.contributor, 'user-456');
      expect(contribution.project, 'proj-789');
      expect(contribution.title, 'feat: implement contribution stream');
      expect(contribution.category, 'code');
      expect(contribution.sourceType, 'github_commit');
      expect(contribution.verificationStatus, 'source-verified');
      expect(contribution.isSourceVerified, isTrue);
      expect(contribution.isConfirmed, isFalse);
      expect(contribution.isDraft, isTrue);
      expect(contribution.contributorName, 'Vishwajith Bhat');
    });

    test('DraftGenerationResult parses generated draft list accurately', () {
      final json = {
        'message': 'Successfully generated 2 draft contributions from GitHub activity.',
        'project_id': 'proj-789',
        'generated_count': 2,
        'contributions': [
          {
            'id': 'c1',
            'contributor': 'u1',
            'project': 'proj-789',
            'title': 'Commit 1',
            'source_type': 'github_commit',
            'verification_status': 'source-verified',
          },
          {
            'id': 'c2',
            'contributor': 'u2',
            'project': 'proj-789',
            'title': 'Pull Request 1',
            'source_type': 'github_pr',
            'verification_status': 'source-verified',
          },
        ],
        'last_generated_at': '2026-08-20T12:30:00Z',
      };

      final result = DraftGenerationResult.fromJson(json);

      expect(result.message, contains('Successfully generated'));
      expect(result.generatedCount, 2);
      expect(result.contributions.length, 2);
      expect(result.contributions[0].title, 'Commit 1');
      expect(result.contributions[1].sourceType, 'github_pr');
    });
  });

  group('ContributionCard Widget Tests', () {
    testWidgets('Renders Git Commit contribution card with Source Verified badge', (tester) async {
      final contribution = Contribution(
        id: 'c-test-1',
        contributor: 'u-1',
        project: 'p-1',
        title: 'fix(auth): secure token refresh flow',
        category: 'code',
        description: 'Fixed token leakage in dev mode',
        sourceType: 'github_commit',
        verificationStatus: 'source-verified',
        contributorName: 'Alex Developer',
        createdAt: DateTime.utc(2026, 8, 20, 10, 30),
      );

      bool tapped = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ContributionCard(
              contribution: contribution,
              onTap: () => tapped = true,
            ),
          ),
        ),
      );

      expect(find.text('Git Commit'), findsOneWidget);
      expect(find.text('Source Verified'), findsOneWidget);
      expect(find.text('fix(auth): secure token refresh flow'), findsOneWidget);
      expect(find.text('Fixed token leakage in dev mode'), findsOneWidget);
      expect(find.text('Alex Developer'), findsOneWidget);
      expect(find.text('2026-08-20'), findsOneWidget);

      await tester.tap(find.byType(ContributionCard));
      expect(tapped, isTrue);
    });

    testWidgets('Renders Pull Request card with Peer Confirmed badge', (tester) async {
      final contribution = Contribution(
        id: 'c-test-2',
        contributor: 'u-2',
        project: 'p-1',
        title: 'feat: add dark theme support',
        sourceType: 'github_pr',
        verificationStatus: 'confirmed',
        contributorName: 'Sarah Engineer',
        createdAt: DateTime.utc(2026, 8, 19),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ContributionCard(
              contribution: contribution,
            ),
          ),
        ),
      );

      expect(find.text('Pull Request'), findsOneWidget);
      expect(find.text('Peer Confirmed'), findsOneWidget);
      expect(find.text('feat: add dark theme support'), findsOneWidget);
      expect(find.text('Sarah Engineer'), findsOneWidget);
    });
  });
}
