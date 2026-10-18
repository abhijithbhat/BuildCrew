import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../models/contribution.dart';
import '../models/project.dart';
import '../models/role_agreement.dart';
import 'project_service.dart';
import 'storage_service.dart';

/// Teammate shown in an avatar stack.
class DashboardMember {
  const DashboardMember(this.name, this.avatarUrl);

  final String name;
  final String? avatarUrl;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'n': name,
        if (avatarUrl != null) 'a': avatarUrl,
      };

  factory DashboardMember.fromJson(Map<String, dynamic> j) =>
      DashboardMember((j['n'] ?? 'Member').toString(), j['a']?.toString());
}

/// One project on the Home dashboard, with my verification counts.
class DashboardCard {
  const DashboardCard({
    required this.project,
    this.members = const <DashboardMember>[],
    this.hydrated = false,
    this.verified = 0,
    this.waiting = 0,
    this.disputed = 0,
  });

  final Project project;
  final List<DashboardMember> members;

  /// True once members and my contribution counts were fetched.
  final bool hydrated;
  final int verified;
  final int waiting;
  final int disputed;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': project.id,
        'name': project.name,
        if (project.role != null) 'role': project.role,
        'members': members.map((DashboardMember m) => m.toJson()).toList(),
        'hydrated': hydrated,
        'verified': verified,
        'waiting': waiting,
        'disputed': disputed,
      };

  factory DashboardCard.fromJson(Map<String, dynamic> j) {
    final Object? raw = j['members'];
    return DashboardCard(
      project: Project(
        id: (j['id'] ?? '').toString(),
        name: (j['name'] ?? '').toString(),
        role: j['role']?.toString(),
      ),
      members: raw is List
          ? raw
              .whereType<Map>()
              .map((Map m) => DashboardMember.fromJson(Map<String, dynamic>.from(m)))
              .toList()
          : const <DashboardMember>[],
      hydrated: j['hydrated'] == true,
      verified: (j['verified'] as num?)?.toInt() ?? 0,
      waiting: (j['waiting'] as num?)?.toInt() ?? 0,
      disputed: (j['disputed'] as num?)?.toInt() ?? 0,
    );
  }
}

class DashboardSnapshot {
  const DashboardSnapshot({
    required this.userId,
    required this.cards,
    required this.pendingCount,
    required this.fetchedAt,
  });

  final String? userId;
  final List<DashboardCard> cards;
  final int pendingCount;
  final DateTime fetchedAt;

  String encode() => jsonEncode(<String, dynamic>{
        'v': 1,
        'uid': userId,
        'pending': pendingCount,
        'at': fetchedAt.toIso8601String(),
        'cards': cards.map((DashboardCard c) => c.toJson()).toList(),
      });

  static DashboardSnapshot? decode(String raw) {
    try {
      final Object? j = jsonDecode(raw);
      if (j is! Map || j['v'] != 1) return null;
      final Object? cards = j['cards'];
      return DashboardSnapshot(
        userId: j['uid']?.toString(),
        pendingCount: (j['pending'] as num?)?.toInt() ?? 0,
        fetchedAt: DateTime.tryParse((j['at'] ?? '').toString()) ?? DateTime.now(),
        cards: cards is List
            ? cards
                .whereType<Map>()
                .map((Map c) => DashboardCard.fromJson(Map<String, dynamic>.from(c)))
                .toList()
            : const <DashboardCard>[],
      );
    } catch (_) {
      return null;
    }
  }
}

enum DashboardRefreshResult { ok, partial, failed }

/// Single source of truth for the Home dashboard.
///
/// * [latest] holds the newest snapshot (memory), so Home paints on its first
///   frame when the splash already prefetched it.
/// * The snapshot is also stored (encrypted) with [StorageService], so a cold
///   start paints saved data immediately and refreshes in the background.
/// * Network work is split: round 1 (projects + pending reviews) publishes
///   right away; round 2 (members and my counts) publishes card by card.
class DashboardRepository {
  DashboardRepository._();

  @visibleForTesting
  DashboardRepository.forTest();

  static final DashboardRepository instance = DashboardRepository._();

  static const String cacheKey = 'dashboard_snapshot_v1';

  final ValueNotifier<DashboardSnapshot?> latest = ValueNotifier<DashboardSnapshot?>(null);
  Future<DashboardRefreshResult>? _inflight;

  /// Forget everything held in memory (call on logout).
  void clearMemory() {
    latest.value = null;
    _inflight = null;
  }

  Future<String?> _userId(StorageService storage) async {
    String? uid;
    try {
      uid = await storage.getUserId();
    } catch (_) {}
    if (uid == null || uid.isEmpty) {
      try {
        uid = Supabase.instance.client.auth.currentUser?.id;
      } catch (_) {}
    }
    return (uid == null || uid.isEmpty) ? null : uid;
  }

  /// Memory first, then secure storage. Ignores data saved for another user.
  Future<DashboardSnapshot?> loadCached(StorageService storage) async {
    final String? uid = await _userId(storage);
    final DashboardSnapshot? mem = latest.value;
    if (mem != null) {
      if (uid == null || mem.userId == uid) return mem;
      latest.value = null; // another account signed in on this device
    }
    final String? raw = await storage.readString(cacheKey);
    if (raw == null) return null;
    final DashboardSnapshot? snap = DashboardSnapshot.decode(raw);
    if (snap == null || uid == null || snap.userId != uid) {
      await storage.deleteString(cacheKey);
      return null;
    }
    latest.value ??= snap;
    return latest.value;
  }

  /// Start loading as early as possible (called while the splash plays).
  Future<void> prefetch({ProjectService? projects, StorageService? storage}) async {
    final StorageService s = storage ?? StorageService();
    await loadCached(s);
    unawaited(refresh(projects: projects ?? ProjectService(), storage: s));
  }

  /// Completes when a snapshot exists (cached or fresh) or after [timeout].
  Future<void> waitForFirstSnapshot({Duration timeout = const Duration(milliseconds: 700)}) async {
    if (latest.value != null) return;
    final Completer<void> done = Completer<void>();
    void listener() {
      if (latest.value != null && !done.isCompleted) done.complete();
    }

    latest.addListener(listener);
    try {
      await done.future.timeout(timeout);
    } on TimeoutException {
      // Navigate anyway; Home shows its own filled "syncing" state.
    } finally {
      latest.removeListener(listener);
    }
  }

  Future<DashboardRefreshResult> refresh({
    required ProjectService projects,
    required StorageService storage,
  }) {
    final Future<DashboardRefreshResult> running = _inflight ??= _refresh(projects, storage)
        .whenComplete(() => _inflight = null);
    return running;
  }

  Future<DashboardRefreshResult> _refresh(ProjectService svc, StorageService storage) async {
    bool projectsFailed = false;
    bool partial = false;

    Future<T> safe<T>(Future<T> task, T fallback) async {
      try {
        return await task;
      } catch (_) {
        partial = true;
        return fallback;
      }
    }

    final String? uid = await _userId(storage);

    // ---- Round 1: projects + pending reviews, in parallel.
    final Future<List<Project>> projectsF = svc.listProjects().catchError((Object _) {
      projectsFailed = true;
      return <Project>[];
    });
    final Future<List<ConfirmationRequest>> pendingF = safe<List<ConfirmationRequest>>(
      svc.getPendingConfirmations(),
      <ConfirmationRequest>[],
    );
    final List<Project> projects = await projectsF;
    final List<ConfirmationRequest> pending = await pendingF;
    if (projectsFailed) return DashboardRefreshResult.failed; // keep whatever is shown

    final DashboardSnapshot? prev = latest.value?.userId == uid ? latest.value : null;
    final Map<String, DashboardCard> prevById = <String, DashboardCard>{
      for (final DashboardCard c in prev?.cards ?? const <DashboardCard>[]) c.project.id: c,
    };

    List<DashboardCard> cards = projects.where((Project p) => p.archivedAt == null).map((Project p) {
      final DashboardCard? old = prevById[p.id];
      return DashboardCard(
        project: p,
        members: old?.members ?? const <DashboardMember>[],
        hydrated: old?.hydrated ?? false,
        verified: old?.verified ?? 0,
        waiting: old?.waiting ?? 0,
        disputed: old?.disputed ?? 0,
      );
    }).toList();

    void publish() {
      latest.value = DashboardSnapshot(
        userId: uid,
        cards: List<DashboardCard>.unmodifiable(cards),
        pendingCount: pending.length,
        fetchedAt: DateTime.now(),
      );
    }

    publish();

    // ---- Round 2: members + my counts for the first three projects.
    final int hydrateCount = cards.length < 3 ? cards.length : 3;
    await Future.wait(
      List<Future<void>>.generate(hydrateCount, (int i) async {
        final DashboardCard card = cards[i];
        final Future<Map<String, dynamic>> detailsF = safe<Map<String, dynamic>>(
          svc.getProjectDetails(card.project.id),
          <String, dynamic>{},
        );
        final Future<List<Contribution>> mineF = uid == null
            ? Future<List<Contribution>>.value(<Contribution>[])
            : safe<List<Contribution>>(
                svc.listContributions(card.project.id, contributor: uid),
                <Contribution>[],
              );
        final Map<String, dynamic> details = await detailsF;
        final List<Contribution> mine = await mineF;

        int verified = 0, waiting = 0, disputed = 0;
        for (final Contribution c in mine) {
          if (c.disputeState == 'disputed' || c.verificationStatus == 'needs-review') {
            disputed++;
          } else if (c.verificationStatus == 'peer-confirmed' ||
              c.verificationStatus == 'confirmed' ||
              c.verificationStatus == 'source-verified') {
            verified++;
          } else {
            waiting++;
          }
        }
        final List<DashboardMember> members = _parseMembers(details);
        cards = List<DashboardCard>.of(cards)
          ..[i] = DashboardCard(
            project: card.project,
            // Keep cached members if this round could not load them.
            members: members.isEmpty ? card.members : members,
            hydrated: true,
            verified: verified,
            waiting: waiting,
            disputed: disputed,
          );
        publish();
      }),
    );

    if (uid != null) {
      await storage.writeString(cacheKey, latest.value!.encode());
    }
    return partial ? DashboardRefreshResult.partial : DashboardRefreshResult.ok;
  }

  static List<DashboardMember> _parseMembers(Map<String, dynamic> details) {
    final Object? proj = details['project'];
    if (proj is! Map) return const <DashboardMember>[];
    final Object? raw = proj['project_members'];
    if (raw is! List) return const <DashboardMember>[];
    final List<DashboardMember> out = <DashboardMember>[];
    for (final Object? m in raw) {
      if (m is! Map) continue;
      final Object? prof = m['profiles'];
      String? name;
      String? avatar;
      if (prof is Map) {
        name = prof['display_name']?.toString();
        avatar = prof['avatar_url']?.toString();
      }
      out.add(
        DashboardMember(
          RoleAgreement.formatEmailToHumanName(name ?? 'Member'),
          (avatar != null && avatar.startsWith('https://')) ? avatar : null,
        ),
      );
    }
    return out;
  }
}
