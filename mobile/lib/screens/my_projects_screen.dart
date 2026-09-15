import 'package:flutter/material.dart';
import '../models/project.dart';
import '../services/project_service.dart';
import '../widgets/empty_state_view.dart';
import '../widgets/project_card.dart';
import 'create_project_screen.dart';
import 'invite_teammate_screen.dart';
import 'join_project_screen.dart';

class MyProjectsScreen extends StatefulWidget {
  static const String routeName = '/projects';

  const MyProjectsScreen({super.key});

  @override
  State<MyProjectsScreen> createState() => _MyProjectsScreenState();
}

class _MyProjectsScreenState extends State<MyProjectsScreen> {
  final ProjectService _projectService = ProjectService();
  final TextEditingController _searchController = TextEditingController();

  List<Project> _projects = [];
  bool _isLoading = true;
  String? _errorMessage;
  String _selectedFilter = 'All'; // 'All', 'Owned', 'Joined'
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
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
      final projects = await _projectService.listProjects();
      if (mounted) {
        setState(() {
          _projects = projects;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString();
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

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text(
          'My Projects',
          style: TextStyle(
            color: Color(0xFF0F172A),
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
        centerTitle: true,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF0F172A),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(
            color: const Color(0xFFE2E8F0),
            height: 1.0,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(
              Icons.group_add_outlined,
              color: Color(0xFF4F46E5),
            ),
            tooltip: 'Join with Code',
            onPressed: _openJoinProjectScreen,
          ),
          IconButton(
            icon: const Icon(
              Icons.add_circle_outline,
              color: Color(0xFF4F46E5),
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
                    color: Color(0xFFE2E8F0),
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
                      color: Color(0xFF0F172A),
                    ),
                    decoration: InputDecoration(
                      hintText: 'Search projects by name or keywords...',
                      hintStyle: const TextStyle(
                        color: Color(0xFF94A3B8),
                        fontSize: 13,
                      ),
                      prefixIcon: const Icon(
                        Icons.search,
                        color: Color(0xFF64748B),
                        size: 20,
                      ),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(
                                Icons.clear,
                                size: 18,
                                color: Color(0xFF64748B),
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
                      fillColor: const Color(0xFFF8FAFC),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 12,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: Color(0xFFE2E8F0),
                          width: 1.0,
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: Color(0xFFE2E8F0),
                          width: 1.0,
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(
                          color: Color(0xFF4F46E5),
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
                          selectedColor: const Color(0xFF4F46E5),
                          labelStyle: TextStyle(
                            color: isSelected ? Colors.white : const Color(0xFF475569),
                            fontSize: 12,
                            fontWeight: isSelected
                                ? FontWeight.w600
                                : FontWeight.w500,
                          ),
                          backgroundColor: const Color(0xFFF1F5F9),
                          side: BorderSide.none,
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
                            AlwaysStoppedAnimation<Color>(Color(0xFF4F46E5)),
                      ),
                    )
                  : _errorMessage != null
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24.0),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(16),
                                  decoration: const BoxDecoration(
                                    color: Color(0xFFFEF2F2),
                                    shape: BoxShape.circle,
                                  ),
                                  child: const Icon(
                                    Icons.error_outline_rounded,
                                    size: 40,
                                    color: Color(0xFFDC2626),
                                  ),
                                ),
                                const SizedBox(height: 16),
                                const Text(
                                  'Failed to load projects',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFF0F172A),
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  _errorMessage!,
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(
                                    fontSize: 13,
                                    color: Color(0xFF64748B),
                                  ),
                                ),
                                const SizedBox(height: 20),
                                ElevatedButton.icon(
                                  onPressed: _fetchProjects,
                                  icon: const Icon(Icons.refresh, size: 18),
                                  label: const Text('Retry'),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: const Color(0xFF4F46E5),
                                    foregroundColor: Colors.white,
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
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
                                              const Color(0xFF4F46E5),
                                          side: const BorderSide(
                                              color: Color(0xFFC7D2FE)),
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
                                              const Color(0xFF4F46E5),
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
                                          color: Color(0xFF0F172A),
                                        ),
                                        label: const Text(
                                          'Join with Code',
                                          style: TextStyle(
                                            color: Color(0xFF0F172A),
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        style: OutlinedButton.styleFrom(
                                          side: const BorderSide(
                                            color: Color(0xFFCBD5E1),
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
                              color: const Color(0xFF4F46E5),
                              onRefresh: _fetchProjects,
                              child: ListView.builder(
                                itemCount: displayProjects.length,
                                padding: const EdgeInsets.only(
                                  bottom: 80,
                                  top: 6,
                                ),
                                itemBuilder: (context, index) {
                                  final project = displayProjects[index];
                                  return ProjectCard(
                                    project: project,
                                    onTap: () {
                                      Navigator.pushNamed(
                                        context,
                                        '/project-detail',
                                        arguments: project,
                                      );
                                    },
                                    onInviteTap: () => _handleInvite(project),
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
        backgroundColor: const Color(0xFF4F46E5),
        foregroundColor: Colors.white,
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
