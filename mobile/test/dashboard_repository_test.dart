import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/services/dashboard_repository.dart';

import 'helpers/fake_home_project_service.dart';
import 'helpers/mem_storage.dart';

class _FailingService extends FakeHomeProjectService {
  @override
  Future<List<Project>> listProjects({bool includeArchived = false}) async =>
      throw Exception('offline');
}

void main() {
  final List<Project> twoProjects = <Project>[
    Project(id: 'p1', name: 'Alpha', role: 'owner'),
    Project(id: 'p2', name: 'Beta', role: 'member'),
  ];

  test('refresh publishes names first, then hydrated cards, and saves a cache', () async {
    final DashboardRepository repo = DashboardRepository.forTest();
    final MemStorage storage = MemStorage();
    final List<DashboardSnapshot> seen = <DashboardSnapshot>[];
    repo.latest.addListener(() {
      final DashboardSnapshot? s = repo.latest.value;
      if (s != null) seen.add(s);
    });

    final DashboardRefreshResult result = await repo.refresh(
      projects: FakeHomeProjectService(projects: twoProjects, pendingCount: 1),
      storage: storage,
    );

    expect(result, DashboardRefreshResult.ok);
    expect(seen.first.cards.every((DashboardCard c) => !c.hydrated), isTrue);
    expect(seen.last.cards.every((DashboardCard c) => c.hydrated), isTrue);
    expect(seen.last.cards.first.members.length, 2);
    expect(seen.last.pendingCount, 1);
    expect(storage.kv.containsKey(DashboardRepository.cacheKey), isTrue);
  });

  test('loadCached returns the saved snapshot for the same user and wipes it for another', () async {
    final MemStorage storage = MemStorage();
    await DashboardRepository.forTest().refresh(
      projects: FakeHomeProjectService(projects: twoProjects),
      storage: storage,
    );

    final DashboardSnapshot? cached = await DashboardRepository.forTest().loadCached(storage);
    expect(cached, isNotNull);
    expect(cached!.cards.map((DashboardCard c) => c.project.name), <String>['Alpha', 'Beta']);

    final MemStorage other = MemStorage(userId: 'someone-else')..kv.addAll(storage.kv);
    expect(await DashboardRepository.forTest().loadCached(other), isNull);
    expect(other.kv.containsKey(DashboardRepository.cacheKey), isFalse);
  });

  test('a failed refresh keeps the last snapshot', () async {
    final DashboardRepository repo = DashboardRepository.forTest();
    final MemStorage storage = MemStorage();
    await repo.refresh(projects: FakeHomeProjectService(projects: twoProjects), storage: storage);
    final DashboardSnapshot? before = repo.latest.value;

    final DashboardRefreshResult result =
        await repo.refresh(projects: _FailingService(), storage: storage);

    expect(result, DashboardRefreshResult.failed);
    expect(identical(repo.latest.value, before), isTrue);
  });

  test('waitForFirstSnapshot times out without data and returns fast with data', () async {
    final DashboardRepository repo = DashboardRepository.forTest();
    final Stopwatch sw = Stopwatch()..start();
    await repo.waitForFirstSnapshot(timeout: const Duration(milliseconds: 80));
    expect(sw.elapsedMilliseconds, greaterThanOrEqualTo(70));

    await repo.refresh(
      projects: FakeHomeProjectService(projects: twoProjects),
      storage: MemStorage(),
    );
    sw
      ..reset()
      ..start();
    await repo.waitForFirstSnapshot(timeout: const Duration(seconds: 5));
    expect(sw.elapsedMilliseconds, lessThan(200));
  });
}
