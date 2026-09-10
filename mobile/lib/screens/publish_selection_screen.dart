import 'package:flutter/material.dart';
import '../models/contribution.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';

/// Screen allowing builders to select which of their confirmed deliverables
/// should be visible on their public BuildCrew Passport.
class PublishSelectionScreen extends StatefulWidget {
  static const String routeName = '/publish-selection';

  final String? projectId;
  final String? projectName;
  final List<Contribution>? initialContributions;
  final ProjectService? projectService;
  final StorageService? storageService;
  final ValueChanged<Set<String>>? onSelectionChanged;
  final VoidCallback? onSave;

  const PublishSelectionScreen({
    super.key,
    this.projectId,
    this.projectName,
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

  final TextEditingController _searchController = TextEditingController();
  final Set<String> _selectedIds = {};
  final Set<String> _updatingIds = {};

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
    try {
      _currentUserId = await _storageService.getUserId();
    } catch (_) {}

    if (widget.initialContributions == null &&
        _resolvedProjectId != null &&
        _resolvedProjectId!.isNotEmpty) {
      await _fetchContributions();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is Map<String, dynamic>) {
      bool shouldFetch = false;
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
      if (shouldFetch && widget.initialContributions == null && _confirmedContributions.isEmpty) {
        _fetchContributions();
      }
    }
  }

  void _loadItems(List<Contribution> list) {
    // Only confirmed deliverables that are NOT disputed or needing review
    final confirmed = list
        .where((c) => c.isConfirmed && !c.needsReview && !c.isDisputed)
        .toList();

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

  Future<void> _toggleItem(Contribution item) async {
    final id = item.id;
    if (_updatingIds.contains(id)) return; // Prevent concurrent requests for same item

    final wasSelected = _selectedIds.contains(id);
    final willSelect = !wasSelected;

    // 1. Optimistic UI update
    setState(() {
      if (willSelect) {
        _selectedIds.add(id);
      } else {
        _selectedIds.remove(id);
      }
      _updatingIds.add(id);
    });
    widget.onSelectionChanged?.call(Set.from(_selectedIds));

    // 2. Call backend endpoint
    try {
      if (willSelect) {
        final updated = await _projectService.publishContribution(id);
        if (!mounted) return;
        _updateContributionInList(updated);
      } else {
        final updated = await _projectService.unpublishContribution(id);
        if (!mounted) return;
        _updateContributionInList(updated);
      }
    } catch (e) {
      if (!mounted) return;

      // 3. Rollback on failure
      setState(() {
        if (willSelect) {
          _selectedIds.remove(id);
        } else {
          _selectedIds.add(id);
        }
      });
      widget.onSelectionChanged?.call(Set.from(_selectedIds));

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.error_outline_rounded,
                  color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  e.toString(),
                  style: const TextStyle(fontSize: 13),
                ),
              ),
            ],
          ),
          backgroundColor: Colors.red.shade700,
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _updatingIds.remove(id);
        });
      }
    }
  }

  void _updateContributionInList(Contribution updated) {
    setState(() {
      final index = _confirmedContributions.indexWhere((c) => c.id == updated.id);
      if (index != -1) {
        _confirmedContributions[index] = updated;
      }
    });
  }

  Future<void> _selectAll() async {
    final toPublish = _filteredContributions
        .where((c) => !_selectedIds.contains(c.id))
        .toList();
    for (final c in toPublish) {
      await _toggleItem(c);
    }
  }

  Future<void> _deselectAll() async {
    final toUnpublish = _filteredContributions
        .where((c) => _selectedIds.contains(c.id))
        .toList();
    for (final c in toUnpublish) {
      await _toggleItem(c);
    }
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

    return Scaffold(
      backgroundColor: const Color(0xFF0B0F19),
      appBar: AppBar(
        backgroundColor: const Color(0xFF151C2C),
        elevation: 0,
        leading: IconButton(
          key: const Key('publish_back_button'),
          icon: const Icon(Icons.arrow_back_rounded, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Select What to Publish',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
            Text(
              _resolvedProjectName != null && _resolvedProjectName!.isNotEmpty
                  ? 'Passport Visibility • $_resolvedProjectName'
                  : 'Passport Visibility Controls',
              style: const TextStyle(
                fontSize: 12,
                color: Color(0xFF94A3B8),
              ),
            ),
          ],
        ),
        actions: [
          if (filtered.isNotEmpty)
            TextButton(
              key: const Key('publish_toggle_all_btn'),
              onPressed: isAllSelected ? _deselectAll : _selectAll,
              child: Text(
                isAllSelected ? 'Deselect All' : 'Select All',
                style: const TextStyle(
                  color: Color(0xFF60A5FA),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          // Header summary card
          Container(
            width: double.infinity,
            margin: const EdgeInsets.fromLTRB(16, 16, 16, 12),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF1E293B), Color(0xFF0F172A)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFF334155)),
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
                        color: const Color(0xFF2563EB).withAlpha(40),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: const Color(0xFF3B82F6).withAlpha(80),
                        ),
                      ),
                      child: const Icon(
                        Icons.verified_user_rounded,
                        color: Color(0xFF60A5FA),
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
                              color: Colors.white,
                            ),
                          ),
                          SizedBox(height: 4),
                          Text(
                            'Choose which confirmed deliverables are featured on your public passport profile. Unchecked items remain private to your team.',
                            style: TextStyle(
                              fontSize: 12,
                              color: Color(0xFF94A3B8),
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
                      color: const Color(0xFF3B82F6),
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
              style: const TextStyle(color: Colors.white, fontSize: 14),
              decoration: InputDecoration(
                filled: true,
                fillColor: const Color(0xFF151C2C),
                hintText: 'Search confirmed deliverables...',
                hintStyle: const TextStyle(
                  color: Color(0xFFB0BEC5),
                  fontSize: 13,
                ),
                prefixIcon: const Icon(
                  Icons.search_rounded,
                  color: Color(0xFF94A3B8),
                  size: 20,
                ),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear_rounded,
                            color: Color(0xFF94A3B8), size: 18),
                        onPressed: () {
                          _searchController.clear();
                          setState(() {
                            _searchQuery = '';
                          });
                        },
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(vertical: 12),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFF1E293B)),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFF1E293B)),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFF2563EB)),
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
                color: Colors.red.withAlpha(25),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.red.withAlpha(70)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.error_outline_rounded,
                      color: Colors.redAccent, size: 20),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _errorMessage!,
                      style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                    ),
                  ),
                  TextButton(
                    onPressed: _fetchContributions,
                    child: const Text('Retry', style: TextStyle(color: Colors.redAccent)),
                  ),
                ],
              ),
            ),

          // Contributions list or empty state or loader
          Expanded(
            child: _isLoading
                ? const Center(
                    child: CircularProgressIndicator(
                      color: Color(0xFF2563EB),
                    ),
                  )
                : RefreshIndicator(
                    onRefresh: _fetchContributions,
                    color: const Color(0xFF2563EB),
                    backgroundColor: const Color(0xFF151C2C),
                    child: filtered.isEmpty
                        ? _buildEmptyState()
                        : ListView.builder(
                            key: const Key('publish_selection_list'),
                            padding: const EdgeInsets.fromLTRB(16, 4, 16, 80),
                            itemCount: filtered.length,
                            itemBuilder: (context, index) {
                              final item = filtered[index];
                              final isSelected = _selectedIds.contains(item.id);
                              final isUpdating = _updatingIds.contains(item.id);
                              return _buildContributionCheckCard(
                                item,
                                isSelected,
                                isUpdating,
                              );
                            },
                          ),
                  ),
          ),
        ],
      ),

      // Bottom action bar
      bottomNavigationBar: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFF151C2C),
          border: const Border(
            top: BorderSide(color: Color(0xFF1E293B)),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withAlpha(80),
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
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      totalSelected == 1
                          ? '1 deliverable visible on passport'
                          : '$totalSelected deliverables visible on passport',
                      style: const TextStyle(
                        fontSize: 11,
                        color: Color(0xFF94A3B8),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              ElevatedButton.icon(
                key: const Key('publish_save_button'),
                onPressed: () {
                  widget.onSave?.call();
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Row(
                        children: [
                          const Icon(Icons.check_circle_rounded,
                              color: Colors.white, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              'Updated passport: $totalSelected deliverables published.',
                            ),
                          ),
                        ],
                      ),
                      backgroundColor: const Color(0xFF10B981),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF2563EB),
                  foregroundColor: Colors.white,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                icon: const Icon(Icons.check_rounded, size: 18),
                label: const Text(
                  'Save Passport',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                ),
              ),
            ],
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
          color: color.withAlpha(20),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withAlpha(60)),
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
                  fontWeight: FontWeight.w600,
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
        color: isSelected
            ? const Color(0xFF151C2C)
            : const Color(0xFF111827).withAlpha(160),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isSelected ? const Color(0xFF3B82F6) : const Color(0xFF1E293B),
          width: isSelected ? 1.5 : 1.0,
        ),
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
                // Custom checkbox or in-flight spinner
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
                                color: Color(0xFF3B82F6),
                              ),
                            ),
                          )
                        : Checkbox(
                            key: Key('publish_checkbox_${item.id}'),
                            value: isSelected,
                            onChanged: isUpdating ? null : (_) => _toggleItem(item),
                            activeColor: const Color(0xFF2563EB),
                            checkColor: Colors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(6),
                            ),
                            side: BorderSide(
                              color: isSelected
                                  ? const Color(0xFF3B82F6)
                                  : const Color(0xFF64748B),
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
                              color: catColor.withAlpha(25),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(color: catColor.withAlpha(80)),
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
                              color: const Color(0xFF10B981).withAlpha(25),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: const Color(0xFF10B981).withAlpha(80),
                              ),
                            ),
                            child: const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.verified_rounded,
                                  color: Color(0xFF10B981),
                                  size: 12,
                                ),
                                SizedBox(width: 4),
                                Text(
                                  'CONFIRMED',
                                  style: TextStyle(
                                    color: Color(0xFF10B981),
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
                                  ? const Color(0xFF10B981).withAlpha(20)
                                  : const Color(0xFF64748B).withAlpha(20),
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
                                        ? const Color(0xFF10B981)
                                        : const Color(0xFF64748B),
                                  ),
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  isSelected ? 'Public' : 'Private',
                                  style: TextStyle(
                                    color: isSelected
                                        ? const Color(0xFF10B981)
                                        : const Color(0xFF94A3B8),
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
                          color: Colors.white,
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
                            color: Color(0xFF94A3B8),
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
                              color: Color(0xFF64748B),
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
    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: const Color(0xFF151C2C),
                        shape: BoxShape.circle,
                        border: Border.all(color: const Color(0xFF1E293B)),
                      ),
                      child: const Icon(
                        Icons.fact_check_outlined,
                        size: 48,
                        color: Color(0xFF64748B),
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'No Confirmed Deliverables',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _searchQuery.isNotEmpty
                          ? 'No confirmed deliverables match "$_searchQuery". Try clearing your search.'
                          : 'Only deliverables confirmed by your team peers can be featured on your passport. Submit or request confirmations for your work to publish them.',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF94A3B8),
                        height: 1.4,
                      ),
                    ),
                    if (_searchQuery.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      OutlinedButton(
                        onPressed: () {
                          _searchController.clear();
                          setState(() {
                            _searchQuery = '';
                          });
                        },
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF60A5FA),
                          side: const BorderSide(color: Color(0xFF2563EB)),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                        child: const Text('Clear Search'),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
