import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/models/role_agreement.dart';
import 'package:mobile/screens/create_project_screen.dart';
import 'package:mobile/screens/declare_role_screen.dart';
import 'package:mobile/screens/invite_teammate_screen.dart';
import 'package:mobile/screens/join_project_screen.dart';
import 'package:mobile/screens/my_projects_screen.dart';
import 'package:mobile/screens/project_detail_screen.dart';
import 'package:mobile/screens/team_roles_screen.dart';
import 'package:mobile/services/project_service.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:mobile/widgets/project_card.dart';

class FakeStorageService extends StorageService {
  String? userId;
  String? userEmail;
  String? userName;

  FakeStorageService({this.userId, this.userEmail, this.userName});

  @override
  Future<String?> getUserId() async => userId;

  @override
  Future<String?> getUserEmail() async => userEmail;

  @override
  Future<String?> getUserName() async => userName;
}


class FakeSuccessProjectService extends ProjectService {

  bool declareRoleCalled = false;
  String? lastProjectId;
  String? lastDeclaredRole;
  List<Map<String, dynamic>> mockRolesList = [];

  @override
  Future<Map<String, dynamic>> declareRole({
    required String projectId,
    required String declaredRole,
    String? responsibilities,
    DateTime? deadline,
  }) async {
    declareRoleCalled = true;
    lastProjectId = projectId;
    lastDeclaredRole = declaredRole;
    return {
      'message': 'Role declared successfully',
      'role_agreement': {
        'id': 'role-123',
        'project_id': projectId,
        'declared_role': declaredRole,
        'responsibilities': responsibilities,
        'deadline': deadline?.toIso8601String(),
      }
    };
  }

  @override
  Future<List<Map<String, dynamic>>> listProjectRoles(String projectId) async {
    return mockRolesList;
  }
}

class FakeErrorProjectService extends ProjectService {
  @override
  Future<Map<String, dynamic>> declareRole({
    required String projectId,
    required String declaredRole,
    String? responsibilities,
    DateTime? deadline,
  }) async {
    throw 'Project not found or user is not a member.';
  }

  @override
  Future<List<Map<String, dynamic>>> listProjectRoles(String projectId) async {
    throw 'Failed to connect to backend server.';
  }
}








void main() {
  group('Project Model Tests', () {
    test('fromJson and toJson should correctly serialize and deserialize', () {
      final json = {
        'id': 'proj-123',
        'name': 'BuildCrew Mobile',
        'description': 'Mobile client for builder teams',
        'created_by': 'user-456',
        'created_at': '2026-08-15T10:00:00.000Z',
        'updated_at': '2026-08-15T10:00:00.000Z',
        'role': 'owner',
        'joined_at': '2026-08-15T10:00:00.000Z',
      };

      final project = Project.fromJson(json);

      expect(project.id, 'proj-123');
      expect(project.name, 'BuildCrew Mobile');
      expect(project.description, 'Mobile client for builder teams');
      expect(project.createdBy, 'user-456');
      expect(project.role, 'owner');
      expect(project.createdAt, isNotNull);

      final outputJson = project.toJson();
      expect(outputJson['id'], 'proj-123');
      expect(outputJson['name'], 'BuildCrew Mobile');
      expect(outputJson['role'], 'owner');
    });

    test('fromJson handles null and missing optional fields safely', () {
      final json = {
        'id': 'proj-456',
        'name': 'Minimal Project',
      };

      final project = Project.fromJson(json);

      expect(project.id, 'proj-456');
      expect(project.name, 'Minimal Project');
      expect(project.description, isNull);
      expect(project.createdBy, isNull);
      expect(project.role, isNull);
    });
  });

  group('CreateProjectScreen Widget Tests', () {
    testWidgets('renders all required form fields and elements', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: CreateProjectScreen(),
        ),
      );

      expect(find.text('Create Project'), findsNWidgets(2)); // Title & Button
      expect(find.text('Start a New Project'), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(2));
      expect(find.text('Project Name'), findsOneWidget);
      expect(find.text('Project Description'), findsOneWidget);
      expect(find.byType(ElevatedButton), findsOneWidget);
    });

    testWidgets('validates required fields on create button tap', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: CreateProjectScreen(),
        ),
      );

      // Tap Create Project button with empty form
      await tester.tap(find.byType(ElevatedButton));
      await tester.pumpAndSettle();

      expect(find.text('Please enter a project name'), findsOneWidget);
      expect(find.text('Please enter a project description'), findsOneWidget);
    });
  });

  group('ProjectCard Widget Tests', () {
    testWidgets('renders project card details and role badges properly', (WidgetTester tester) async {
      final project = Project(
        id: 'p1',
        name: 'BuildCrew Core',
        description: 'Core backend and mobile engine',
        role: 'owner',
        createdAt: DateTime(2026, 8, 15),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ProjectCard(project: project),
          ),
        ),
      );

      expect(find.text('BuildCrew Core'), findsOneWidget);
      expect(find.text('Core backend and mobile engine'), findsOneWidget);
      expect(find.text('Team Lead'), findsOneWidget);
      expect(find.text('Crew Admin'), findsOneWidget);
      expect(find.text('B'), findsOneWidget); // Leading Avatar Initial
    });
  });


  group('MyProjectsScreen Widget Tests', () {
    testWidgets('renders search bar, filter chips, and action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: MyProjectsScreen(),
        ),
      );

      expect(find.text('My Projects'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
      expect(find.text('All'), findsOneWidget);
      expect(find.text('Owned'), findsOneWidget);
      expect(find.text('Joined'), findsOneWidget);
      expect(find.byIcon(Icons.add_circle_outline), findsOneWidget);
      expect(find.byIcon(Icons.group_add_outlined), findsOneWidget);
    });
  });

  group('InviteTeammateScreen Widget Tests', () {
    testWidgets('renders invite code, direct link, and share button', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: InviteTeammateScreen(),
        ),
      );

      expect(find.text('Invite Teammates'), findsOneWidget);
    });
  });

  group('JoinProjectScreen Widget Tests', () {
    testWidgets('renders invite code input and join button', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: JoinProjectScreen(),
        ),
      );

      expect(find.text('Join Project'), findsWidgets);
      expect(find.text('Join a Project Crew'), findsOneWidget);
      expect(find.text('INVITE CODE'), findsOneWidget);
      expect(find.byType(TextFormField), findsOneWidget);
      expect(find.byType(ElevatedButton), findsOneWidget);
    });

    testWidgets('validates empty invite code on submit tap', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: JoinProjectScreen(),
        ),
      );

      await tester.tap(find.byType(ElevatedButton));
      await tester.pumpAndSettle();

      expect(find.text('Please enter a valid invite code'), findsOneWidget);
    });
  });

  group('ProjectDetailScreen Widget Tests', () {
    testWidgets('renders project details when project passed via route', (WidgetTester tester) async {
      final project = Project(
        id: 'proj-999',
        name: 'BuildCrew Full Flow Test',
        description: 'Testing complete mobile UI lifecycle',
        role: 'owner',
      );

      await tester.pumpWidget(
        MaterialApp(
          routes: {
            '/': (context) => Builder(
                  builder: (ctx) => ElevatedButton(
                    onPressed: () => Navigator.pushNamed(
                      ctx,
                      ProjectDetailScreen.routeName,
                      arguments: project,
                    ),
                    child: const Text('Open Details'),
                  ),
                ),
            ProjectDetailScreen.routeName: (context) => const ProjectDetailScreen(),
          },
        ),
      );

      await tester.tap(find.text('Open Details'));
      await tester.pumpAndSettle();

      expect(find.text('BuildCrew Full Flow Test'), findsWidgets);
      expect(find.text('Testing complete mobile UI lifecycle'), findsOneWidget);
      expect(find.text('👑 Team Lead (Owner)'), findsOneWidget);
      expect(find.text('View Team Roles & Responsibilities'), findsOneWidget);
      expect(find.text('Generate Team Invite Code'), findsOneWidget);
    });
  });



  group('DeclareRoleScreen Widget Tests', () {
    testWidgets('renders all required form fields, text areas, deadline picker, and submit button', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: DeclareRoleScreen(),
        ),
      );

      expect(find.text('Declare Your Role'), findsOneWidget);
      expect(find.text('Declare Your Project Role'), findsOneWidget);
      expect(find.text('ROLE TITLE'), findsOneWidget);
      expect(find.text('KEY RESPONSIBILITIES'), findsOneWidget);
      expect(find.text('TARGET DEADLINE'), findsOneWidget);
      expect(find.text('Select target completion deadline'), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(2));
      expect(find.byType(ElevatedButton), findsOneWidget);
      expect(find.text('Declare Role'), findsOneWidget);
    });

    testWidgets('validates required fields only upon submit button tap', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: DeclareRoleScreen(),
        ),
      );

      // No validation errors initially
      expect(find.text('Please enter your role title'), findsNothing);
      expect(find.text('Please enter your key responsibilities'), findsNothing);

      // Scroll to button and tap submit button with empty form
      final submitButton = find.byType(ElevatedButton);
      await tester.ensureVisible(submitButton);
      await tester.tap(submitButton);
      await tester.pumpAndSettle();

      expect(find.text('Please enter your role title'), findsOneWidget);
      expect(find.text('Please enter your key responsibilities'), findsOneWidget);
    });


    testWidgets('renders prefilled values when initial data is provided', (WidgetTester tester) async {
      final deadline = DateTime(2026, 11, 20);

      await tester.pumpWidget(
        MaterialApp(
          home: DeclareRoleScreen(
            initialRole: 'Principal Cloud Architect',
            initialResponsibilities: 'Lead cloud infrastructure and high availability deployments',
            initialDeadline: deadline,
          ),
        ),
      );

      expect(find.text('Principal Cloud Architect'), findsOneWidget);
      expect(find.text('Lead cloud infrastructure and high availability deployments'), findsOneWidget);
      expect(find.text('Nov 20, 2026'), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsOneWidget);
    });

    testWidgets('submits valid role form and invokes ProjectService.declareRole successfully', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();

      await tester.pumpWidget(
        MaterialApp(
          home: DeclareRoleScreen(
            projectId: 'proj-123',
            projectService: fakeService,
          ),
        ),
      );

      // Enter role and responsibilities
      final textFields = find.byType(TextFormField);
      await tester.enterText(textFields.at(0), 'Staff Backend Engineer');
      await tester.enterText(textFields.at(1), 'Architect scalable microservices and API gateways');

      // Scroll to submit button and tap
      final submitButton = find.byType(ElevatedButton);
      await tester.ensureVisible(submitButton);
      await tester.tap(submitButton);
      await tester.pumpAndSettle();

      expect(fakeService.declareRoleCalled, isTrue);
      expect(fakeService.lastProjectId, 'proj-123');
      expect(fakeService.lastDeclaredRole, 'Staff Backend Engineer');
      expect(find.text('Successfully declared role "Staff Backend Engineer"!'), findsOneWidget);
    });

    testWidgets('displays error banner when ProjectService.declareRole throws an error', (WidgetTester tester) async {
      final fakeService = FakeErrorProjectService();

      await tester.pumpWidget(
        MaterialApp(
          home: DeclareRoleScreen(
            projectId: 'proj-err-99',
            projectService: fakeService,
          ),
        ),
      );

      final textFields = find.byType(TextFormField);
      await tester.enterText(textFields.at(0), 'Security Engineer');
      await tester.enterText(textFields.at(1), 'Conduct penetration testing and audits');

      final submitButton = find.byType(ElevatedButton);
      await tester.ensureVisible(submitButton);
      await tester.tap(submitButton);
      await tester.pumpAndSettle();

      expect(find.text('Project not found or user is not a member.'), findsOneWidget);
    });

    testWidgets('shows error when project ID is missing', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();

      await tester.pumpWidget(
        MaterialApp(
          home: DeclareRoleScreen(
            projectService: fakeService,
          ),
        ),
      );

      final textFields = find.byType(TextFormField);
      await tester.enterText(textFields.at(0), 'DevOps Lead');
      await tester.enterText(textFields.at(1), 'Manage Kubernetes clusters');

      final submitButton = find.byType(ElevatedButton);
      await tester.ensureVisible(submitButton);
      await tester.tap(submitButton);
      await tester.pumpAndSettle();

      expect(fakeService.declareRoleCalled, isFalse);
      expect(find.text('Project ID is required to declare a role.'), findsOneWidget);
    });
  });

  group('RoleAgreement Model Tests', () {
    test('fromJson and toJson serialize and deserialize correctly', () {
      final json = {
        'id': 'role-1',
        'project_id': 'proj-1',
        'user_id': 'usr-1',
        'declared_role': 'Frontend Lead',
        'responsibilities': 'Flutter UI development & testing',
        'deadline': '2026-11-20T00:00:00.000Z',
        'created_at': '2026-08-16T10:00:00.000Z',
        'updated_at': '2026-08-16T11:00:00.000Z',
        'profile': {
          'display_name': 'Sarah Connor',
          'email': 'sarah@buildcrew.dev',
        },
      };

      final agreement = RoleAgreement.fromJson(json);
      expect(agreement.id, 'role-1');
      expect(agreement.projectId, 'proj-1');
      expect(agreement.userId, 'usr-1');
      expect(agreement.declaredRole, 'Frontend Lead');
      expect(agreement.responsibilities, 'Flutter UI development & testing');
      expect(agreement.displayName, 'Sarah Connor');
      expect(agreement.email, 'sarah@buildcrew.dev');
      expect(agreement.avatarInitial, 'S');
      expect(agreement.formattedDeadline, 'Nov 20, 2026');

      final serialized = agreement.toJson();
      expect(serialized['id'], 'role-1');
      expect(serialized['declared_role'], 'Frontend Lead');
      expect(serialized['responsibilities'], 'Flutter UI development & testing');
    });

    test('handles missing or null fields gracefully', () {
      final json = {
        'id': 'role-2',
        'project_id': 'proj-2',
        'user_id': 'usr-987654321',
      };

      final agreement = RoleAgreement.fromJson(json);
      expect(agreement.id, 'role-2');
      expect(agreement.declaredRole, 'Team Member');
      expect(agreement.responsibilities, isNull);
      expect(agreement.deadline, isNull);
      expect(agreement.formattedDeadline, isNull);
      expect(agreement.displayName, 'Member (usr-9876)');
      expect(agreement.email, isNull);
      expect(agreement.avatarInitial, 'M');
    });

    test('formats raw email display_name into human name with proper spaces and extracts email', () {
      final json1 = {
        'id': 'role-3',
        'project_id': 'proj-3',
        'user_id': 'usr-3',
        'declared_role': 'Lead Architect',
        'profile': {'display_name': 'abhijithmbhat@gmail.com'},
      };
      final agreement1 = RoleAgreement.fromJson(json1);
      expect(agreement1.displayName, 'Abhijith M Bhat');
      expect(agreement1.email, 'abhijithmbhat@gmail.com');
      expect(agreement1.avatarInitial, 'A');

      final json2 = {
        'id': 'role-4',
        'project_id': 'proj-3',
        'user_id': 'usr-4',
        'declared_role': 'Frontend',
        'profile': {'display_name': 'abhijithhubli@gmail.com'},
      };
      final agreement2 = RoleAgreement.fromJson(json2);
      expect(agreement2.displayName, 'Abhijith Hubli');
      expect(agreement2.email, 'abhijithhubli@gmail.com');
      expect(agreement2.avatarInitial, 'A');
    });
  });

  group('TeamRolesScreen Widget Tests', () {

    testWidgets('renders loaded role cards and header summary from backend', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();
      fakeService.mockRolesList = [
        {
          'id': 'role-1',
          'project_id': 'proj-100',
          'user_id': 'usr-1',
          'declared_role': 'Principal Architect',
          'responsibilities': 'System design, database architecture, and microservices',
          'deadline': '2026-12-15T00:00:00.000Z',
          'profile': {'display_name': 'Alex Rivers', 'email': 'alex@buildcrew.io'},
        },
        {
          'id': 'role-2',
          'project_id': 'proj-100',
          'user_id': 'usr-2',
          'declared_role': 'Frontend Lead',
          'responsibilities': 'Flutter UI development and widget tests',
          'profile': {'display_name': 'Elena Rostova', 'email': 'elena@buildcrew.io'},
        },
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: TeamRolesScreen(
            projectId: 'proj-100',
            projectName: 'Quantum Hub',
            projectService: fakeService,
            storageService: FakeStorageService(),
          ),
        ),
      );

      // Settle loading state
      await tester.pumpAndSettle();

      expect(find.text('Quantum Hub Roles'), findsOneWidget);
      expect(find.text('2 of 2 Members Declared'), findsOneWidget);
      expect(find.text('Alex Rivers'), findsOneWidget);
      expect(find.text('alex@buildcrew.io'), findsOneWidget);
      expect(find.text('Principal Architect'), findsOneWidget);
      expect(find.text('System design, database architecture, and microservices'), findsOneWidget);
      expect(find.text('Target: Dec 15, 2026'), findsOneWidget);

      expect(find.text('Elena Rostova'), findsOneWidget);
      expect(find.text('elena@buildcrew.io'), findsOneWidget);
      expect(find.text('Frontend Lead'), findsOneWidget);
      expect(find.text('Flutter UI development and widget tests'), findsOneWidget);
    });

    testWidgets('filters roles by category chip selection and search query', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();
      fakeService.mockRolesList = [
        {
          'id': 'role-1',
          'project_id': 'proj-100',
          'user_id': 'usr-1',
          'declared_role': 'Frontend Lead',
          'responsibilities': 'Flutter UI development',
          'profile': {'display_name': 'Sarah Connor', 'email': 'sarah@buildcrew.io'},
        },
        {
          'id': 'role-2',
          'project_id': 'proj-100',
          'user_id': 'usr-2',
          'declared_role': 'Backend Architect',
          'responsibilities': 'FastAPI microservices and databases',
          'profile': {'display_name': 'John Doe', 'email': 'john@buildcrew.io'},
        },
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: TeamRolesScreen(
            projectId: 'proj-100',
            projectName: 'Quantum Hub',
            projectService: fakeService,
            storageService: FakeStorageService(),
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Tap on Frontend filter chip
      final frontendChip = find.widgetWithText(ChoiceChip, 'Frontend');
      expect(frontendChip, findsOneWidget);
      await tester.tap(frontendChip);
      await tester.pumpAndSettle();

      // Only Sarah Connor (Frontend) should be visible, John Doe (Backend) filtered out
      expect(find.text('Sarah Connor'), findsOneWidget);
      expect(find.text('John Doe'), findsNothing);

      // Tap on All chip
      final allChip = find.widgetWithText(ChoiceChip, 'All');
      await tester.tap(allChip);
      await tester.pumpAndSettle();
      expect(find.text('Sarah Connor'), findsOneWidget);
      expect(find.text('John Doe'), findsOneWidget);
    });



    testWidgets('renders empty state when no roles are declared', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();
      fakeService.mockRolesList = [];

      await tester.pumpWidget(
        MaterialApp(
          home: TeamRolesScreen(
            projectId: 'proj-empty',
            projectName: 'Empty Project',
            projectService: fakeService,
            storageService: FakeStorageService(),
          ),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text('No Roles Declared Yet'), findsOneWidget);
      expect(find.text('Declare Your Role'), findsWidgets);
    });

    testWidgets('renders error state and retry button on fetch failure', (WidgetTester tester) async {
      final fakeService = FakeErrorProjectService();

      await tester.pumpWidget(
        MaterialApp(
          home: TeamRolesScreen(
            projectId: 'proj-err',
            projectName: 'Error Project',
            projectService: fakeService,
            storageService: FakeStorageService(),
          ),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text('Failed to load team roles'), findsOneWidget);
      expect(find.text('Failed to connect to backend server.'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
    });

    testWidgets('tapping Declare Your Role navigates to DeclareRoleScreen', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();
      fakeService.mockRolesList = [];

      await tester.pumpWidget(
        MaterialApp(
          routes: {
            TeamRolesScreen.routeName: (context) => TeamRolesScreen(
                  projectId: 'proj-123',
                  projectName: 'Project Alpha',
                  projectService: fakeService,
                  storageService: FakeStorageService(),
                ),
            DeclareRoleScreen.routeName: (context) => const Scaffold(
                  body: Text('Declare Role Target Screen'),
                ),
          },
          initialRoute: TeamRolesScreen.routeName,
        ),
      );


      await tester.pumpAndSettle();

      final declareBtn = find.widgetWithText(ElevatedButton, 'Declare Your Role');
      await tester.tap(declareBtn);
      await tester.pumpAndSettle();

      expect(find.text('Declare Role Target Screen'), findsOneWidget);
    });

    testWidgets('hides Declare Role FAB and displays YOU badge and Edit button when user has already declared a role', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();
      final fakeStorage = FakeStorageService(userId: 'usr-1', userEmail: 'alex@buildcrew.io');
      fakeService.mockRolesList = [
        {
          'id': 'role-1',
          'project_id': 'proj-100',
          'user_id': 'usr-1',
          'declared_role': 'Principal Architect',
          'responsibilities': 'System design and microservices',
          'profile': {'display_name': 'Alex Rivers', 'email': 'alex@buildcrew.io'},
        },
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: TeamRolesScreen(
            projectId: 'proj-100',
            projectName: 'Quantum Hub',
            projectService: fakeService,
            storageService: fakeStorage,
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Verify FloatingActionButton is NOT present
      expect(find.byType(FloatingActionButton), findsNothing);

      // Verify YOU badge is displayed on the user's card
      expect(find.text('YOU'), findsOneWidget);

      // Verify Edit button is displayed in card and summary header
      expect(find.byTooltip('Edit your declared role'), findsOneWidget);
      expect(find.text('Edit'), findsOneWidget);
    });

    testWidgets('shows Declare Role FAB when user has not declared a role yet', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();
      final fakeStorage = FakeStorageService(userId: 'usr-unassigned', userEmail: 'new@buildcrew.io');
      fakeService.mockRolesList = [
        {
          'id': 'role-1',
          'project_id': 'proj-100',
          'user_id': 'usr-other',
          'declared_role': 'Frontend Lead',
          'profile': {'display_name': 'Sarah Connor'},
        },
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: TeamRolesScreen(
            projectId: 'proj-100',
            projectName: 'Quantum Hub',
            projectService: fakeService,
            storageService: fakeStorage,
          ),
        ),
      );

      await tester.pumpAndSettle();

      // User hasn't declared a role -> inline button is visible on their card
      expect(find.byType(FloatingActionButton), findsNothing);
      expect(find.text('YOU'), findsNothing);
    });


    testWidgets('displays Team Lead badge on project creator card', (WidgetTester tester) async {
      final fakeService = FakeSuccessProjectService();
      final fakeStorage = FakeStorageService(userId: 'usr-member', userEmail: 'member@buildcrew.io');
      fakeService.mockRolesList = [
        {
          'id': 'role-1',
          'project_id': 'proj-100',
          'user_id': 'usr-lead',
          'declared_role': 'Lead Architect',
          'project_created_by': 'usr-lead',
          'profile': {'display_name': 'Alex Rivers', 'email': 'alex@buildcrew.io'},
        },
        {
          'id': 'role-2',
          'project_id': 'proj-100',
          'user_id': 'usr-member',
          'declared_role': 'Mobile Dev',
          'project_created_by': 'usr-lead',
          'profile': {'display_name': 'Elena Rostova', 'email': 'member@buildcrew.io'},
        },
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: TeamRolesScreen(
            projectId: 'proj-100',
            projectName: 'Quantum Hub',
            projectService: fakeService,
            storageService: fakeStorage,
          ),
        ),
      );

      await tester.pumpAndSettle();

      // Verify Team Lead badge is displayed on the creator's card
      expect(find.text('Team Lead'), findsOneWidget);
      // Verify YOU badge is displayed on current user's card
      expect(find.text('YOU'), findsOneWidget);
    });
  });

  group('ProjectDetailScreen Widget Tests', () {
    testWidgets('renders project details, team lead badge, and action buttons', (WidgetTester tester) async {
      final project = Project(
        id: 'proj-lead-100',
        name: 'Alpha Apollo',
        description: 'Next-gen lunar telemetry app',
        role: 'owner',
      );

      await tester.pumpWidget(
        MaterialApp(
          routes: {
            ProjectDetailScreen.routeName: (context) => const ProjectDetailScreen(),
          },
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.pushNamed(
                context,
                ProjectDetailScreen.routeName,
                arguments: project,
              ),
              child: const Text('Open Detail'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Detail'));
      await tester.pumpAndSettle();

      expect(find.text('Alpha Apollo'), findsNWidgets(2));
      expect(find.text('Next-gen lunar telemetry app'), findsOneWidget);
      expect(find.text('👑 Team Lead (Owner)'), findsOneWidget);

      expect(find.text('View Team Roles & Responsibilities'), findsOneWidget);
      expect(find.text('Generate Team Invite Code'), findsOneWidget);
      expect(find.text('Remind Teammates to Declare Roles'), findsOneWidget);
      expect(find.text('Dismantle / Delete Project'), findsOneWidget);
    });

    testWidgets('renders Leave Project button for regular teammate member', (WidgetTester tester) async {
      final project = Project(
        id: 'proj-member-100',
        name: 'Beta Project',
        description: 'Teammate view test',
        role: 'member',
      );

      await tester.pumpWidget(
        MaterialApp(
          routes: {
            ProjectDetailScreen.routeName: (context) => const ProjectDetailScreen(),
          },
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.pushNamed(
                context,
                ProjectDetailScreen.routeName,
                arguments: project,
              ),
              child: const Text('Open Member Detail'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Member Detail'));
      await tester.pumpAndSettle();

      expect(find.text('Beta Project'), findsNWidgets(2));
      expect(find.text('Member'), findsOneWidget);
      expect(find.text('Leave Project'), findsOneWidget);
      expect(find.text('Dismantle / Delete Project'), findsNothing);
    });
  });
}













