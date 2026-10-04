import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/screens/my_contributions_screen.dart';
import 'package:mobile/services/project_service.dart';
import 'package:mobile/services/storage_service.dart';
import 'package:mobile/theme/app_colors.dart';

class FakeResponsiveProjectService extends Fake implements ProjectService {
  final List<Contribution> mockContributions;

  FakeResponsiveProjectService({this.mockContributions = const []});

  @override
  Future<List<Contribution>> listContributions(
    String projectId, {
    String? status,
    String? contributor,
    String? category,
  }) async {
    return mockContributions;
  }
}

class FakeResponsiveStorageService extends Fake implements StorageService {
  @override
  Future<String?> getAccessToken() async => 'test-token';

  @override
  Future<String?> getUserId() async => 'user-123';

  @override
  Future<String?> getUserName() async => 'Dev User';

  @override
  Future<String?> getUserEmail() async => 'dev@example.com';
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final List<Contribution> sampleContributions = [
    Contribution(
      id: 'contrib-1',
      project: 'proj-1',
      contributor: 'user-123',
      contributorName: 'Dev User',
      category: 'code',
      title: 'Built Authentication Engine',
      description: 'Implemented multi-tenant JWT & OAuth flow',
      verificationStatus: 'verified',
      evidenceLink: 'https://github.com/org/repo/pull/1',
      createdAt: DateTime.now().subtract(const Duration(days: 2)),
    ),
    Contribution(
      id: 'contrib-2',
      project: 'proj-1',
      contributor: 'user-123',
      contributorName: 'Dev User',
      category: 'design',
      title: 'Figma Design System',
      description: 'Created UI components and token system',
      verificationStatus: 'self-declared',
      evidenceLink: 'https://figma.com/file/123',
      createdAt: DateTime.now().subtract(const Duration(days: 1)),
    ),
  ];

  final sampleProject = Project(
    id: 'proj-1',
    name: 'BuildCrew Mobile',
    description: 'Production team app',
    createdBy: 'user-123',
    createdAt: DateTime.now(),
  );

  group('Responsive 560px Max-Width Layout Tests', () {
    testWidgets('MaterialApp builder constrains width to 560px on wide tablet display', (tester) async {
      // Simulate Tablet Landscape (1280 x 800)
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => ColoredBox(
            color: AppColors.champagne,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: child,
              ),
            ),
          ),
          home: const Scaffold(
            body: Center(child: Text('Tablet Test Content')),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final constrainedBoxFinder = find.byType(ConstrainedBox);
      expect(constrainedBoxFinder, findsWidgets);

      final matchingBox = tester.widgetList<ConstrainedBox>(constrainedBoxFinder).firstWhere(
        (b) => b.constraints.maxWidth == 560,
      );
      expect(matchingBox.constraints.maxWidth, 560);

      final renderBox = tester.renderObject<RenderBox>(find.byType(Scaffold));
      expect(renderBox.size.width, lessThanOrEqualTo(560));
      expect(tester.takeException(), isNull);
    });

    testWidgets('MaterialApp builder maintains full width when screen is smaller than 560px', (tester) async {
      // Simulate compact phone portrait (390 x 844)
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => ColoredBox(
            color: AppColors.champagne,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: child,
              ),
            ),
          ),
          home: const Scaffold(
            body: Center(child: Text('Phone Content')),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final renderBox = tester.renderObject<RenderBox>(find.byType(Scaffold));
      expect(renderBox.size.width, equals(390));
      expect(tester.takeException(), isNull);
    });
  });

  group('Device Orientation & Display Simulation Tests', () {
    // 1. Tablet Landscape (1280 x 800)
    testWidgets('MyContributionsScreen renders cleanly on Tablet Landscape', (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => ColoredBox(
            color: AppColors.champagne,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: child,
              ),
            ),
          ),
          home: MyContributionsScreen(
            projectId: 'proj-1',
            project: sampleProject,
            projectService: FakeResponsiveProjectService(mockContributions: sampleContributions),
            storageService: FakeResponsiveStorageService(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(SafeArea), findsWidgets);
      expect(find.text('My Contributions'), findsOneWidget);
      expect(find.text('Built Authentication Engine'), findsOneWidget);
      expect(find.text('Figma Design System'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    // 2. Tablet Portrait (800 x 1280)
    testWidgets('MyContributionsScreen renders cleanly on Tablet Portrait', (tester) async {
      tester.view.physicalSize = const Size(800, 1280);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => ColoredBox(
            color: AppColors.champagne,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: child,
              ),
            ),
          ),
          home: MyContributionsScreen(
            projectId: 'proj-1',
            project: sampleProject,
            projectService: FakeResponsiveProjectService(mockContributions: sampleContributions),
            storageService: FakeResponsiveStorageService(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(SafeArea), findsWidgets);
      expect(find.text('My Contributions'), findsOneWidget);
      expect(find.text('Built Authentication Engine'), findsOneWidget);
      expect(find.text('Figma Design System'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    // 3. Foldable Unfolded Landscape (841 x 673)
    testWidgets('MyContributionsScreen renders cleanly on Foldable Landscape', (tester) async {
      tester.view.physicalSize = const Size(841, 673);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => ColoredBox(
            color: AppColors.champagne,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: child,
              ),
            ),
          ),
          home: MyContributionsScreen(
            projectId: 'proj-1',
            project: sampleProject,
            projectService: FakeResponsiveProjectService(mockContributions: sampleContributions),
            storageService: FakeResponsiveStorageService(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(SafeArea), findsWidgets);
      expect(find.text('My Contributions'), findsOneWidget);
      expect(find.text('Built Authentication Engine'), findsOneWidget);
      expect(find.text('Figma Design System'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    // 4. Foldable Unfolded Portrait (673 x 841)
    testWidgets('MyContributionsScreen renders cleanly on Foldable Portrait', (tester) async {
      tester.view.physicalSize = const Size(673, 841);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) => ColoredBox(
            color: AppColors.champagne,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: child,
              ),
            ),
          ),
          home: MyContributionsScreen(
            projectId: 'proj-1',
            project: sampleProject,
            projectService: FakeResponsiveProjectService(mockContributions: sampleContributions),
            storageService: FakeResponsiveStorageService(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(SafeArea), findsWidgets);
      expect(find.text('My Contributions'), findsOneWidget);
      expect(find.text('Built Authentication Engine'), findsOneWidget);
      expect(find.text('Figma Design System'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
