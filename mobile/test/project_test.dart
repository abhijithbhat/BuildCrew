import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/screens/create_project_screen.dart';
import 'package:mobile/screens/invite_teammate_screen.dart';
import 'package:mobile/screens/join_project_screen.dart';
import 'package:mobile/screens/my_projects_screen.dart';
import 'package:mobile/screens/project_detail_screen.dart';
import 'package:mobile/widgets/project_card.dart';





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
      expect(find.text('Owner'), findsOneWidget);
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
      expect(find.text('You are the Owner'), findsOneWidget);
      expect(find.text('Generate Team Invite Code'), findsOneWidget);
    });
  });
}





