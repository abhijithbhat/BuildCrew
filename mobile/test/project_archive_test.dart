import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/screens/my_projects_screen.dart';
import 'package:mobile/screens/project_detail_screen.dart';
import 'package:mobile/services/project_service.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:mobile/widgets/project_card.dart';

class MockStorageService extends StorageService {
  final String? _mockUserId;
  MockStorageService({String? mockUserId}) : _mockUserId = mockUserId ?? 'user-lead-123';

  @override
  Future<String?> getUserId() async => _mockUserId;

  @override
  Future<String?> getAccessToken() async => 'mock-valid-token';
}

class FakeArchiveProjectService extends ProjectService {
  List<Project> mockProjects = [];
  List<Map<String, dynamic>> mockRolesList = [];
  List<Contribution> mockContributionsList = [];
  bool deleteProjectCalled = false;
  String? lastDeletedProjectId;

  FakeArchiveProjectService({
    List<Project>? projects,
    List<Map<String, dynamic>>? roles,
  }) {
    if (projects != null) mockProjects = projects;
    if (roles != null) mockRolesList = roles;
  }

  @override
  Future<List<Project>> listProjects({bool includeArchived = false}) async {
    if (includeArchived) return mockProjects;
    return mockProjects.where((p) => !p.isArchived).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> listProjectRoles(String projectId) async {
    return mockRolesList;
  }

  @override
  Future<List<Contribution>> listContributions(
    String projectId, {
    String? status,
    String? contributor,
    String? category,
  }) async {
    return mockContributionsList;
  }

  @override
  Future<Map<String, dynamic>> deleteProject(String projectId) async {
    deleteProjectCalled = true;
    lastDeletedProjectId = projectId;
    final hasOthers = mockRolesList.any((r) => r['user_id'] != 'user-lead-123') || mockRolesList.length > 1;
    return {
      'message': hasOthers ? 'Project archived successfully' : 'Project dismantled permanently',
      'project_id': projectId,
      'archived': hasOthers,
    };
  }
}

void main() {
  group('Project Archiving & Dismantle Dialog Tests', () {
    testWidgets('dismantle dialog prompts to archive when other teammates exist', (WidgetTester tester) async {
      final leadProject = Project(
        id: 'proj-team-lead-1',
        name: 'Shared Rocket Project',
        description: 'Multi-member collaborative team',
        role: 'owner',
        createdBy: 'user-lead-123',
      );

      final service = FakeArchiveProjectService(
        roles: [
          {
            'user_id': 'user-lead-123',
            'declared_role': 'Tech Lead',
            'total_members': 2,
          },
          {
            'user_id': 'teammate-other-456',
            'declared_role': 'Frontend Engineer',
            'total_members': 2,
          },
        ],
      );

      await tester.pumpWidget(
        MaterialApp(
          routes: {
            ProjectDetailScreen.routeName: (context) => ProjectDetailScreen(
                  projectService: service,
                  storageService: MockStorageService(mockUserId: 'user-lead-123'),
                ),
          },
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.pushNamed(
                context,
                ProjectDetailScreen.routeName,
                arguments: leadProject,
              ),
              child: const Text('Open Project Detail'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Project Detail'));
      await tester.pumpAndSettle();

      // Scroll down to the dismantle button
      await tester.drag(find.byType(ListView), const Offset(0, -700));
      await tester.pumpAndSettle();

      expect(find.text('Dismantle / Delete Project'), findsOneWidget);

      // Tap dismantle button
      await tester.tap(find.text('Dismantle / Delete Project'));
      await tester.pumpAndSettle();

      // Dialog MUST display exact required copy
      expect(
        find.text('Archive project? Teammates keep their published passports. This can\'t be undone from the app.'),
        findsOneWidget,
      );
      expect(find.text('Archive Project'), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);

      // Confirm archive
      await tester.tap(find.text('Archive Project'));
      await tester.pumpAndSettle();

      expect(service.deleteProjectCalled, isTrue);
      expect(service.lastDeletedProjectId, equals('proj-team-lead-1'));
    });

    testWidgets('dismantle dialog prompts permanent dismantle when caller is solo member', (WidgetTester tester) async {
      final soloProject = Project(
        id: 'proj-solo-1',
        name: 'Solo Founder Project',
        description: 'Lead only project',
        role: 'owner',
        createdBy: 'user-lead-123',
      );

      final service = FakeArchiveProjectService(
        roles: [
          {
            'user_id': 'user-lead-123',
            'declared_role': 'Tech Lead',
            'total_members': 1,
          },
        ],
      );

      await tester.pumpWidget(
        MaterialApp(
          routes: {
            ProjectDetailScreen.routeName: (context) => ProjectDetailScreen(
                  projectService: service,
                  storageService: MockStorageService(mockUserId: 'user-lead-123'),
                ),
          },
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.pushNamed(
                context,
                ProjectDetailScreen.routeName,
                arguments: soloProject,
              ),
              child: const Text('Open Project Detail'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Project Detail'));
      await tester.pumpAndSettle();

      await tester.drag(find.byType(ListView), const Offset(0, -700));
      await tester.pumpAndSettle();

      expect(find.text('Dismantle / Delete Project'), findsOneWidget);

      await tester.tap(find.text('Dismantle / Delete Project'));
      await tester.pumpAndSettle();

      // Solo project dialog should NOT prompt with teammates text
      expect(
        find.text('Archive project? Teammates keep their published passports. This can\'t be undone from the app.'),
        findsNothing,
      );
      expect(find.textContaining('permanently dismantle'), findsOneWidget);
      expect(find.text('Yes, Dismantle'), findsOneWidget);
    });

    testWidgets('MyProjectsScreen partitions into active and Archived sections', (WidgetTester tester) async {
      final activeProject = Project(
        id: 'p-active',
        name: 'Active Build Project',
        description: 'Currently in progress',
        role: 'owner',
      );
      final archivedProject = Project(
        id: 'p-archived',
        name: 'Historic Apollo Project',
        description: 'Completed and archived',
        role: 'member',
        archivedAt: DateTime.parse('2026-03-01T10:00:00Z'),
      );

      final service = FakeArchiveProjectService(
        projects: [activeProject, archivedProject],
      );

      await tester.pumpWidget(
        MaterialApp(
          home: MyProjectsScreen(projectService: service),
        ),
      );

      await tester.pumpAndSettle();

      // Verify both project names appear
      expect(find.text('Active Build Project'), findsOneWidget);
      expect(find.text('Historic Apollo Project'), findsOneWidget);

      // Verify Archived section header is rendered
      expect(find.text('Archived'), findsNWidgets(2)); // 1 for section header, 1 for card badge
      expect(find.byType(ProjectCard), findsNWidgets(2));
    });

    testWidgets('ProjectCard renders Archived badge and hides Invite button for archived projects', (WidgetTester tester) async {
      final archivedProject = Project(
        id: 'p-card-archived',
        name: 'Archived Card Test',
        description: 'Testing badge visibility',
        role: 'owner',
        archivedAt: DateTime.now(),
      );

      bool inviteTapped = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ProjectCard(
              project: archivedProject,
              onInviteTap: () {
                inviteTapped = true;
              },
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();

      // "Archived" badge should be visible
      expect(find.text('Archived'), findsOneWidget);
      // Invite button should be hidden on archived card
      expect(find.text('Invite'), findsNothing);
      expect(inviteTapped, isFalse);
    });
  });
}
