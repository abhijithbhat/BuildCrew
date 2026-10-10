import 'package:flutter/material.dart';
import '../models/project.dart';
import '../services/project_service.dart';
import '../theme/app_colors.dart';
import '../utils/error_messages.dart';
import '../widgets/empty_state_view.dart';
import '../widgets/connection_error_retry_widget.dart';
import '../widgets/project_card.dart';
import 'create_project_screen.dart';
import 'invite_teammate_screen.dart';
import 'join_project_screen.dart';

class MyProjectsScreen extends StatefulWidget {
  static const String routeName = '/projects';

  final ProjectService? projectService;

  const MyProjectsScreen({super.key, this.projectService});

  @override
  State<MyProjectsScreen> createState() => _MyProjectsScreenState();
}

class _MyProjectsScreenState extends State<MyProjectsScreen> {
  late final ProjectService _projectService;
  final TextEditingController _searchController = TextEditingController();

  List<Project> _projects = [];
  bool _isLoading = true;
  String? _errorMessage;
  String _selectedFilter = 'All'; // 'All', 'Owned', 'Joined'
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _fetchProjects();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _fetchProjects() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final projects = await _projectService.listProjects(includeArchived: true);
      if (mounted) {
        setState(() {
          _projects = projects;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = friendlyError(e);
          _isLoading = false;
        });
      }
    }
  }

  List<Project> get _filteredProjects {
    return _projects.where((p) {
      // Role filter
      if (_selectedFilter == 'Owned' && (p.role ?? '').toLowerCase() != 'owner') {
        return false;
      }
      if (_selectedFilter == 'Joined' && (p.role ?? '').toLowerCase() != 'member') {
        return false;
      }
      // Search query
      if (_searchQuery.isNotEmpty) {
        final matchesName =
            p.name.toLowerCase().contains(_searchQuery.toLowerCase());
        final matchesDesc = (p.description ?? '')
            .toLowerCase()
            .contains(_searchQuery.toLowerCase());
        return matchesName || matchesDesc;
      }
      return true;
    }).toList();
  }

  void _handleInvite(Project project) {
    Navigator.pushNamed(
      context,
      InviteTeammateScreen.routeName,
      arguments: project,
    );
  }

  Future<void> _openJoinProjectScreen() async {
    final result = await Navigator.pushNamed(
      context,
      JoinProjectScreen.routeName,
    );
    if (result != null && mounted) {
      _fetchProjects();
    }
  }

  @override
  Widget build(BuildContext context) {
    final displayProjects = _filteredProjects;
    final activeProjects =
        displayProjects.where((p) => !p.isArchived).toList();
    final archivedProjects =
        displayProjects.where((p) => p.isArchived).toList();
    final hasArchivedSection = archivedProjects.isNotEmpty;
    final totalItemCount = activeProjects.length +
        (hasArchivedSection ? (1 + archivedProjects.length) : 0);

    return Scaffold(
      backgroundColor: AppColors.champagne,
      appBar: AppBar(
        title: const Text(
          'My Projects',
          style: TextStyle(
            color: AppColors.emeraldInk,
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
        centerTitle: true,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: AppColors.champagne,
        foregroundColor: AppColors.emeraldInk,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(
            color: AppColors.inputBorder,
            height: 1.0,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(
              Icons.group_add_outlined,
              color: AppColors.emeraldInk,
            ),
            tooltip: 'Join with Code',
            onPressed: _openJoinProjectScreen,
          ),
          IconButton(
            icon: const Icon(
              Icons.add_circle_outline,
              color: AppColors.emeraldInk,
            ),
            tooltip: 'Create Project',
            onPressed: () async {
              final result = await Navigator.pushNamed(
                context,
                CreateProjectScreen.routeName,
              );
              if (result != null || mounted) {
                _fetchProjects();
              }
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Search and Filter Header Container
            Container(
              decoration: const BoxDecoration(
                color: Colors.white,
                border: Border(
                  bottom: BorderSide(
                    color: AppColors.divider,
                    width: 1.0,
                  ),
                ),
              ),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
              child: Column(
                children: [
                  // Search TextField
                  TextField(
                    controller: _searchController,
                    onChanged: (val) {
                      setState(() {
                        _searchQuery = val.trim();
                      });
                    },
                    style: const TextStyle(
                      fontSize: 14,
                      color: AppColors.emeraldInk,
                    ),
                    decoration: InputDecoration(
                      hintText: 'Search projects by name or keywords...',
                      hintStyle: const TextStyle(
                        color: AppColors.hint,
                        fontSize: 13,
                      ),
                      prefixIcon: const Icon(
                        Icons.search,
                        color: AppColors.textMuted,
                        size: 20,
                      ),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(
                                Icons.clear,
                                size: 18,
                                color: AppColors.textMuted,
                              ),
                              onPressed: () {
                                _searchController.clear();
                                setState(() {
                                  _searchQuery = '';
                                });
                              },
                            )
                          : null,
                      filled: true,
                      fillColor: Colors.white,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 12,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: AppColors.inputBorder,
                          width: 1.0,
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: AppColors.inputBorder,
                          width: 1.0,
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: AppColors.emeraldInk,
                          width: 1.5,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Filter ChoiceChips
                  Row(
                    children: ['All', 'Owned', 'Joined'].map((filter) {
                      final isSelected = _selectedFilter == filter;
                      return Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: ChoiceChip(
                          label: Text(filter),
                          selected: isSelected,
                          selectedColor: AppColors.emeraldInk,
                          checkmarkColor: AppColors.champagne,
                          labelStyle: TextStyle(
                            color: isSelected ? AppColors.champagne : AppColors.bodyText,
                            fontSize: 12,
                            fontWeight: isSelected
                                ? FontWeight.w600
                                : FontWeight.w500,
                          ),
                          backgroundColor: Colors.white,
                          side: BorderSide(
                            color: isSelected ? AppColors.emeraldInk : AppColors.inputBorder,
                          ),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(20),
                          ),
                          onSelected: (selected) {
                            if (selected) {
                              setState(() {
                                _selectedFilter = filter;
                              });
                            }
                          },
                        ),
                      );
                    }).toList(),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 6),

            // Content Area: Loading / Error / Empty / List
            Expanded(
              child: _isLoading
                  ? const Center(
                      child: CircularProgressIndicator(
                        valueColor:
                            AlwaysStoppedAnimation<Color>(AppColors.emeraldInk),
                      ),
                    )
                  : _errorMessage != null
                      ? ConnectionErrorRetryWidget(
                          title: 'Couldn\'t connect to server',
                          message: _errorMessage,
                          onRetry: _fetchProjects,
                        )
                      : displayProjects.isEmpty
                          ? SingleChildScrollView(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 16, vertical: 24),
                              child: EmptyStateView(
                                icon: _searchQuery.isNotEmpty
                                    ? Icons.search_off_rounded
                                    : Icons.folder_open_rounded,
                                title: 'No Projects Found',
                                description: _searchQuery.isNotEmpty
                                    ? 'No projects match "$_searchQuery". Try another keyword.'
                                    : 'You haven\'t created or joined any projects yet. Start building with your team today!',
                                primaryAction: _searchQuery.isNotEmpty
                                    ? OutlinedButton.icon(
                                         onPressed: () {
                                           _searchController.clear();
                                           setState(() {
                                             _searchQuery = '';
                                           });
                                         },
                                        icon: const Icon(Icons.clear_rounded,
                                            size: 16),
                                        label: const Text('Clear Search'),
                                        style: OutlinedButton.styleFrom(
                                          foregroundColor:
                                              AppColors.emeraldInk,
                                          side: const BorderSide(
                                              color: AppColors.inputBorder),
                                          shape: RoundedRectangleBorder(
                                            borderRadius:
                                                BorderRadius.circular(12),
                                          ),
                                        ),
                                      )
                                    : ElevatedButton.icon(
                                        onPressed: () async {
                                          final res =
                                              await Navigator.pushNamed(
                                            context,
                                            CreateProjectScreen.routeName,
                                          );
                                          if (res != null || mounted) {
                                            _fetchProjects();
                                          }
                                        },
                                        icon: const Icon(Icons.add, size: 18),
                                        label: const Text('Create Project'),
                                        style: ElevatedButton.styleFrom(
                                          backgroundColor:
                                              AppColors.emeraldInk,
                                          foregroundColor: Colors.white,
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 18,
                                            vertical: 12,
                                          ),
                                          shape: RoundedRectangleBorder(
                                            borderRadius:
                                                BorderRadius.circular(12),
                                          ),
                                        ),
                                      ),
                                secondaryAction: _searchQuery.isNotEmpty
                                    ? null
                                    : OutlinedButton.icon(
                                        onPressed: _openJoinProjectScreen,
                                        icon: const Icon(
                                          Icons.group_add_outlined,
                                          size: 18,
                                          color: AppColors.emeraldInk,
                                        ),
                                        label: const Text(
                                          'Join with Code',
                                          style: TextStyle(
                                            color: AppColors.emeraldInk,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        style: OutlinedButton.styleFrom(
                                          side: const BorderSide(
                                            color: AppColors.divider,
                                            width: 1.2,
                                          ),
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 16,
                                            vertical: 12,
                                          ),
                                          shape: RoundedRectangleBorder(
                                            borderRadius:
                                                BorderRadius.circular(12),
                                          ),
                                        ),
                                      ),
                              ),
                            )
                          : RefreshIndicator(
                              color: AppColors.emeraldInk,
                              onRefresh: _fetchProjects,
                              child: ListView.builder(
                                itemCount: totalItemCount,
                                padding: const EdgeInsets.only(
                                  bottom: 80,
                                  top: 6,
                                ),
                                itemBuilder: (context, index) {
                                  if (index < activeProjects.length) {
                                    final project = activeProjects[index];
                                    return ProjectCard(
                                      project: project,
                                      onTap: () async {
                                        final res = await Navigator.pushNamed(
                                          context,
                                          '/project-detail',
                                          arguments: project,
                                        );
                                        if (res != null || mounted) {
                                          _fetchProjects();
                                        }
                                      },
                                      onInviteTap: () => _handleInvite(project),
                                    );
                                  }

                                  final archivedIndex =
                                      index - activeProjects.length;
                                  if (archivedIndex == 0) {
                                    return Padding(
                                      padding: const EdgeInsets.fromLTRB(
                                          16, 20, 16, 8),
                                      child: Row(
                                        children: [
                                          const Icon(
                                            Icons.archive_outlined,
                                            size: 18,
                                            color: AppColors.textMuted,
                                          ),
                                          const SizedBox(width: 8),
                                          const Text(
                                            'Archived',
                                            style: TextStyle(
                                              fontSize: 14,
                                              fontWeight: FontWeight.w700,
                                              color: AppColors.textMuted,
                                              letterSpacing: 0.2,
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          Container(
                                            padding: const EdgeInsets.symmetric(
                                                horizontal: 8, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: Colors.grey.shade200,
                                              borderRadius:
                                                  BorderRadius.circular(10),
                                            ),
                                            child: Text(
                                              '${archivedProjects.length}',
                                              style: TextStyle(
                                                fontSize: 11,
                                                fontWeight: FontWeight.w600,
                                                color: Colors.grey.shade700,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    );
                                  }

                                  final project =
                                      archivedProjects[archivedIndex - 1];
                                  return ProjectCard(
                                    project: project,
                                    onTap: () async {
                                      final res = await Navigator.pushNamed(
                                        context,
                                        '/project-detail',
                                        arguments: project,
                                      );
                                      if (res != null || mounted) {
                                        _fetchProjects();
                                      }
                                    },
                                    onInviteTap: null,
                                  );
                                },
                              ),
                            ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          final result = await Navigator.pushNamed(
            context,
            CreateProjectScreen.routeName,
          );
          if (result != null || mounted) {
            _fetchProjects();
          }
        },
        backgroundColor: AppColors.emeraldInk,
        foregroundColor: AppColors.champagne,
        elevation: 3,
        icon: const Icon(Icons.add),
        label: const Text(
          'New Project',
          style: TextStyle(
            fontWeight: FontWeight.w600,
            letterSpacing: 0.2,
          ),
        ),
      ),
    );
  }
}
