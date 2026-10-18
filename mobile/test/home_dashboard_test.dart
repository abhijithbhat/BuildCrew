import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/screens/home_screen.dart';
import 'package:mobile/services/dashboard_repository.dart';

import 'helpers/fake_home_project_service.dart';
import 'helpers/mem_storage.dart';

class _GatedService extends FakeHomeProjectService {
  _GatedService(this.gate);

  final Completer<List<Project>> gate;

  @override
  Future<List<Project>> listProjects({bool includeArchived = false}) => gate.future;
}

class _OfflineService extends FakeHomeProjectService {
  @override
  Future<List<Project>> listProjects({bool includeArchived = false}) async =>
      throw Exception('offline');
}

DashboardSnapshot _snapshot() => DashboardSnapshot(
      userId: 'u1',
      pendingCount: 2,
      fetchedAt: DateTime(2026, 10, 18),
      cards: <DashboardCard>[
        DashboardCard(
          project: Project(id: 'p1', name: 'Hack Team', role: 'owner'),
          hydrated: true,
          verified: 3,
          waiting: 1,
          members: const <DashboardMember>[
            DashboardMember('Sam K', null),
            DashboardMember('Veekshith K', null),
          ],
        ),
      ],
    );

Widget _home({
  required DashboardRepository repo,
  FakeHomeProjectService? service,
}) {
  return MaterialApp(
    home: HomeScreen(
      userName: 'Alice Developer',
      repository: repo,
      storageService: MemStorage(),
      projectService: service ?? FakeHomeProjectService(),
    ),
  );
}

void main() {
  setUp(() {
    final TestWidgetsFlutterBinding binding = TestWidgetsFlutterBinding.ensureInitialized();
    binding.platformDispatcher.views.first.physicalSize = const Size(800, 1400);
    binding.platformDispatcher.views.first.devicePixelRatio = 1.0;
  });

  tearDown(() {
    final TestWidgetsFlutterBinding binding = TestWidgetsFlutterBinding.ensureInitialized();
    binding.platformDispatcher.views.first.resetPhysicalSize();
    binding.platformDispatcher.views.first.resetDevicePixelRatio();
  });

  testWidgets('prefetched data is on screen on the very first frame', (tester) async {
    final DashboardRepository repo = DashboardRepository.forTest()..latest.value = _snapshot();
    await tester.pumpWidget(
      _home(repo: repo, service: _GatedService(Completer<List<Project>>())),
    );

    // Exactly one frame: the network has not answered yet.
    expect(find.text('Hack Team'), findsWidgets);
    expect(find.text('Active'), findsOneWidget);
    expect(find.text('2 teammates are waiting for your review'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsNothing);
  });

  testWidgets('with no data yet, every box is filled with real text', (tester) async {
    final Completer<List<Project>> gate = Completer<List<Project>>();
    await tester.pumpWidget(
      _home(repo: DashboardRepository.forTest(), service: _GatedService(gate)),
    );
    await tester.pump();

    expect(find.text('Getting your passport ready…'), findsOneWidget);
    expect(find.text('Loading your projects…'), findsOneWidget);

    gate.complete(<Project>[Project(id: 'p1', name: 'Hack Team', role: 'owner')]);
    await tester.pumpAndSettle();

    expect(find.text('Getting your passport ready…'), findsNothing);
    expect(find.text('Hack Team'), findsWidgets);
  });

  testWidgets('offline refresh keeps the saved content and says so', (tester) async {
    final DashboardRepository repo = DashboardRepository.forTest()..latest.value = _snapshot();
    await tester.pumpWidget(_home(repo: repo, service: _OfflineService()));
    await tester.pumpAndSettle();

    expect(find.text('Hack Team'), findsWidgets);
    expect(find.textContaining('Offline'), findsOneWidget);
  });

  testWidgets('empty state: greeting, quick actions and a start-your-passport hero', (tester) async {
    await tester.pumpWidget(_home(repo: DashboardRepository.forTest()));
    await tester.pumpAndSettle();

    expect(find.text('Hello, Alice'), findsOneWidget);
    expect(find.text('Start your contribution passport'), findsOneWidget);
    expect(find.text('Join Team'), findsOneWidget);
    expect(find.text('Create Project'), findsOneWidget);
    expect(find.text('Connect GitHub'), findsOneWidget);
    expect(find.text('Team Ledger'), findsOneWidget);
    expect(find.byKey(const Key('home_settings_btn')), findsOneWidget);
    expect(find.byKey(const Key('home_pending_banner')), findsNothing);
  });

  testWidgets('with a project and pending reviews: banner, badge and project card', (tester) async {
    await tester.pumpWidget(
      _home(
        repo: DashboardRepository.forTest(),
        service: FakeHomeProjectService(
          projects: <Project>[Project(id: 'p1', name: 'Hack Team', role: 'owner')],
          pendingCount: 2,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('2 teammates are waiting for your review'), findsOneWidget);
    expect(find.text('Needs verification'), findsOneWidget); // nothing verified yet
    expect(find.text('Hack Team'), findsWidgets);
    expect(find.text('Team Lead'), findsOneWidget);
    expect(find.byKey(const Key('home_view_passport_btn')), findsOneWidget);
  });
}
