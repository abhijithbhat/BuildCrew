import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/project.dart';
import '../models/role_agreement.dart';
import '../services/api_client.dart';
import '../services/dashboard_repository.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';
import '../theme/app_colors.dart';
import 'connect_repository_screen.dart';
import 'project_detail_screen.dart';
import 'settings_screen.dart';
import 'team_ledger_screen.dart';

/// Colors used only by the dashboard (all pairs below meet WCAG AA 4.5:1).
class _Ui {
  static const Color card = Colors.white;
  static const Color mint = Color(0xFFD1FAE5);
  static const Color amberBg = Color(0xFFFFF1CC);
  static const Color amberLine = Color(0xFFE8C25A);
  static const Color amberText = Color(0xFF6B4A00);
  static const Color redText = Color(0xFFB42318);
  static const Color redBg = Color(0xFFFEE4E2);
}

/// Executive dashboard: profile header, passport hero card, review banner,
/// quick actions and project cards.
///
/// Data comes from [DashboardRepository]. When the splash already prefetched
/// it, the first frame is fully populated; otherwise the last saved snapshot
/// paints immediately and refreshes in the background. There are no blank
/// placeholder boxes: every state shows real text.
class HomeScreen extends StatefulWidget {
  static const String routeName = '/home';

  final String? userName;
  final StorageService? storageService;
  final ProjectService? projectService;
  final DashboardRepository? repository;

  const HomeScreen({
    super.key,
    this.userName,
    this.storageService,
    this.projectService,
    this.repository,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  late final StorageService _storage;
  late final ProjectService _projects;
  late final DashboardRepository _repo;

  String? _storedName;
  DashboardSnapshot? _snap;
  bool _refreshing = false;
  bool _failedNoData = false;
  bool _offlineStale = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _storage = widget.storageService ?? StorageService();
    _projects = widget.projectService ?? ProjectService();
    _repo = widget.repository ?? DashboardRepository.instance;
    _repo.latest.addListener(_onSnapshot);
    // Already in memory when the splash prefetched it: first frame is filled.
    _snap = _repo.latest.value;
    _bootstrap();
  }

  @override
  void dispose() {
    _repo.latest.removeListener(_onSnapshot);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refresh();
    }
  }

  void _onSnapshot() {
    if (!mounted) return;
    setState(() => _snap = _repo.latest.value);
  }

  Future<void> _bootstrap() async {
    unawaited(_loadName());
    if (_snap == null) {
      final DashboardSnapshot? cached = await _repo.loadCached(_storage);
      if (mounted && cached != null && _snap == null) {
        setState(() => _snap = cached);
      }
    }
    await _refresh();
    unawaited(_refreshIdentity());
  }

  Future<void> _loadName() async {
    try {
      final String? name = await _storage.getUserName();
      if (mounted && name != null && name.trim().isNotEmpty) {
        setState(() => _storedName = name.trim());
      }
    } catch (_) {}
  }

  /// Off the critical path: refresh identity metadata (e.g. a linked GitHub
  /// account) after the dashboard is already on screen.
  Future<void> _refreshIdentity() async {
    try {
      await Supabase.instance.client.auth.getUser();
    } catch (_) {
      return;
    }
    if (mounted) setState(() {});
  }

  Future<void> _refresh() async {
    if (_refreshing) return;
    if (mounted) setState(() => _refreshing = true);
    DashboardRefreshResult result;
    try {
      result = await _repo.refresh(projects: _projects, storage: _storage);
    } catch (_) {
      result = DashboardRefreshResult.failed;
    }
    if (!mounted) return;
    final DashboardSnapshot? latest = _repo.latest.value;
    setState(() {
      _refreshing = false;
      _snap = latest;
      _failedNoData = result == DashboardRefreshResult.failed && latest == null;
      _offlineStale = result == DashboardRefreshResult.failed && latest != null;
    });
  }

  // ------------------------------------------------------------- helpers

  User? _supabaseUser() {
    try {
      return Supabase.instance.client.auth.currentUser;
    } catch (_) {
      return null;
    }
  }

  String? get _avatarUrl {
    final Map<String, dynamic>? meta = _supabaseUser()?.userMetadata;
    final String? v = (meta?['avatar_url'] ?? meta?['picture'])?.toString();
    return (v != null && v.startsWith('https://')) ? v : null;
  }

  String? get _githubLogin {
    final List<UserIdentity>? ids = _supabaseUser()?.identities;
    if (ids == null) return null;
    for (final UserIdentity i in ids) {
      if (i.provider == 'github') {
        final Map<String, dynamic>? data = i.identityData;
        final String? login =
            (data?['user_name'] ?? data?['preferred_username'])?.toString();
        if (login != null && login.isNotEmpty) return login;
      }
    }
    return null;
  }

  String _displayName(BuildContext context) {
    final Object? arg = ModalRoute.of(context)?.settings.arguments;
    final String raw = widget.userName ??
        _storedName ??
        (arg is String ? arg : null) ??
        _supabaseUser()?.userMetadata?['full_name']?.toString() ??
        'User';
    return RoleAgreement.formatEmailToHumanName(raw);
  }

  static String _firstName(String full) {
    final String t = full.trim();
    if (t.isEmpty) return 'there';
    return t.split(RegExp(r'\s+')).first;
  }

  static String _initials(String full) {
    final List<String> parts =
        full.trim().split(RegExp(r'\s+')).where((String s) => s.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1)).toUpperCase();
  }

  static String _roleLabel(String? role) {
    switch ((role ?? '').toLowerCase()) {
      case 'owner':
      case 'lead':
        return 'Team Lead';
      case 'member':
      case '':
        return 'Contributor';
      default:
        return role![0].toUpperCase() + role.substring(1);
    }
  }

  String? _passportUrl(Project p) {
    final String? uid = _snap?.userId;
    if (uid == null) return null;
    return '${ApiClient.activeBaseUrl}/passport/$uid/${p.id}';
  }

  void _toast(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _openPassport(Project p) async {
    final String? url = _passportUrl(p);
    if (url == null) {
      _toast('Passport link is not ready yet. Pull down to refresh.');
      return;
    }
    final bool ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!ok) _toast('Could not open the passport.');
  }

  Future<void> _copyPassport(Project p) async {
    final String? url = _passportUrl(p);
    if (url == null) {
      _toast('Passport link is not ready yet. Pull down to refresh.');
      return;
    }
    await Clipboard.setData(ClipboardData(text: url));
    _toast('Passport link copied');
  }

  Future<void> _withProject(String title, void Function(Project) onPick) async {
    final List<Project> projects =
        (_snap?.cards ?? const <DashboardCard>[]).map((DashboardCard c) => c.project).toList();
    if (projects.isEmpty) {
      _toast('Create or join a project first.');
      return;
    }
    if (projects.length == 1) {
      onPick(projects.first);
      return;
    }
    final Project? picked = await showModalBottomSheet<Project>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppColors.champagne,
      builder: (BuildContext ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Text(
                title,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  color: AppColors.emeraldInk,
                ),
              ),
            ),
            for (final Project p in projects)
              ListTile(
                title: Text(
                  p.name,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: AppColors.bodyText,
                  ),
                ),
                trailing: const Icon(Icons.chevron_right_rounded, color: AppColors.emeraldInk),
                onTap: () => Navigator.pop(ctx, p),
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (picked != null && mounted) onPick(picked);
  }

  void _openProject(Project p) {
    Navigator.pushNamed(context, ProjectDetailScreen.routeName, arguments: p)
        .then((_) => _refresh());
  }

  void _showGitHubInfo() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppColors.champagne,
      builder: (BuildContext ctx) => const SafeArea(
        child: Padding(
          padding: EdgeInsets.fromLTRB(20, 0, 20, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                'Get credit for your commits',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  color: AppColors.emeraldInk,
                ),
              ),
              SizedBox(height: 10),
              Text(
                'BuildCrew credits GitHub commits only to accounts that signed in '
                'with GitHub. Sign in with GitHub using the same email as this '
                'account so the two are linked.',
                style: TextStyle(fontSize: 14.5, height: 1.4, color: AppColors.bodyText),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // --------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final String name = _displayName(context);
    final DashboardSnapshot? snap = _snap;
    final int pending = snap?.pendingCount ?? 0;

    return Scaffold(
      backgroundColor: AppColors.champagne,
      body: RefreshIndicator(
        color: AppColors.emeraldInk,
        onRefresh: _refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.zero,
          children: <Widget>[
            Stack(
              fit: StackFit.passthrough,
              clipBehavior: Clip.none,
              children: <Widget>[
                Positioned(
                  left: 0,
                  right: 0,
                  top: 0,
                  height: 250,
                  child: Container(
                    decoration: const BoxDecoration(
                      color: AppColors.emeraldInk,
                      borderRadius: BorderRadius.vertical(bottom: Radius.circular(32)),
                    ),
                  ),
                ),
                Column(
                  children: <Widget>[
                    SafeArea(
                      bottom: false,
                      child: _buildHeader(context, name, pending),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                      child: _buildHero(context, snap),
                    ),
                  ],
                ),
              ],
            ),
            if (pending > 0)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                child: _buildPendingBanner(context, pending),
              ),
            if (_offlineStale)
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 12, 20, 0),
                child: _InlineNote('Offline. Showing your last saved data. Pull down to retry.'),
              ),
            const _SectionTitle('Quick actions'),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: _buildActions(),
            ),
            _SectionTitle(
              'Your projects',
              trailing: TextButton(
                onPressed: () =>
                    Navigator.pushNamed(context, '/projects').then((_) => _refresh()),
                child: const Text(
                  'See all',
                  style: TextStyle(
                    color: AppColors.emeraldInk,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 32),
              child: _buildProjects(context, snap),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, String name, int pending) {
    final String? avatar = _avatarUrl;
    final String? login = _githubLogin;
    final bool knowsUser =
        _supabaseUser() != null || widget.userName != null || _storedName != null;

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 8, 0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Container(
            width: 56,
            height: 56,
            padding: const EdgeInsets.all(2),
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.champagne,
            ),
            child: ClipOval(
              child: avatar != null
                  ? Image.network(
                      avatar,
                      fit: BoxFit.cover,
                      errorBuilder: (BuildContext c, Object e, StackTrace? s) =>
                          _InitialsAvatar(initials: _initials(name)),
                    )
                  : _InitialsAvatar(initials: _initials(name)),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Hello, ${_firstName(name)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.champagne,
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 6),
                if (login != null)
                  _IdentityPill(
                    key: const Key('home_github_verified_pill'),
                    icon: Icons.verified_rounded,
                    label: 'GitHub verified · @$login',
                    filled: true,
                  )
                else if (knowsUser)
                  GestureDetector(
                    onTap: _showGitHubInfo,
                    child: const _IdentityPill(
                      key: Key('home_github_unlinked_pill'),
                      icon: Icons.info_outline_rounded,
                      label: 'GitHub not linked',
                      filled: false,
                    ),
                  ),
              ],
            ),
          ),
          Badge.count(
            count: pending,
            isLabelVisible: pending > 0,
            backgroundColor: const Color(0xFFE8C25A),
            textColor: const Color(0xFF3B2A00),
            child: IconButton(
              key: const Key('home_pending_confirmations_btn'),
              tooltip: 'Pending reviews',
              icon: const Icon(Icons.notifications_none_rounded, color: AppColors.champagne),
              onPressed: () => Navigator.pushNamed(context, '/pending-confirmations')
                  .then((_) => _refresh()),
            ),
          ),
          IconButton(
            key: const Key('home_settings_btn'),
            tooltip: 'Settings',
            icon: const Icon(Icons.settings_outlined, color: AppColors.champagne),
            onPressed: () => Navigator.pushNamed(context, SettingsScreen.routeName),
          ),
        ],
      ),
    );
  }

  Widget _buildHero(BuildContext context, DashboardSnapshot? snap) {
    if (snap == null) {
      if (_failedNoData) {
        return _InlineRetry(message: "Couldn't load your passport.", onRetry: _refresh);
      }
      return const _HeroSyncing();
    }

    final DashboardCard? hero = snap.cards.isEmpty ? null : snap.cards.first;

    if (hero == null) {
      return _Card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const _Eyebrow('PASSPORT'),
            const SizedBox(height: 8),
            const Text(
              'Start your contribution passport',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w800,
                color: AppColors.emeraldInk,
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              'Create a project or join your team with an invite code, log what you built, and let teammates confirm it.',
              style: TextStyle(fontSize: 14, height: 1.4, color: AppColors.textMuted),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: <Widget>[
                FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.emeraldInk,
                    foregroundColor: Colors.white,
                    minimumSize: const Size(0, 48),
                  ),
                  onPressed: () =>
                      Navigator.pushNamed(context, '/create-project').then((_) => _refresh()),
                  child: const Text('Create project'),
                ),
                OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.emeraldInk,
                    minimumSize: const Size(0, 48),
                    side: const BorderSide(color: AppColors.emeraldInk),
                  ),
                  onPressed: () =>
                      Navigator.pushNamed(context, '/join-project').then((_) => _refresh()),
                  child: const Text('Join with code'),
                ),
              ],
            ),
          ],
        ),
      );
    }

    final _Health health;
    if (!hero.hydrated) {
      health = _refreshing ? _Health.syncing : _Health.unknown;
    } else if (hero.verified > 0 && hero.disputed == 0) {
      health = _Health.active;
    } else {
      health = _Health.needsVerification;
    }
    String shown(int v) => hero.hydrated ? '$v' : '–';

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Expanded(child: _Eyebrow('PASSPORT HEALTH')),
              _StatusBadge(health: health),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            hero.project.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: AppColors.emeraldInk,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: <Widget>[
              Expanded(
                child: _Stat(
                  valueText: shown(hero.verified),
                  label: 'verified',
                  color: AppColors.emeraldInk,
                ),
              ),
              Expanded(
                child: _Stat(
                  valueText: shown(hero.waiting),
                  label: 'waiting',
                  color: _Ui.amberText,
                ),
              ),
              Expanded(
                child: _Stat(
                  valueText: shown(hero.disputed),
                  label: 'disputed',
                  color: _Ui.redText,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              Expanded(
                child: FilledButton.icon(
                  key: const Key('home_view_passport_btn'),
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.emeraldInk,
                    foregroundColor: Colors.white,
                    minimumSize: const Size(0, 48),
                  ),
                  onPressed: () => _openPassport(hero.project),
                  icon: const Icon(Icons.open_in_new_rounded, size: 18),
                  label: const Text('View passport'),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.outlined(
                key: const Key('home_copy_passport_btn'),
                tooltip: 'Copy passport link',
                style: IconButton.styleFrom(
                  foregroundColor: AppColors.emeraldInk,
                  side: const BorderSide(color: AppColors.emeraldInk),
                  minimumSize: const Size(48, 48),
                ),
                onPressed: () => _copyPassport(hero.project),
                icon: const Icon(Icons.link_rounded),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPendingBanner(BuildContext context, int pending) {
    final String text = pending == 1
        ? '1 teammate is waiting for your review'
        : '$pending teammates are waiting for your review';
    return Material(
      color: _Ui.amberBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: _Ui.amberLine),
      ),
      child: InkWell(
        key: const Key('home_pending_banner'),
        borderRadius: BorderRadius.circular(16),
        onTap: () =>
            Navigator.pushNamed(context, '/pending-confirmations').then((_) => _refresh()),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: <Widget>[
              const Icon(Icons.rate_review_outlined, color: _Ui.amberText),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  text,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: _Ui.amberText,
                    height: 1.3,
                  ),
                ),
              ),
              const Text(
                'Review',
                style: TextStyle(fontWeight: FontWeight.w800, color: _Ui.amberText),
              ),
              const Icon(Icons.chevron_right_rounded, color: _Ui.amberText),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildActions() {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double w = (constraints.maxWidth - 12) / 2;
        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: <Widget>[
            SizedBox(
              width: w,
              child: _ActionCard(
                key: const Key('home_action_join'),
                icon: Icons.group_add_outlined,
                title: 'Join Team',
                subtitle: 'Enter an invite code',
                onTap: () =>
                    Navigator.pushNamed(context, '/join-project').then((_) => _refresh()),
              ),
            ),
            SizedBox(
              width: w,
              child: _ActionCard(
                key: const Key('home_action_create'),
                icon: Icons.add_circle_outline_rounded,
                title: 'Create Project',
                subtitle: 'Start a new team',
                onTap: () =>
                    Navigator.pushNamed(context, '/create-project').then((_) => _refresh()),
              ),
            ),
            SizedBox(
              width: w,
              child: _ActionCard(
                key: const Key('home_action_github'),
                icon: Icons.hub_outlined,
                title: 'Connect GitHub',
                subtitle: 'Link a repository',
                onTap: () => _withProject('Connect GitHub for…', (Project p) {
                  Navigator.pushNamed(
                    context,
                    ConnectRepositoryScreen.routeName,
                    arguments: <String, dynamic>{'projectId': p.id, 'projectName': p.name},
                  ).then((_) => _refresh());
                }),
              ),
            ),
            SizedBox(
              width: w,
              child: _ActionCard(
                key: const Key('home_action_ledger'),
                icon: Icons.fact_check_outlined,
                title: 'Team Ledger',
                subtitle: 'See who verified what',
                onTap: () => _withProject('Open the ledger for…', (Project p) {
                  Navigator.push(
                    context,
                    MaterialPageRoute<void>(
                      builder: (_) => TeamLedgerScreen(projectId: p.id, projectName: p.name),
                    ),
                  ).then((_) => _refresh());
                }),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildProjects(BuildContext context, DashboardSnapshot? snap) {
    if (snap == null) {
      if (_failedNoData) {
        return _InlineRetry(message: "Couldn't load your projects.", onRetry: _refresh);
      }
      return const _SyncingTile();
    }
    if (snap.cards.isEmpty) {
      return const _Card(
        child: Text(
          'No projects yet. Create one or join with an invite code to start building your passport.',
          style: TextStyle(fontSize: 14, height: 1.4, color: AppColors.textMuted),
        ),
      );
    }
    return Column(
      children: <Widget>[
        for (int i = 0; i < snap.cards.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: _ProjectTile(
              data: snap.cards[i],
              roleLabel: _roleLabel(snap.cards[i].project.role),
              syncing: i < 3 && !snap.cards[i].hydrated && _refreshing,
              onTap: () => _openProject(snap.cards[i].project),
            ),
          ),
      ],
    );
  }
}

// ------------------------------------------------------------------ widgets

class _Card extends StatelessWidget {
  const _Card({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: _Ui.card,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: AppColors.divider),
        boxShadow: const <BoxShadow>[
          BoxShadow(color: Color(0x1F064E3B), blurRadius: 18, offset: Offset(0, 8)),
        ],
      ),
      child: child,
    );
  }
}

class _Eyebrow extends StatelessWidget {
  const _Eyebrow(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 11.5,
        fontWeight: FontWeight.w800,
        letterSpacing: 1.1,
        color: AppColors.textMuted,
      ),
    );
  }
}

enum _Health { active, needsVerification, syncing, unknown }

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.health});
  final _Health health;

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color fg;
    IconData icon;
    String label;
    if (health == _Health.active) {
      bg = _Ui.mint;
      fg = AppColors.emeraldInk;
      icon = Icons.check_circle_rounded;
      label = 'Active';
    } else if (health == _Health.needsVerification) {
      bg = _Ui.amberBg;
      fg = _Ui.amberText;
      icon = Icons.error_outline_rounded;
      label = 'Needs verification';
    } else if (health == _Health.syncing) {
      bg = AppColors.champagne;
      fg = AppColors.emeraldInk;
      icon = Icons.sync_rounded;
      label = 'Syncing';
    } else {
      bg = AppColors.champagne;
      fg = AppColors.textMuted;
      icon = Icons.cloud_off_rounded;
      label = 'Pull down to refresh';
    }
    return Container(
      key: const Key('home_status_badge'),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 15, color: fg),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w800, color: fg),
          ),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.valueText, required this.label, required this.color});
  final String valueText;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Text(
          valueText,
          style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: color),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
        ),
      ],
    );
  }
}

class _IdentityPill extends StatelessWidget {
  const _IdentityPill({super.key, required this.icon, required this.label, required this.filled});
  final IconData icon;
  final String label;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final Color fg = filled ? AppColors.emeraldInk : AppColors.champagne;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: filled ? _Ui.mint : Colors.transparent,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: filled ? _Ui.mint : AppColors.champagne.withValues(alpha: 0.7)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 14, color: fg),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: fg),
            ),
          ),
        ],
      ),
    );
  }
}

class _InitialsAvatar extends StatelessWidget {
  const _InitialsAvatar({required this.initials});
  final String initials;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.champagne,
      alignment: Alignment.center,
      child: Text(
        initials,
        style: const TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w800,
          color: AppColors.emeraldInk,
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text, {this.trailing});
  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 22, 12, 8),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w800,
                color: AppColors.emeraldInk,
              ),
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: _Ui.card,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: AppColors.divider),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 96),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Container(
                  width: 38,
                  height: 38,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    color: AppColors.champagne,
                  ),
                  child: Icon(icon, size: 21, color: AppColors.emeraldInk),
                ),
                const SizedBox(height: 10),
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: AppColors.emeraldInk,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ProjectTile extends StatelessWidget {
  const _ProjectTile({
    required this.data,
    required this.roleLabel,
    required this.syncing,
    required this.onTap,
  });

  final DashboardCard data;
  final String roleLabel;
  final bool syncing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Project p = data.project;
    return Material(
      color: _Ui.card,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: AppColors.divider),
      ),
      child: InkWell(
        key: Key('home_project_${p.id}'),
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Container(
                    width: 42,
                    height: 42,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: AppColors.emeraldInk,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      p.name.isEmpty ? '?' : p.name.substring(0, 1).toUpperCase(),
                      style: const TextStyle(
                        color: AppColors.champagne,
                        fontSize: 19,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          p.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: AppColors.bodyText,
                          ),
                        ),
                        const SizedBox(height: 4),
                        _Chip(
                          label: roleLabel,
                          bg: AppColors.champagne,
                          fg: AppColors.emeraldInk,
                        ),
                      ],
                    ),
                  ),
                  if (data.members.isNotEmpty) _AvatarStack(members: data.members),
                ],
              ),
              if (data.hydrated) ...<Widget>[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: <Widget>[
                    _Chip(
                      label: '${data.verified} verified',
                      bg: _Ui.mint,
                      fg: AppColors.emeraldInk,
                    ),
                    if (data.waiting > 0)
                      _Chip(
                        label: '${data.waiting} waiting',
                        bg: _Ui.amberBg,
                        fg: _Ui.amberText,
                      ),
                    if (data.disputed > 0)
                      _Chip(
                        label: '${data.disputed} disputed',
                        bg: _Ui.redBg,
                        fg: _Ui.redText,
                      ),
                  ],
                ),
              ] else if (syncing) ...<Widget>[
                const SizedBox(height: 12),
                const _InlineNote('Syncing your contributions…'),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.bg, required this.fg});
  final String label;
  final Color bg;
  final Color fg;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(
        label,
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: fg),
      ),
    );
  }
}

class _AvatarStack extends StatelessWidget {
  const _AvatarStack({required this.members});
  final List<DashboardMember> members;

  @override
  Widget build(BuildContext context) {
    const double size = 28;
    const double overlap = 18;
    final List<DashboardMember> shown = members.take(3).toList();
    final int extra = members.length - shown.length;
    final int slots = shown.length + (extra > 0 ? 1 : 0);
    return Semantics(
      label: '${members.length} team members',
      child: SizedBox(
        width: size + (slots - 1) * overlap,
        height: size,
        child: Stack(
          children: <Widget>[
            for (int i = 0; i < shown.length; i++)
              Positioned(
                left: i * overlap,
                child: _MiniAvatar(member: shown[i], size: size),
              ),
            if (extra > 0)
              Positioned(
                left: shown.length * overlap,
                child: Container(
                  width: size,
                  height: size,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: AppColors.emeraldInk,
                    border: Border.all(color: Colors.white, width: 2),
                  ),
                  child: Text(
                    '+$extra',
                    style: const TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w800,
                      color: AppColors.champagne,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _MiniAvatar extends StatelessWidget {
  const _MiniAvatar({required this.member, required this.size});
  final DashboardMember member;
  final double size;

  @override
  Widget build(BuildContext context) {
    final String letter = member.name.isEmpty ? '?' : member.name.substring(0, 1).toUpperCase();
    final Widget fallback = Container(
      color: AppColors.champagne,
      alignment: Alignment.center,
      child: Text(
        letter,
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w800,
          color: AppColors.emeraldInk,
        ),
      ),
    );
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 2),
      ),
      child: ClipOval(
        child: member.avatarUrl == null
            ? fallback
            : Image.network(
                member.avatarUrl!,
                fit: BoxFit.cover,
                errorBuilder: (BuildContext c, Object e, StackTrace? s) => fallback,
              ),
      ),
    );
  }
}

class _InlineRetry extends StatelessWidget {
  const _InlineRetry({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Row(
        children: <Widget>[
          const Icon(Icons.cloud_off_rounded, color: AppColors.textMuted),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(fontWeight: FontWeight.w600, color: AppColors.bodyText),
            ),
          ),
          TextButton(
            onPressed: () => onRetry(),
            child: const Text(
              'Retry',
              style: TextStyle(color: AppColors.emeraldInk, fontWeight: FontWeight.w800),
            ),
          ),
        ],
      ),
    );
  }
}

/// Hero shown only while there is neither memory nor saved data yet.
/// It is filled with real text, never a blank box.
class _HeroSyncing extends StatelessWidget {
  const _HeroSyncing();

  @override
  Widget build(BuildContext context) {
    return const _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _Eyebrow('PASSPORT HEALTH'),
          SizedBox(height: 8),
          Text(
            'Getting your passport ready…',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
              color: AppColors.emeraldInk,
            ),
          ),
          SizedBox(height: 6),
          Text(
            'Syncing your projects and reviews.',
            style: TextStyle(fontSize: 14, height: 1.4, color: AppColors.textMuted),
          ),
          SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.all(Radius.circular(99)),
            child: LinearProgressIndicator(
              minHeight: 5,
              color: AppColors.emeraldInk,
              backgroundColor: AppColors.champagne,
            ),
          ),
        ],
      ),
    );
  }
}

class _SyncingTile extends StatelessWidget {
  const _SyncingTile();

  @override
  Widget build(BuildContext context) {
    return const _Card(
      child: Row(
        children: <Widget>[
          Icon(Icons.sync_rounded, color: AppColors.emeraldInk),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'Loading your projects…',
              style: TextStyle(fontWeight: FontWeight.w600, color: AppColors.bodyText),
            ),
          ),
        ],
      ),
    );
  }
}

class _InlineNote extends StatelessWidget {
  const _InlineNote(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        const Icon(Icons.sync_rounded, size: 15, color: AppColors.textMuted),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
          ),
        ),
      ],
    );
  }
}
