import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/screens/connect_repository_screen.dart';
import 'package:mobile/screens/repo_status_screen.dart';
import 'package:mobile/services/github_service.dart';

class MockGitHubService extends GitHubService {
  final bool shouldSucceed;
  final bool isConnected;
  final Map<String, dynamic>? customInstallation;
  bool launchCalled = false;
  bool unlinkCalled = false;

  MockGitHubService({
    this.shouldSucceed = true,
    this.isConnected = true,
    this.customInstallation,
  });

  @override
  Future<bool> launchInstallFlow(String projectId) async {
    launchCalled = true;
    if (!shouldSucceed) {
      throw 'Failed to connect to GitHub installation endpoint.';
    }
    return true;
  }

  @override
  Future<Map<String, dynamic>> getInstallation(String projectId) async {
    if (!shouldSucceed) {
      throw 'Network error while fetching installation.';
    }
    if (!isConnected) {
      return {'connected': false, 'installation': null};
    }
    return {
      'connected': true,
      'installation': customInstallation ??
          {
            'id': 'inst-uuid-1',
            'project_id': projectId,
            'installation_id': '4635635',
            'repo_full_name': 'BuildCrew-Org/buildcrew-core',
            'connected_at': '2026-08-19T10:00:00Z',
          },
    };
  }

  @override
  Future<bool> unlinkInstallation(String projectId) async {
    unlinkCalled = true;
    if (!shouldSucceed) {
      throw 'Failed to disconnect repository.';
    }
    return true;
  }
}

void main() {
  group('ConnectRepositoryScreen Tests', () {
    testWidgets('renders all header elements, feature highlights, and connect button',
        (WidgetTester tester) async {
      final mockService = MockGitHubService(shouldSucceed: true);

      await tester.pumpWidget(
        MaterialApp(
          home: ConnectRepositoryScreen(
            projectId: 'proj-123',
            projectName: 'BuildCrew Core',
            gitHubService: mockService,
          ),
        ),
      );

      // Verify AppBar
      expect(find.text('Connect Repository'), findsOneWidget);

      // Verify Project Title & Subtitle
      expect(find.text('Link GitHub to\nBuildCrew Core'), findsOneWidget);
      expect(
        find.text(
          'Connect your repository to seamlessly track commits, review pull requests, and log member contributions.',
        ),
        findsOneWidget,
      );

      // Verify Feature Highlight Rows
      expect(find.text('Live Commit Sync'), findsOneWidget);
      expect(find.text('Pull Request Activity'), findsOneWidget);
      expect(find.text('Issue & Milestone Tracking'), findsOneWidget);
      expect(find.text('Secure & Read-Only Access'), findsOneWidget);

      // Verify Connect Button
      expect(find.text('Open GitHub in Browser'), findsOneWidget);
      expect(find.byIcon(Icons.open_in_browser_rounded), findsOneWidget);

      // Scroll into view & tap Connect Button
      await tester.ensureVisible(find.text('Open GitHub in Browser'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Open GitHub in Browser'));
      await tester.pumpAndSettle();

      expect(mockService.launchCalled, isTrue);
      expect(
        find.text(
          'Opening GitHub in browser... Click "Save" or "Install" on GitHub and return here.',
        ),
        findsOneWidget,
      );
    });

    testWidgets('displays error banner when launchInstallFlow throws error',
        (WidgetTester tester) async {
      final mockService = MockGitHubService(shouldSucceed: false);

      await tester.pumpWidget(
        MaterialApp(
          home: ConnectRepositoryScreen(
            projectId: 'proj-123',
            projectName: 'BuildCrew Core',
            gitHubService: mockService,
          ),
        ),
      );

      // Tap Connect Button
      await tester.ensureVisible(find.text('Open GitHub in Browser'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Open GitHub in Browser'));
      await tester.pumpAndSettle();

      expect(mockService.launchCalled, isTrue);
      expect(
        find.text('Failed to connect to GitHub installation endpoint.'),
        findsOneWidget,
      );
    });

  });

  group('RepoStatusScreen Tests', () {
    testWidgets('renders connected repository name, badge, and metadata',
        (WidgetTester tester) async {
      final mockService = MockGitHubService(isConnected: true);

      await tester.pumpWidget(
        MaterialApp(
          home: RepoStatusScreen(
            projectId: 'proj-123',
            projectName: 'BuildCrew Core',
            isOwner: true,
            gitHubService: mockService,
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Verify Connected Badge & Name
      expect(find.text('Connected & Active'), findsOneWidget);
      expect(find.text('BuildCrew-Org/buildcrew-core'), findsOneWidget);
      expect(find.text('View on GitHub (BuildCrew-Org/buildcrew-core)'),
          findsOneWidget);

      // Verify Installation Details
      expect(find.text('Integration Details'), findsOneWidget);
      expect(find.text('#4635635'), findsOneWidget);
      expect(find.text('Read-Only (Secure RS256)'), findsOneWidget);

      // Verify Disconnect button for Owner
      expect(find.text('Disconnect Repository'), findsOneWidget);
    });

    testWidgets('renders unconnected empty state with connect button',
        (WidgetTester tester) async {
      final mockService = MockGitHubService(isConnected: false);

      await tester.pumpWidget(
        MaterialApp(
          home: RepoStatusScreen(
            projectId: 'proj-123',
            projectName: 'BuildCrew Core',
            isOwner: true,
            gitHubService: mockService,
          ),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text('No Repository Connected'), findsOneWidget);
      expect(find.text('Connect with GitHub'), findsOneWidget);
    });

    testWidgets('renders error state and retry button on fetch failure',
        (WidgetTester tester) async {
      final mockService = MockGitHubService(shouldSucceed: false);

      await tester.pumpWidget(
        MaterialApp(
          home: RepoStatusScreen(
            projectId: 'proj-123',
            projectName: 'BuildCrew Core',
            isOwner: true,
            gitHubService: mockService,
          ),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text('Could not load repository status'), findsOneWidget);
      expect(find.text('Network error while fetching installation.'),
          findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
    });

    testWidgets('unlinks repository when owner confirms disconnect',
        (WidgetTester tester) async {
      final mockService = MockGitHubService(isConnected: true);

      await tester.pumpWidget(
        MaterialApp(
          home: RepoStatusScreen(
            projectId: 'proj-123',
            projectName: 'BuildCrew Core',
            isOwner: true,
            gitHubService: mockService,
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Tap Disconnect Repository
      await tester.ensureVisible(find.text('Disconnect Repository'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Disconnect Repository'));
      await tester.pumpAndSettle();

      // Verify confirmation dialog
      expect(find.text('Disconnect Repository?'), findsOneWidget);
      expect(find.text('Yes, Disconnect'), findsOneWidget);

      // Confirm disconnect
      await tester.tap(find.text('Yes, Disconnect'));
      await tester.pumpAndSettle();

      expect(mockService.unlinkCalled, isTrue);
    });

    testWidgets('renders long repository names cleanly without overflow',
        (WidgetTester tester) async {
      final longRepoMock = MockGitHubService(
        isConnected: true,
        customInstallation: {
          'id': 'inst-long-1',
          'project_id': 'proj-123',
          'installation_id': '9876543',
          'repo_full_name':
              'Very-Long-Enterprise-Org-Name/extremely-long-custom-buildcrew-mobile-app-repository',
          'connected_at': '2026-08-22T10:00:00Z',
        },
      );

      await tester.pumpWidget(
        MaterialApp(
          home: RepoStatusScreen(
            projectId: 'proj-123',
            projectName: 'Enterprise BuildCrew Project Long Title',
            isOwner: true,
            gitHubService: longRepoMock,
          ),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text('Connected & Active'), findsOneWidget);
      expect(
        find.text(
          'Very-Long-Enterprise-Org-Name/extremely-long-custom-buildcrew-mobile-app-repository',
        ),
        findsOneWidget,
      );
      expect(find.text('Integration Details'), findsOneWidget);
    });
  });
}
