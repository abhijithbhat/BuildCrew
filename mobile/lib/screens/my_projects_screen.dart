import 'package:flutter/material.dart';
import '../models/project.dart';

import '../services/project_service.dart';
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
      backgroundColor: Colors.grey.shade50,
      appBar: AppBar(
        title: const Text(
          'My Projects',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
        actions: [
          IconButton(
            icon: const Icon(Icons.group_add_outlined, color: Colors.blueAccent),
            tooltip: 'Join with Code',
            onPressed: _openJoinProjectScreen,
          ),
          IconButton(
            icon: const Icon(Icons.add_circle_outline, color: Colors.blueAccent),
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
              color: Colors.white,
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
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
                    decoration: InputDecoration(
                      hintText: 'Search projects by name or keywords...',
                      hintStyle: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 13,
                      ),
                      prefixIcon: Icon(Icons.search, color: Colors.grey.shade400, size: 20),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.clear, size: 18),
                              onPressed: () {
                                _searchController.clear();
                                setState(() {
                                  _searchQuery = '';
                                });
                              },
                            )
                          : null,
                      filled: true,
                      fillColor: Colors.grey.shade100,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 10,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide.none,
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),

                  // Filter Chips
                  Row(
                    children: ['All', 'Owned', 'Joined'].map((filter) {
                      final isSelected = _selectedFilter == filter;
                      return Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: ChoiceChip(
                          label: Text(filter),
                          selected: isSelected,
                          selectedColor: Colors.blueAccent,
                          labelStyle: TextStyle(
                            color: isSelected ? Colors.white : Colors.black87,
                            fontSize: 12,
                            fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                          ),
                          backgroundColor: Colors.grey.shade100,
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

            const SizedBox(height: 8),

            // Content Area: Loading / Error / Empty / List
            Expanded(
              child: _isLoading
                  ? const Center(
                      child: CircularProgressIndicator(),
                    )
                  : _errorMessage != null
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24.0),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.error_outline,
                                  size: 48,
                                  color: Colors.red.shade400,
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  'Failed to load projects',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.grey.shade800,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  _errorMessage!,
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontSize: 13,
                                    color: Colors.grey.shade600,
                                  ),
                                ),
                                const SizedBox(height: 20),
                                ElevatedButton.icon(
                                  onPressed: _fetchProjects,
                                  icon: const Icon(Icons.refresh),
                                  label: const Text('Retry'),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.blueAccent,
                                    foregroundColor: Colors.white,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        )
                      : displayProjects.isEmpty
                          ? Center(
                              child: SingleChildScrollView(
                                padding: const EdgeInsets.all(32),
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.all(20),
                                      decoration: BoxDecoration(
                                        color: Colors.blue.shade50,
                                        shape: BoxShape.circle,
                                      ),
                                      child: Icon(
                                        Icons.folder_open_rounded,
                                        size: 56,
                                        color: Colors.blue.shade400,
                                      ),
                                    ),
                                    const SizedBox(height: 20),
                                    const Text(
                                      'No Projects Found',
                                      style: TextStyle(
                                        fontSize: 18,
                                        fontWeight: FontWeight.bold,
                                        color: Colors.black87,
                                      ),
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      _searchQuery.isNotEmpty
                                          ? 'No projects match "$_searchQuery". Try another keyword.'
                                          : 'You haven\'t created or joined any projects yet.',
                                      textAlign: TextAlign.center,
                                      style: TextStyle(
                                        fontSize: 13,
                                        color: Colors.grey.shade600,
                                      ),
                                    ),
                                    const SizedBox(height: 24),
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        ElevatedButton.icon(
                                          onPressed: () async {
                                            final res = await Navigator.pushNamed(
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
                                            backgroundColor: Colors.blueAccent,
                                            foregroundColor: Colors.white,
                                            padding: const EdgeInsets.symmetric(
                                              horizontal: 16,
                                              vertical: 12,
                                            ),
                                            shape: RoundedRectangleBorder(
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 12),
                                        OutlinedButton.icon(
                                          onPressed: _openJoinProjectScreen,
                                          icon: const Icon(Icons.group_add_outlined, size: 18),
                                          label: const Text('Join with Code'),
                                          style: OutlinedButton.styleFrom(
                                            padding: const EdgeInsets.symmetric(
                                              horizontal: 16,
                                              vertical: 12,
                                            ),
                                            shape: RoundedRectangleBorder(
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                          ),
                                        ),

                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            )
                          : RefreshIndicator(
                              onRefresh: _fetchProjects,
                              child: ListView.builder(
                                itemCount: displayProjects.length,
                                padding: const EdgeInsets.only(bottom: 80, top: 4),
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
        backgroundColor: Colors.blueAccent,
        foregroundColor: Colors.white,
        elevation: 3,
        icon: const Icon(Icons.add),
        label: const Text(
          'New Project',
          style: TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}
