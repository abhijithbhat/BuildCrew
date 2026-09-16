import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/contribution.dart';
import '../services/api_client.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';
import '../widgets/empty_state_view.dart';

/// Screen allowing builders to select which of their confirmed deliverables
/// should be visible on their public BuildCrew Passport.
class PublishSelectionScreen extends StatefulWidget {
  static const String routeName = '/publish-selection';

  final String? projectId;
  final String? projectName;
  final String? userId;
  final List<Contribution>? initialContributions;
  final ProjectService? projectService;
  final StorageService? storageService;
  final ValueChanged<Set<String>>? onSelectionChanged;
  final VoidCallback? onSave;

  const PublishSelectionScreen({
    super.key,
    this.projectId,
    this.projectName,
    this.userId,
    this.initialContributions,
    this.projectService,
    this.storageService,
    this.onSelectionChanged,
    this.onSave,
  });

  @override
  State<PublishSelectionScreen> createState() => _PublishSelectionScreenState();
}

class _PublishSelectionScreenState extends State<PublishSelectionScreen> {
  late final ProjectService _projectService;
  late final StorageService _storageService;
  ScaffoldMessengerState? _scaffoldMessenger;

  final TextEditingController _searchController = TextEditingController();
  final Set<String> _selectedIds = {};
  bool _isSaving = false;

  List<Contribution> _confirmedContributions = [];
  String _searchQuery = '';
  String? _resolvedProjectId;
  String? _resolvedProjectName;
  String? _currentUserId;

  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _currentUserId = widget.userId;
    _resolvedProjectId = widget.projectId;
    _resolvedProjectName = widget.projectName;
    _projectService = widget.projectService ?? ProjectService();
    _storageService = widget.storageService ?? StorageService();
    if (widget.initialContributions != null) {
      _loadItems(widget.initialContributions!);
    }
    _initAndLoad();
  }

  Future<void> _initAndLoad() async {
    if (_currentUserId == null || _currentUserId!.isEmpty) {
      try {
        _currentUserId = await _storageService.getUserId();
      } catch (_) {}
    }

    if (widget.initialContributions == null &&
        _resolvedProjectId != null &&
        _resolvedProjectId!.isNotEmpty) {
      await _fetchContributions();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _scaffoldMessenger = ScaffoldMessenger.of(context);
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is Map<String, dynamic>) {
      bool shouldFetch = false;
      if (args['userId'] != null && _currentUserId == null) {
        _currentUserId = args['userId']?.toString();
      }
      if (args['projectId'] != null && _resolvedProjectId == null) {
        _resolvedProjectId = args['projectId']?.toString();
        shouldFetch = true;
      }
      if (args['projectName'] != null && _resolvedProjectName == null) {
        _resolvedProjectName = args['projectName']?.toString();
      }
      if (args['contributions'] is List<Contribution> &&
          _confirmedContributions.isEmpty) {
        final passedList = args['contributions'] as List<Contribution>;
        _loadItems(passedList);
        shouldFetch = false;
      }
      if (shouldFetch &&
          widget.initialContributions == null &&
          _confirmedContributions.isEmpty) {
        _fetchContributions();
      }
    }
  }

  @override
  void deactivate() {
    _scaffoldMessenger?.hideCurrentSnackBar();
    super.deactivate();
  }

  void _loadItems(List<Contribution> list) {
    // Strictly isolate to THIS user's confirmed deliverables that are NOT disputed or needing review.
    final confirmed = list.where((c) {
      final matchesUser = _currentUserId == null ||
          _currentUserId!.isEmpty ||
          c.contributor == _currentUserId ||
          (c.contributorProfile != null &&
              (c.contributorProfile!['user_id'] == _currentUserId ||
                  c.contributorProfile!['id'] == _currentUserId));
      return matchesUser && c.isConfirmed && !c.needsReview && !c.isDisputed;
    }).toList();

    setState(() {
      _confirmedContributions = confirmed;
      _selectedIds.clear();
      for (final c in confirmed) {
        if (c.visibility.toLowerCase() == 'public') {
          _selectedIds.add(c.id);
        }
      }
    });
  }

  Future<void> _fetchContributions() async {
    if (_resolvedProjectId == null || _resolvedProjectId!.isEmpty) return;

    // Ensure _currentUserId is loaded so we never fetch other users' contributions
    if (_currentUserId == null || _currentUserId!.isEmpty) {
      try {
        _currentUserId = await _storageService.getUserId();
      } catch (_) {}
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final list = await _projectService.listContributions(
        _resolvedProjectId!,
        contributor: _currentUserId,
      );
      if (!mounted) return;
      _loadItems(list);
      setState(() {
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<Contribution> get _filteredContributions {
    if (_searchQuery.trim().isEmpty) {
      return _confirmedContributions;
    }
    final q = _searchQuery.trim().toLowerCase();
    return _confirmedContributions.where((c) {
      final titleMatch = c.title.toLowerCase().contains(q);
      final descMatch = c.description?.toLowerCase().contains(q) ?? false;
      final catMatch = c.category?.toLowerCase().contains(q) ?? false;
      return titleMatch || descMatch || catMatch;
    }).toList();
  }

  void _toggleItem(Contribution item) {
    if (_isSaving) return;
    final id = item.id;
    setState(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
      } else {
        _selectedIds.add(id);
      }
    });
    widget.onSelectionChanged?.call(Set.from(_selectedIds));
  }

  void _selectAll() {
    if (_isSaving) return;
    setState(() {
      for (final c in _filteredContributions) {
        _selectedIds.add(c.id);
      }
    });
    widget.onSelectionChanged?.call(Set.from(_selectedIds));
  }

  void _deselectAll() {
    if (_isSaving) return;
    setState(() {
      for (final c in _filteredContributions) {
        _selectedIds.remove(c.id);
      }
    });
    widget.onSelectionChanged?.call(Set.from(_selectedIds));
  }

  Future<void> _savePassport() async {
    if (_isSaving) return;
    setState(() {
      _isSaving = true;
    });

    try {
      final toPublish = _confirmedContributions
          .where((c) =>
              _selectedIds.contains(c.id) &&
              c.visibility.toLowerCase() != 'public')
          .map((c) => c.id)
          .toList();

      final toUnpublish = _confirmedContributions
          .where((c) =>
              !_selectedIds.contains(c.id) &&
              c.visibility.toLowerCase() == 'public')
          .map((c) => c.id)
          .toList();

      final futures = <Future<Contribution>>[];
      for (final id in toPublish) {
        futures.add(_projectService.publishContribution(id));
      }
      for (final id in toUnpublish) {
        futures.add(_projectService.unpublishContribution(id));
      }

      if (futures.isNotEmpty) {
        final results = await Future.wait(futures);
        if (!mounted) return;
        for (final updated in results) {
          _updateContributionInList(updated);
        }
      }

      if (!mounted) return;
      widget.onSave?.call();

      final totalSelected = _selectedIds.length;
      if (!mounted) return;
      _scaffoldMessenger?.hideCurrentSnackBar();
      _scaffoldMessenger?.showSnackBar(
        SnackBar(
          duration: const Duration(seconds: 4),
          content: Row(
            children: [
              const Icon(Icons.check_circle_rounded,
                  color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Updated passport: $totalSelected deliverable${totalSelected == 1 ? "" : "s"} published.',
                ),
              ),
            ],
          ),
          backgroundColor: const Color(0xFF10B981),
          behavior: SnackBarBehavior.floating,
          action: SnackBarAction(
            label: 'Copy Link',
            textColor: Colors.white,
            onPressed: _sharePassportLink,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      _scaffoldMessenger?.hideCurrentSnackBar();
      _scaffoldMessenger?.showSnackBar(
        SnackBar(
          duration: const Duration(seconds: 4),
          content: Row(
            children: [
              const Icon(Icons.error_outline_rounded,
                  color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(e.toString()),
              ),
            ],
          ),
          backgroundColor: const Color(0xFFE11D48),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSaving = false;
        });
      }
    }
  }

  String _getPassportUrl() {
    final uid = _currentUserId ?? 'user';
    final pid = _resolvedProjectId ?? 'project';
    return '${ApiClient.activeBaseUrl}/passport/$uid/$pid';
  }

  Future<void> _sharePassportLink() async {
    final url = _getPassportUrl();
    await Clipboard.setData(ClipboardData(text: url));
    if (!mounted) return;
    _scaffoldMessenger?.hideCurrentSnackBar();
    _scaffoldMessenger?.showSnackBar(
      SnackBar(
        duration: const Duration(seconds: 3),
        content: Row(
          children: [
            const Icon(Icons.link_rounded, color: Colors.white, size: 20),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Public passport link copied:\n$url',
                style: const TextStyle(fontSize: 12),
              ),
            ),
          ],
        ),
        backgroundColor: const Color(0xFF4F46E5),
        behavior: SnackBarBehavior.floating,
        action: SnackBarAction(
          label: 'Open',
          textColor: Colors.white,
          onPressed: () async {
            final uri = Uri.parse(url);
            if (await canLaunchUrl(uri)) {
              await launchUrl(uri, mode: LaunchMode.externalApplication);
            }
          },
        ),
      ),
    );
  }

  void _updateContributionInList(Contribution updated) {
    setState(() {
      final index =
          _confirmedContributions.indexWhere((c) => c.id == updated.id);
      if (index != -1) {
        _confirmedContributions[index] = updated;
      }
    });
  }

  Color _getCategoryColor(String? category) {
    switch (category?.toLowerCase()) {
      case 'code':
        return const Color(0xFF3B82F6); // Blue
      case 'design':
        return const Color(0xFFA855F7); // Purple
      case 'docs':
      case 'documentation':
        return const Color(0xFF14B8A6); // Teal
      case 'devops':
        return const Color(0xFFF59E0B); // Amber
      case 'marketing':
        return const Color(0xFFEC4899); // Pink
      case 'testing':
      case 'qa':
        return const Color(0xFF10B981); // Emerald
      default:
        return const Color(0xFF64748B); // Slate
    }
  }

  IconData _getCategoryIcon(String? category) {
    switch (category?.toLowerCase()) {
      case 'code':
        return Icons.code_rounded;
      case 'design':
        return Icons.palette_outlined;
      case 'docs':
      case 'documentation':
        return Icons.description_outlined;
      case 'devops':
        return Icons.cloud_done_outlined;
      case 'marketing':
        return Icons.campaign_outlined;
      case 'testing':
      case 'qa':
        return Icons.bug_report_outlined;
      default:
        return Icons.folder_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filteredContributions;
    final totalConfirmed = _confirmedContributions.length;
    final totalSelected = _selectedIds.length;
    final isAllSelected = filtered.isNotEmpty &&
        filtered.every((c) => _selectedIds.contains(c.id));

    return PopScope(
      canPop: true,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) {
          _scaffoldMessenger?.hideCurrentSnackBar();
        }
      },
      child: Scaffold(
        backgroundColor: const Color(0xFFF8FAFC),
        appBar: AppBar(
          backgroundColor: Colors.white,
          elevation: 0,
          scrolledUnderElevation: 0,
          shape: const Border(
            bottom: BorderSide(color: Color(0xFFE2E8F0), width: 1),
          ),
          leading: IconButton(
            key: const Key('publish_back_button'),
            icon: const Icon(Icons.arrow_back_rounded, color: Color(0xFF0F172A)),
            onPressed: () {
              _scaffoldMessenger?.hideCurrentSnackBar();
              Navigator.of(context).pop();
            },
          ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Select What to Publish',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Color(0xFF0F172A),
                letterSpacing: -0.3,
              ),
            ),
            Text(
              _resolvedProjectName != null && _resolvedProjectName!.isNotEmpty
                  ? 'Passport Visibility • $_resolvedProjectName'
                  : 'Passport Visibility Controls',
              style: const TextStyle(
                fontSize: 12,
                color: Color(0xFF64748B),
                fontWeight: FontWeight.w400,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            key: const Key('publish_share_passport_btn'),
            tooltip: 'Share Passport Link',
            icon: const Icon(Icons.share_outlined, color: Color(0xFF4F46E5), size: 20),
            onPressed: _sharePassportLink,
          ),
          if (filtered.isNotEmpty)
            TextButton(
              key: const Key('publish_toggle_all_btn'),
              onPressed: isAllSelected ? _deselectAll : _selectAll,
              child: Text(
                isAllSelected ? 'Deselect All' : 'Select All',
                style: const TextStyle(
                  color: Color(0xFF4F46E5),
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _fetchContributions,
        color: const Color(0xFF4F46E5),
        backgroundColor: Colors.white,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Header summary card
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.fromLTRB(16, 16, 16, 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: const Color(0xFFE2E8F0)),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF0F172A).withValues(alpha: 0.04),
                          blurRadius: 10,
                          offset: const Offset(0, 3),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: const Color(0xFFEEF2FF),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Icon(
                                Icons.verified_user_rounded,
                                color: Color(0xFF4F46E5),
                                size: 24,
                              ),
                            ),
                            const SizedBox(width: 12),
                            const Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'Public Passport Visibility',
                                    style: TextStyle(
                                      fontSize: 15,
                                      fontWeight: FontWeight.bold,
                                      color: Color(0xFF0F172A),
                                    ),
                                  ),
                                  SizedBox(height: 4),
                                  Text(
                                    'Choose which confirmed deliverables are featured on your public passport profile. Unchecked items remain private to your team.',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: Color(0xFF64748B),
                                      height: 1.4,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 14),
                        // Stats badges row
                        Row(
                          children: [
                            _buildStatBadge(
                              label: 'Published',
                              count: totalSelected,
                              color: const Color(0xFF10B981),
                              icon: Icons.public_rounded,
                            ),
                            const SizedBox(width: 8),
                            _buildStatBadge(
                              label: 'Private',
                              count: totalConfirmed - totalSelected > 0
                                  ? totalConfirmed - totalSelected
                                  : 0,
                              color: const Color(0xFF64748B),
                              icon: Icons.lock_outline_rounded,
                            ),
                            const SizedBox(width: 8),
                            _buildStatBadge(
                              label: 'Confirmed',
                              count: totalConfirmed,
                              color: const Color(0xFF4F46E5),
                              icon: Icons.check_circle_outline_rounded,
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),

                  // Search & filter field
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: TextField(
                      key: const Key('publish_search_field'),
                      controller: _searchController,
                      onChanged: (val) {
                        setState(() {
                          _searchQuery = val;
                        });
                      },
                      style: const TextStyle(
                          color: Color(0xFF0F172A), fontSize: 14),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: Colors.white,
                        hintText: 'Search confirmed deliverables...',
                        hintStyle: const TextStyle(
                          color: Color(0xFFB0BEC5),
                          fontSize: 13,
                        ),
                        prefixIcon: const Icon(
                          Icons.search_rounded,
                          color: Color(0xFF4F46E5),
                          size: 20,
                        ),
                        suffixIcon: _searchQuery.isNotEmpty
                            ? IconButton(
                                icon: const Icon(Icons.clear_rounded,
                                    color: Color(0xFF64748B), size: 18),
                                onPressed: () {
                                  _searchController.clear();
                                  setState(() {
                                    _searchQuery = '';
                                  });
                                },
                              )
                            : null,
                        contentPadding:
                            const EdgeInsets.symmetric(vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide:
                              const BorderSide(color: Color(0xFFE2E8F0)),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide:
                              const BorderSide(color: Color(0xFFE2E8F0)),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide:
                              const BorderSide(color: Color(0xFF4F46E5), width: 1.5),
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 12),

                  // Error banner if initial fetch failed
                  if (_errorMessage != null)
                    Container(
                      margin: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF1F2),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: const Color(0xFFFECDD3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline_rounded,
                              color: Color(0xFFE11D48), size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: const TextStyle(
                                  color: Color(0xFFBE123C), fontSize: 13),
                            ),
                          ),
                          TextButton(
                            onPressed: _fetchContributions,
                            child: const Text('Retry',
                                style: TextStyle(
                                    color: Color(0xFFE11D48),
                                    fontWeight: FontWeight.bold)),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            if (_isLoading)
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: 48),
                  child: Center(
                    child: CircularProgressIndicator(
                      color: Color(0xFF4F46E5),
                    ),
                  ),
                ),
              )
            else if (filtered.isEmpty)
              SliverToBoxAdapter(
                child: _buildEmptyState(),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 80),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      final item = filtered[index];
                      final isSelected = _selectedIds.contains(item.id);
                      return _buildContributionCheckCard(
                        item,
                        isSelected,
                        _isSaving,
                      );
                    },
                    childCount: filtered.length,
                  ),
                ),
              ),
          ],
        ),
      ),

      // Bottom action bar
      bottomNavigationBar: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white,
          border: const Border(
            top: BorderSide(color: Color(0xFFE2E8F0)),
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF0F172A).withValues(alpha: 0.05),
              offset: const Offset(0, -4),
              blurRadius: 12,
            ),
          ],
        ),
        child: SafeArea(
          child: Row(
            children: [
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$totalSelected of $totalConfirmed selected',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF0F172A),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      totalSelected == 1
                          ? '1 deliverable visible on passport'
                          : '$totalSelected deliverables visible on passport',
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF64748B),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              ElevatedButton.icon(
                key: const Key('publish_save_button'),
                onPressed: _isSaving ? null : _savePassport,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF4F46E5),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                icon: _isSaving
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.check_rounded, size: 18),
                label: Text(
                  _isSaving ? 'Saving...' : 'Save Passport',
                  style: const TextStyle(
                      fontSize: 14, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

  Widget _buildStatBadge({
    required String label,
    required int count,
    required Color color,
    required IconData icon,
  }) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: color.withAlpha(16),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withAlpha(50)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: color, size: 14),
            const SizedBox(width: 4),
            Flexible(
              child: Text(
                '$count $label',
                style: TextStyle(
                  color: color,
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContributionCheckCard(
    Contribution item,
    bool isSelected,
    bool isUpdating,
  ) {
    final catColor = _getCategoryColor(item.category);
    final catIcon = _getCategoryIcon(item.category);

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: isSelected ? Colors.white : const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isSelected
              ? const Color(0xFF4F46E5)
              : const Color(0xFFE2E8F0),
          width: isSelected ? 1.5 : 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: isSelected
                ? const Color(0xFF4F46E5).withValues(alpha: 0.06)
                : const Color(0xFF0F172A).withValues(alpha: 0.03),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: isUpdating ? null : () => _toggleItem(item),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Checkbox or in-flight spinner
                Padding(
                  padding: const EdgeInsets.only(top: 2, right: 12),
                  child: SizedBox(
                    width: 24,
                    height: 24,
                    child: isUpdating
                        ? const Center(
                            child: SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Color(0xFF4F46E5),
                              ),
                            ),
                          )
                        : Checkbox(
                            key: Key('publish_checkbox_${item.id}'),
                            value: isSelected,
                            onChanged:
                                isUpdating ? null : (_) => _toggleItem(item),
                            activeColor: const Color(0xFF4F46E5),
                            checkColor: Colors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(6),
                            ),
                            side: BorderSide(
                              color: isSelected
                                  ? const Color(0xFF4F46E5)
                                  : const Color(0xFF94A3B8),
                              width: 1.5,
                            ),
                          ),
                  ),
                ),

                // Deliverable details
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Badges row: Category + Confirmed badge
                      Row(
                        children: [
                          // Category badge
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: catColor.withAlpha(20),
                              borderRadius: BorderRadius.circular(6),
                              border:
                                  Border.all(color: catColor.withAlpha(70)),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(catIcon, color: catColor, size: 12),
                                const SizedBox(width: 4),
                                Text(
                                  (item.category ?? 'Other').toUpperCase(),
                                  style: TextStyle(
                                    color: catColor,
                                    fontSize: 10,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 6),

                          // Verified confirmation badge
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: const Color(0xFFECFDF5),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: const Color(0xFFA7F3D0),
                              ),
                            ),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.verified_rounded,
                                  color: Color(0xFF059669),
                                  size: 12,
                                ),
                                SizedBox(width: 4),
                                Text(
                                  'CONFIRMED',
                                  style: TextStyle(
                                    color: Color(0xFF059669),
                                    fontSize: 10,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          const Spacer(),

                          // Visibility state pill
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? const Color(0xFFECFDF5)
                                  : const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 6,
                                  height: 6,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: isSelected
                                        ? const Color(0xFF059669)
                                        : const Color(0xFF94A3B8),
                                  ),
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  isSelected ? 'Public' : 'Private',
                                  style: TextStyle(
                                    color: isSelected
                                        ? const Color(0xFF059669)
                                        : const Color(0xFF64748B),
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(height: 8),

                      // Title
                      Text(
                        item.title,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF0F172A),
                          height: 1.3,
                        ),
                      ),

                      if (item.description != null &&
                          item.description!.trim().isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(
                          item.description!.trim(),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF64748B),
                            height: 1.3,
                          ),
                        ),
                      ],

                      if (item.dateRange != null &&
                          item.dateRange!.trim().isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Row(
                          children: [
                            const Icon(
                              Icons.calendar_today_outlined,
                              size: 11,
                              color: Color(0xFF94A3B8),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              item.dateRange!.trim(),
                              style: const TextStyle(
                                fontSize: 11,
                                color: Color(0xFF64748B),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return EmptyStateView(
      icon: _searchQuery.isNotEmpty
          ? Icons.search_off_rounded
          : Icons.fact_check_outlined,
      badgeSize: 84,
      iconSize: 42,
      title: 'No Confirmed Deliverables',
      description: _searchQuery.isNotEmpty
          ? 'No confirmed deliverables match "$_searchQuery". Try clearing your search.'
          : 'Only deliverables confirmed by your team peers can be featured on your passport. Submit or request confirmations for your work to publish them.',
      primaryAction: _searchQuery.isNotEmpty
          ? OutlinedButton.icon(
              onPressed: () {
                _searchController.clear();
                setState(() {
                  _searchQuery = '';
                });
              },
              icon: const Icon(Icons.clear_rounded, size: 16),
              label: const Text('Clear Search'),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF4F46E5),
                side: const BorderSide(color: Color(0xFF4F46E5)),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            )
          : null,
    );
  }
}
