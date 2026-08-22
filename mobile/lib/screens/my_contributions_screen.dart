import 'package:flutter/material.dart';
import '../models/contribution.dart';
import '../models/project.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';
import '../widgets/contribution_card.dart';
import 'add_contribution_screen.dart';

class MyContributionsScreen extends StatefulWidget {
  static const String routeName = '/my-contributions';

  final String? projectId;
  final Project? project;
  final ProjectService? projectService;
  final StorageService? storageService;

  const MyContributionsScreen({
    super.key,
    this.projectId,
    this.project,
    this.projectService,
    this.storageService,
  });

  @override
  State<MyContributionsScreen> createState() => _MyContributionsScreenState();
}

class _MyContributionsScreenState extends State<MyContributionsScreen> {
  late final ProjectService _projectService;
  late final StorageService _storageService;
  late final TextEditingController _searchController;

  String? _resolvedProjectId;
  String? _currentUserId;
  String? _currentUserName;

  List<Contribution> _allContributions = [];
  bool _isLoading = false;
  String? _errorMessage;

  String _activeStatTab = 'total'; // 'total' | 'nonCode' | 'verified' | 'declared'
  String _selectedCategory = 'all';
  String _selectedStatus = 'all';
  String _searchQuery = '';

  static const List<Map<String, dynamic>> _categoryFilters = [
    {'id': 'all', 'label': 'All Impact', 'icon': Icons.apps_rounded},
    {'id': 'code', 'label': 'Code & Commits', 'icon': Icons.terminal_rounded},
    {'id': 'design', 'label': 'UI/UX Design', 'icon': Icons.palette_outlined},
    {'id': 'research', 'label': 'User Research', 'icon': Icons.science_outlined},
    {'id': 'documentation', 'label': 'Documentation', 'icon': Icons.description_outlined},
    {'id': 'presentation', 'label': 'Presentations', 'icon': Icons.slideshow_outlined},
    {'id': 'devops', 'label': 'DevOps & Infra', 'icon': Icons.cloud_sync_outlined},
    {'id': 'testing', 'label': 'QA & Testing', 'icon': Icons.bug_report_outlined},
    {'id': 'other', 'label': 'Other Impact', 'icon': Icons.lightbulb_outline},
  ];

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _storageService = widget.storageService ?? StorageService();
    _searchController = TextEditingController();
    _resolvedProjectId = widget.projectId ?? widget.project?.id;

    _initUserDataAndLoad();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_resolvedProjectId == null) {
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is Map<String, dynamic>) {
        if (args['projectId'] != null) {
          _resolvedProjectId = args['projectId'].toString();
        } else if (args['project'] is Project) {
          _resolvedProjectId = (args['project'] as Project).id;
        }
      } else if (args is Project) {
        _resolvedProjectId = args.id;
      } else if (args is String) {
        _resolvedProjectId = args;
      }

      if (_allContributions.isEmpty && !_isLoading && _resolvedProjectId != null) {
        _loadContributions();
      }
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _initUserDataAndLoad() async {
    _currentUserId = await _storageService.getUserId();
    _currentUserName = await _storageService.getUserName();
    if (_resolvedProjectId != null) {
      await _loadContributions();
    }
  }

  Future<void> _loadContributions() async {
    if (_resolvedProjectId == null || _resolvedProjectId!.trim().isEmpty) {
      setState(() {
        _errorMessage = 'Project ID is missing. Please open from a project.';
        _isLoading = false;
      });
      return;
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
      setState(() {
        _allContributions = list;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = e.toString();
      });
    }
  }

  List<Contribution> get _filteredContributions {
    return _allContributions.where((c) {
      // 1. User Scoping fallback (if not filtered by backend)
      if (_currentUserId != null && _currentUserId!.isNotEmpty) {
        if (c.contributor.isNotEmpty && c.contributor != _currentUserId) {
          return false;
        }
      }

      // 2. Active Top Stat Tab filtering
      if (_activeStatTab == 'nonCode') {
        final isGitHub = c.sourceType == 'github_commit' ||
            c.sourceType == 'github_pr' ||
            c.sourceType == 'github_issue';
        final isCodeCat = (c.category ?? '').toLowerCase() == 'code';
        if (isGitHub || isCodeCat) {
          return false;
        }
      } else if (_activeStatTab == 'verified') {
        if (!c.isSourceVerified) {
          return false;
        }
      } else if (_activeStatTab == 'declared') {
        if (c.verificationStatus.toLowerCase() != 'self-declared') {
          return false;
        }
      }

      // 3. Category filtering (from chips carousel)
      if (_selectedCategory != 'all') {
        final cat = (c.category ?? '').toLowerCase();
        if (cat != _selectedCategory.toLowerCase()) {
          // Check for code / github mapping
          if (_selectedCategory == 'code' &&
              (c.sourceType == 'github_commit' || c.sourceType == 'github_pr')) {
            // Keep code match
          } else {
            return false;
          }
        }
      }

      // 4. Status filtering
      if (_selectedStatus != 'all') {
        if (c.verificationStatus.toLowerCase() != _selectedStatus.toLowerCase()) {
          return false;
        }
      }

      // 5. Search query filtering
      if (_searchQuery.trim().isNotEmpty) {
        final query = _searchQuery.trim().toLowerCase();
        final titleMatch = c.title.toLowerCase().contains(query);
        final descMatch = c.description?.toLowerCase().contains(query) ?? false;
        final catMatch = c.category?.toLowerCase().contains(query) ?? false;
        final sourceMatch = (c.sourceType ?? '').toLowerCase().contains(query);

        if (!titleMatch && !descMatch && !catMatch && !sourceMatch) {
          return false;
        }
      }

      return true;
    }).toList();
  }

  Future<void> _openAddContributionScreen() async {
    if (_resolvedProjectId == null) return;
    final result = await Navigator.pushNamed(
      context,
      AddContributionScreen.routeName,
      arguments: {'projectId': _resolvedProjectId},
    );

    if (result != null) {
      await _loadContributions();
    }
  }

  Widget _buildStatCard({
    required String title,
    required String value,
    required IconData icon,
    required Color color,
    VoidCallback? onTap,
    bool isSelected = false,
  }) {
    return Expanded(
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            decoration: BoxDecoration(
              color: isSelected ? color.withAlpha(25) : const Color(0xFF151C2C),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: isSelected ? color : const Color(0xFF1E293B),
                width: isSelected ? 1.5 : 1.0,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Icon(icon, color: color, size: 18),
                    Text(
                      value,
                      style: TextStyle(
                        color: color,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  title,
                  style: TextStyle(
                    color: isSelected ? Colors.white : const Color(0xFF94A3B8),
                    fontSize: 11,
                    fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFilterChip(String id, String label, IconData icon) {
    final isSelected = _selectedCategory == id;
    return GestureDetector(
      onTap: () {
        setState(() {
          _selectedCategory = id;
          if (id == 'all') {
            _activeStatTab = 'total';
          } else {
            _activeStatTab = '';
          }
        });
      },
      child: Container(
        margin: const EdgeInsets.only(right: 8),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF2563EB) : const Color(0xFF151C2C),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: isSelected ? const Color(0xFF3B82F6) : const Color(0xFF1E293B),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 14,
              color: isSelected ? Colors.white : const Color(0xFF94A3B8),
            ),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                color: isSelected ? Colors.white : const Color(0xFF94A3B8),
                fontSize: 12,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmAndDeleteContribution(Contribution c) async {
    if (c.sourceType == 'github_commit' || c.sourceType == 'github_pr') {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: const Color(0xFF151C2C),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: Color(0xFF1E293B)),
          ),
          title: const Row(
            children: [
              Icon(Icons.info_outline_rounded, color: Color(0xFF60A5FA), size: 22),
              SizedBox(width: 8),
              Text('GitHub Contribution', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
            ],
          ),
          content: const Text(
            'This contribution was automatically imported from GitHub. To modify or delete it, please push changes to your GitHub repository.',
            style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13, height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('OK', style: TextStyle(color: Color(0xFF60A5FA))),
            ),
          ],
        ),
      );
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF151C2C),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: Color(0xFF1E293B)),
        ),
        title: const Row(
          children: [
            Icon(Icons.delete_forever_rounded, color: Colors.redAccent, size: 24),
            SizedBox(width: 8),
            Text('Delete Impact Log?', style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Text(
          'Are you sure you want to delete "${c.title}"?\n\nThis will remove the logged deliverable and its attached evidence link from your contribution timeline.',
          style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: Colors.white70)),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red.shade700,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: const Text('Delete Log'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      try {
        await _projectService.deleteContribution(c.id, projectId: _resolvedProjectId);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Row(
                children: [
                  Icon(Icons.check_circle_rounded, color: Colors.white, size: 20),
                  SizedBox(width: 10),
                  Text('Impact log deleted successfully.'),
                ],
              ),
              backgroundColor: Color(0xFF10B981),
              behavior: SnackBarBehavior.floating,
            ),
          );
          _loadContributions();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to delete contribution: $e'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filteredContributions;
    final totalCount = _allContributions.length;
    final nonCodeCount = _allContributions
        .where((c) =>
            c.sourceType != 'github_commit' &&
            c.sourceType != 'github_pr' &&
            c.sourceType != 'github_issue' &&
            (c.category ?? '').toLowerCase() != 'code')
        .length;
    final verifiedCount = _allContributions.where((c) => c.isSourceVerified).length;
    final selfDeclaredCount = _allContributions
        .where((c) => c.verificationStatus.toLowerCase() == 'self-declared')
        .length;

    return Scaffold(
      backgroundColor: const Color(0xFF0B0F19),
      appBar: AppBar(
        backgroundColor: const Color(0xFF151C2C),
        elevation: 0,
        centerTitle: false,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'My Contributions',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
            Text(
              _currentUserName != null && _currentUserName!.isNotEmpty
                  ? 'Personal Log • $_currentUserName'
                  : 'Personal Contribution Feed',
              style: const TextStyle(
                fontSize: 12,
                color: Color(0xFF94A3B8),
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            key: const Key('my_contributions_refresh_btn'),
            icon: const Icon(Icons.refresh_rounded, color: Colors.blueAccent),
            tooltip: 'Refresh',
            onPressed: _isLoading ? null : _loadContributions,
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('my_contributions_add_fab'),
        onPressed: _openAddContributionScreen,
        backgroundColor: const Color(0xFF2563EB),
        icon: const Icon(Icons.add_rounded, color: Colors.white),
        label: const Text(
          'Add Impact',
          style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
        ),
      ),
      body: RefreshIndicator(
        onRefresh: _loadContributions,
        color: const Color(0xFF2563EB),
        child: ListView(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          children: [
            // Error banner
            if (_errorMessage != null) ...[
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.withAlpha(30),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Colors.red.withAlpha(80)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline_rounded, color: Colors.redAccent, size: 20),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _errorMessage!,
                        style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                      ),
                    ),
                    TextButton(
                      onPressed: _loadContributions,
                      child: const Text('Retry', style: TextStyle(color: Colors.white)),
                    ),
                  ],
                ),
              ),
            ],

            // 1. Stats Summary Row
            Row(
              children: [
                _buildStatCard(
                  title: 'Total Logs',
                  value: '$totalCount',
                  icon: Icons.history_edu_rounded,
                  color: const Color(0xFF3B82F6),
                  isSelected: _activeStatTab == 'total',
                  onTap: () {
                    setState(() {
                      _activeStatTab = 'total';
                      _selectedCategory = 'all';
                      _selectedStatus = 'all';
                    });
                  },
                ),
                const SizedBox(width: 8),
                _buildStatCard(
                  title: 'Non-Code Impact',
                  value: '$nonCodeCount',
                  icon: Icons.palette_outlined,
                  color: const Color(0xFF8B5CF6),
                  isSelected: _activeStatTab == 'nonCode',
                  onTap: () {
                    setState(() {
                      if (_activeStatTab == 'nonCode') {
                        _activeStatTab = 'total';
                      } else {
                        _activeStatTab = 'nonCode';
                      }
                      _selectedCategory = 'all';
                      _selectedStatus = 'all';
                    });
                  },
                ),
                const SizedBox(width: 8),
                _buildStatCard(
                  title: 'Verified / Declared',
                  value: '$verifiedCount / $selfDeclaredCount',
                  icon: Icons.verified_user_outlined,
                  color: const Color(0xFF10B981),
                  isSelected: _activeStatTab == 'verified' || _activeStatTab == 'declared',
                  onTap: () {
                    setState(() {
                      _selectedCategory = 'all';
                      if (_activeStatTab == 'verified') {
                        _activeStatTab = 'declared';
                      } else if (_activeStatTab == 'declared') {
                        _activeStatTab = 'total';
                      } else {
                        _activeStatTab = 'verified';
                      }
                    });
                  },
                ),
              ],
            ),
            const SizedBox(height: 16),

            // 2. Search Field
            TextField(
              key: const Key('my_contributions_search_input'),
              controller: _searchController,
              onChanged: (val) {
                setState(() {
                  _searchQuery = val;
                });
              },
              style: const TextStyle(color: Colors.white, fontSize: 14),
              decoration: InputDecoration(
                hintText: 'Search contributions by title, category, or spec...',
                hintStyle: const TextStyle(color: Color(0xFFB0BEC5), fontSize: 13),
                prefixIcon: const Icon(Icons.search_rounded, color: Color(0xFF94A3B8), size: 20),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear_rounded, color: Colors.white70, size: 18),
                        onPressed: () {
                          _searchController.clear();
                          setState(() {
                            _searchQuery = '';
                          });
                        },
                      )
                    : null,
                filled: true,
                fillColor: const Color(0xFF151C2C),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
            const SizedBox(height: 14),

            // 3. Category Filter Chips Carousel
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: _categoryFilters.map((cat) {
                  return _buildFilterChip(
                    cat['id'] as String,
                    cat['label'] as String,
                    cat['icon'] as IconData,
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 16),

            // 4. Contribution Stream Body
            if (_isLoading) ...[
              const SizedBox(height: 60),
              const Center(
                child: CircularProgressIndicator(
                  strokeWidth: 2.5,
                  color: Color(0xFF2563EB),
                ),
              ),
              const SizedBox(height: 16),
              const Center(
                child: Text(
                  'Loading your personal contributions...',
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                ),
              ),
            ] else if (filtered.isEmpty) ...[
              const SizedBox(height: 40),
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: const Color(0xFF151C2C),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFF1E293B)),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2563EB).withAlpha(30),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.assignment_turned_in_outlined,
                        size: 32,
                        color: Color(0xFF3B82F6),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      _searchQuery.isNotEmpty || _selectedCategory != 'all'
                          ? 'No matching contributions found'
                          : 'No contributions logged yet',
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      _searchQuery.isNotEmpty || _selectedCategory != 'all'
                          ? 'Try clearing filters or searching for different keywords.'
                          : 'Declare your non-code impact or sync GitHub activity to show deliverables.',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                    ),
                    const SizedBox(height: 18),
                    ElevatedButton.icon(
                      key: const Key('my_contributions_empty_add_btn'),
                      onPressed: _openAddContributionScreen,
                      icon: const Icon(Icons.add_rounded, color: Colors.white),
                      label: const Text('Log Your First Contribution'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2563EB),
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ] else ...[
              ...filtered.map(
                (c) => ContributionCard(
                  contribution: c,
                  onTap: () {
                    if (c.evidenceLink != null && c.evidenceLink!.isNotEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('Evidence: ${c.evidenceLink}'),
                          backgroundColor: const Color(0xFF2563EB),
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                    }
                  },
                  onLongPress: () => _confirmAndDeleteContribution(c),
                  onDelete: () => _confirmAndDeleteContribution(c),
                ),
              ),
            ],
            const SizedBox(height: 80),
          ],
        ),
      ),
    );
  }
}
