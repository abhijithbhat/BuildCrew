import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/project.dart';
import '../models/role_agreement.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';
import 'declare_role_screen.dart';

class TeamRolesScreen extends StatefulWidget {
  static const String routeName = '/team-roles';

  final String? projectId;
  final String? projectName;
  final ProjectService? projectService;
  final StorageService? storageService;

  const TeamRolesScreen({
    super.key,
    this.projectId,
    this.projectName,
    this.projectService,
    this.storageService,
  });

  @override
  State<TeamRolesScreen> createState() => _TeamRolesScreenState();
}

class _TeamRolesScreenState extends State<TeamRolesScreen> {
  late final ProjectService _projectService;
  late final StorageService _storageService;
  bool _isLoading = true;
  String? _errorMessage;
  List<RoleAgreement> _roles = [];
  String? _projectId;
  String? _projectName;
  String? _projectCreatedBy;
  String? _currentUserId;
  String? _currentUserEmail;
  String? _currentUserName;
  int _totalMembers = 0;

  // Search and Filter State
  String _selectedCategory = 'All';
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  bool _showSearchBar = false;

  static const List<String> _categories = [
    'All',
    'Architecture',
    'Frontend',
    'Backend',
    'Mobile',
    'DevOps',
    'Testing / QA',
  ];

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _storageService = widget.storageService ?? StorageService();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _resolveProjectInfo();
    _fetchRoles();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _resolveProjectInfo() {
    if (_projectId != null) return;

    if (widget.projectId != null && widget.projectId!.isNotEmpty) {
      _projectId = widget.projectId;
      _projectName = widget.projectName;
      return;
    }

    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is Project) {
      _projectId = args.id;
      _projectName = args.name;
      _projectCreatedBy = args.createdBy;
    } else if (args is String) {
      _projectId = args;
    } else if (args is Map<String, dynamic>) {
      _projectId = args['projectId'] as String? ?? args['id'] as String?;
      _projectName = args['projectName'] as String? ?? args['name'] as String?;
      _projectCreatedBy = args['createdBy'] as String? ?? args['created_by'] as String?;
    }
  }

  Future<void> _fetchRoles() async {
    if (_projectId == null || _projectId!.isEmpty) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Project ID is required to fetch team roles.';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final userId = await _storageService.getUserId();
      final userEmail = await _storageService.getUserEmail();
      final userName = await _storageService.getUserName();
      final rawRoles = await _projectService.listProjectRoles(_projectId!);
      final parsedRoles =
          rawRoles.map((item) => RoleAgreement.fromJson(item)).toList();

      int memberCount = parsedRoles.length;
      if (rawRoles.isNotEmpty && rawRoles[0]['total_members'] != null) {
        memberCount = rawRoles[0]['total_members'] as int;
      }
      if (memberCount < parsedRoles.length) {
        memberCount = parsedRoles.length;
      }

      if (mounted) {
        setState(() {
          _currentUserId = userId;
          _currentUserEmail = userEmail;
          _currentUserName = userName;
          _roles = parsedRoles;
          _totalMembers = memberCount;
          if (_projectCreatedBy == null || _projectCreatedBy!.isEmpty) {
            for (final r in parsedRoles) {
              if (r.projectCreatedBy != null && r.projectCreatedBy!.isNotEmpty) {
                _projectCreatedBy = r.projectCreatedBy;
                break;
              }
            }
          }
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

  bool _isUserRole(RoleAgreement agreement) {
    if (_currentUserId != null &&
        _currentUserId!.isNotEmpty &&
        agreement.userId == _currentUserId) {
      return true;
    }
    final profileEmail = agreement.profile?['email']?.toString().toLowerCase();
    if (_currentUserEmail != null &&
        _currentUserEmail!.isNotEmpty &&
        profileEmail == _currentUserEmail!.toLowerCase()) {
      return true;
    }
    return false;
  }

  RoleAgreement? get _myRole {
    for (final role in _roles) {
      if (_isUserRole(role) && role.isDeclared) return role;
    }
    return null;
  }


  bool get _isLead {
    if (_currentUserId != null &&
        _projectCreatedBy != null &&
        _currentUserId == _projectCreatedBy) {
      return true;
    }
    final myR = _myRole;
    return myR?.isLead ?? false;
  }

  List<RoleAgreement> get _filteredRoles {
    return _roles.where((role) {
      // 1. Category Filter
      final roleText = role.declaredRole.toLowerCase();
      final respText = (role.responsibilities ?? '').toLowerCase();
      final matchesCategory = switch (_selectedCategory) {
        'All' => true,
        'Frontend' => roleText.contains('front') ||
            roleText.contains('ui') ||
            roleText.contains('react') ||
            roleText.contains('flutter') ||
            respText.contains('ui'),
        'Backend' => roleText.contains('back') ||
            roleText.contains('api') ||
            roleText.contains('fastapi') ||
            roleText.contains('database') ||
            respText.contains('api'),
        'Mobile' => roleText.contains('mobile') ||
            roleText.contains('flutter') ||
            roleText.contains('android') ||
            roleText.contains('ios') ||
            respText.contains('mobile'),
        'Architecture' => roleText.contains('arch') ||
            roleText.contains('lead') ||
            roleText.contains('system') ||
            respText.contains('architecture'),
        'Testing / QA' => roleText.contains('test') ||
            roleText.contains('qa') ||
            roleText.contains('quality') ||
            respText.contains('test'),
        'DevOps' => roleText.contains('devops') ||
            roleText.contains('infra') ||
            roleText.contains('cloud') ||
            roleText.contains('ci'),
        _ => true,
      };

      if (!matchesCategory) return false;

      // 2. Search Query Filter
      if (_searchQuery.trim().isEmpty) return true;
      final q = _searchQuery.toLowerCase().trim();
      final name = role.displayName.toLowerCase();
      final email = (role.email ?? '').toLowerCase();
      final title = role.declaredRole.toLowerCase();
      final resp = (role.responsibilities ?? '').toLowerCase();

      return name.contains(q) ||
          email.contains(q) ||
          title.contains(q) ||
          resp.contains(q);
    }).toList();
  }

  Future<void> _navigateToDeclareRole() async {
    if (_projectId == null) return;

    final result = await Navigator.pushNamed(
      context,
      DeclareRoleScreen.routeName,
      arguments: Project(
        id: _projectId!,
        name: _projectName ?? 'Project',
      ),
    );

    if (result != null && mounted) {
      _fetchRoles();
    }
  }

  Future<void> _navigateToEditRole(RoleAgreement myRole) async {
    if (_projectId == null) return;

    final result = await Navigator.pushNamed(
      context,
      DeclareRoleScreen.routeName,
      arguments: {
        'projectId': _projectId,
        'initialRole': myRole.declaredRole,
        'initialResponsibilities': myRole.responsibilities,
        'initialDeadline': myRole.deadline,
      },
    );

    if (result != null && mounted) {
      _fetchRoles();
    }
  }

  Future<void> _confirmRemoveMember(RoleAgreement agreement) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: const Row(
          children: [
            Icon(Icons.person_remove_outlined, color: Colors.red, size: 24),
            SizedBox(width: 8),
            Text('Remove Member?'),
          ],
        ),
        content: Text(
          'Are you sure you want to remove "${agreement.displayName}" from the project team? Their declared role will be deleted.',
          style: const TextStyle(fontSize: 14, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red.shade700,
              foregroundColor: Colors.white,
            ),
            child: const Text('Yes, Remove'),
          ),
        ],
      ),
    );

    if (confirm == true && _projectId != null) {
      try {
        await _projectService.removeMember(_projectId!, agreement.userId);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('${agreement.displayName} removed from team.'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
          _fetchRoles();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to remove member: $e'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      }
    }
  }

  void _copyReminderMessage() {
    final reminderText =
        '🚀 BuildCrew Reminder: Please declare your project role and milestone deadlines for project "${_projectName ?? 'BuildCrew'}" on the BuildCrew app!';
    Clipboard.setData(ClipboardData(text: reminderText));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Copied reminder to clipboard! Share it with your team.'),
        backgroundColor: Colors.blueAccent,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }


  Widget _buildRoleCard(RoleAgreement agreement) {
    final isMe = _isUserRole(agreement);
    final isLead = (agreement.userId == _projectCreatedBy) || agreement.isLead;
    final displayedName = isMe &&
            (_currentUserName != null && _currentUserName!.trim().isNotEmpty)
        ? _currentUserName!.trim()
        : agreement.displayName;
    final displayedEmail =
        (agreement.email != null && agreement.email!.trim().isNotEmpty)
            ? agreement.email!.trim()
            : (isMe &&
                    (_currentUserEmail != null &&
                        _currentUserEmail!.trim().isNotEmpty)
                ? _currentUserEmail!.trim()
                : null);
    final displayedInitial = displayedName.isNotEmpty
        ? displayedName[0].toUpperCase()
        : agreement.avatarInitial;

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isMe ? Colors.blueAccent.shade200 : Colors.grey.shade200,
          width: isMe ? 1.5 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: isMe
                ? Colors.blue.withValues(alpha: 0.08)
                : Colors.black.withValues(alpha: 0.03),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(18.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Member info header with avatar, name, badges, and role badge
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: isLead
                      ? Colors.amber.shade100
                      : (isMe
                          ? Colors.blueAccent
                          : Colors.blueAccent.shade100.withValues(alpha: 0.3)),
                  child: Text(
                    displayedInitial,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: isLead
                          ? Colors.amber.shade900
                          : (isMe ? Colors.white : Colors.blueAccent),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(
                              displayedName,
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: Colors.black87,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (isLead) ...[
                            const SizedBox(width: 6),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.amber.shade50,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: Colors.amber.shade300),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(Icons.stars_rounded,
                                      size: 12, color: Colors.amber.shade800),
                                  const SizedBox(width: 3),
                                  Text(
                                    'Team Lead',
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.bold,
                                      color: Colors.amber.shade900,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                          if (isMe) ...[
                            const SizedBox(width: 6),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 6,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.green.shade50,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: Colors.green.shade300),
                              ),
                              child: Text(
                                'YOU',
                                style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.green.shade800,
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                      if (displayedEmail != null &&
                          displayedEmail.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          displayedEmail,
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.grey.shade500,
                            fontWeight: FontWeight.w400,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                      const SizedBox(height: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 3,
                        ),
                        decoration: BoxDecoration(
                          color: agreement.isDeclared
                              ? Colors.blue.shade50
                              : Colors.amber.shade50,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: agreement.isDeclared
                                ? Colors.blue.shade200
                                : Colors.amber.shade300,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (!agreement.isDeclared) ...[
                              Icon(
                                Icons.hourglass_top_rounded,
                                size: 12,
                                color: Colors.amber.shade900,
                              ),
                              const SizedBox(width: 4),
                            ],
                            Text(
                              agreement.isDeclared
                                  ? agreement.declaredRole
                                  : 'Pending Role Declaration',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: agreement.isDeclared
                                    ? Colors.blue.shade800
                                    : Colors.amber.shade900,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                if (isMe && agreement.isDeclared)
                  IconButton(
                    onPressed: () => _navigateToEditRole(agreement),
                    icon: const Icon(Icons.edit_outlined,
                        color: Colors.blueAccent, size: 20),
                    tooltip: 'Edit your declared role',
                  )
                else if (_isLead && agreement.userId != _projectCreatedBy)
                  IconButton(
                    onPressed: () => _confirmRemoveMember(agreement),
                    icon: Icon(Icons.person_remove_outlined,
                        color: Colors.red.shade400, size: 20),
                    tooltip: 'Remove teammate from project',
                  ),

              ],
            ),
            const SizedBox(height: 14),

            // Responsibilities & Details (If Declared)
            if (agreement.isDeclared) ...[
              if (agreement.responsibilities != null &&
                  agreement.responsibilities!.trim().isNotEmpty) ...[
                const Text(
                  'Responsibilities',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: Colors.grey,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 6),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade50,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: Colors.grey.shade200),
                  ),
                  child: Text(
                    agreement.responsibilities!.trim(),
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.grey.shade800,
                      height: 1.4,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
              ],

              // Target Deadline & Timestamp footer
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  if (agreement.formattedDeadline != null)
                    Row(
                      children: [
                        const Icon(
                          Icons.event_available_rounded,
                          size: 16,
                          color: Colors.deepPurpleAccent,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          'Target: ${agreement.formattedDeadline}',
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: Colors.deepPurpleAccent,
                          ),
                        ),
                      ],
                    )
                  else
                    const SizedBox.shrink(),
                  if (agreement.updatedAt != null || agreement.createdAt != null)
                    Text(
                      'Updated ${_formatDate(agreement.updatedAt ?? agreement.createdAt)}',
                      style: TextStyle(
                        fontSize: 11,
                        color: Colors.grey.shade500,
                      ),
                    ),
                ],
              ),
            ] else ...[
              // Undeclared State UI
              if (isMe)
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _navigateToDeclareRole,
                    icon: const Icon(Icons.add_task_rounded, size: 16),
                    label: const Text('Declare Your Role & Milestone Target'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blueAccent,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                  ),
                )
              else
                Container(
                  width: double.infinity,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.amber.shade50.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: Colors.amber.shade200),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline_rounded,
                          size: 16, color: Colors.amber.shade800),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Awaiting role & milestone deadline declaration.',
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.amber.shade900,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],

          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime? date) {
    if (date == null) return '';
    return '${date.month}/${date.day}/${date.year}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(

      backgroundColor: Colors.grey.shade50,
      appBar: AppBar(
        title: Text(
          _projectName != null ? '$_projectName Roles' : 'Team Roles',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
        actions: [
          IconButton(
            icon: Icon(_showSearchBar ? Icons.close : Icons.search_rounded,
                color: Colors.blueAccent),
            tooltip: _showSearchBar ? 'Close Search' : 'Search Roles',
            onPressed: () {
              setState(() {
                _showSearchBar = !_showSearchBar;
                if (!_showSearchBar) {
                  _searchQuery = '';
                  _searchController.clear();
                }
              });
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: Colors.blueAccent),
            tooltip: 'Refresh Roles',
            onPressed: _fetchRoles,
          ),
        ],
      ),
      body: SafeArea(

        child: RefreshIndicator(
          onRefresh: _fetchRoles,
          color: Colors.blueAccent,
          child: _buildBody(),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(),
      );
    }

    if (_errorMessage != null) {
      return ListView(
        padding: const EdgeInsets.all(24.0),
        children: [
          const SizedBox(height: 40),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.red.shade50,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: Colors.red.shade200),
            ),
            child: Column(
              children: [
                Icon(Icons.error_outline_rounded,
                    color: Colors.red.shade700, size: 36),
                const SizedBox(height: 10),
                Text(
                  'Failed to load team roles',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Colors.red.shade900,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  _errorMessage!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13,
                    color: Colors.red.shade800,
                  ),
                ),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: _fetchRoles,
                  icon: const Icon(Icons.refresh, size: 18),
                  label: const Text('Try Again'),
                  style: ElevatedButton.styleFrom(

                    backgroundColor: Colors.red.shade700,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      );
    }

    if (_roles.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(24.0),
        children: [
          const SizedBox(height: 60),
          Center(
            child: Container(
              width: 90,
              height: 90,
              decoration: BoxDecoration(
                color: Colors.blue.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.assignment_ind_outlined,
                size: 48,
                color: Colors.blueAccent,
              ),
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'No Roles Declared Yet',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: Colors.black87,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Be the first to declare your role, responsibilities, and target milestones for this project!',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 14,
              color: Colors.grey.shade600,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 28),
          Center(
            child: ElevatedButton.icon(
              onPressed: _navigateToDeclareRole,
              icon: const Icon(Icons.add_circle_outline_rounded, size: 20),
              label: const Text(
                'Declare Your Role',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.blueAccent,
                foregroundColor: Colors.white,
                padding:
                    const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                elevation: 2,
              ),
            ),
          ),
        ],
      );
    }

    final myRole = _myRole;
    final filteredRoles = _filteredRoles;
    final totalCount = _totalMembers > 0 ? _totalMembers : _roles.length;
    final declaredCount = _roles.where((r) => r.isDeclared).length;


    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 80),
      itemCount: filteredRoles.length + 3,
      itemBuilder: (context, index) {
        if (index == 0) {
          // Header summary banner with declared vs total members
          return Container(
            margin: const EdgeInsets.only(bottom: 14),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.blueAccent.shade700,
                  Colors.blueAccent.shade400,
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.blueAccent.withValues(alpha: 0.25),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(
                      Icons.groups_3_rounded,
                      color: Colors.white,
                      size: 32,
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '$declaredCount of $totalCount Members Declared',
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            myRole != null
                                ? 'Your declared role: ${myRole.declaredRole}'
                                : 'Declare your role below to align with your crew.',
                            style: const TextStyle(
                              fontSize: 12,
                              color: Colors.white70,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (myRole != null)
                      TextButton.icon(
                        onPressed: () => _navigateToEditRole(myRole),
                        icon: const Icon(Icons.edit_note_rounded,
                            color: Colors.white, size: 18),
                        label: const Text(
                          'Edit',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 13,
                          ),
                        ),
                        style: TextButton.styleFrom(
                          backgroundColor:
                              Colors.white.withValues(alpha: 0.2),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 6),
                        ),
                      ),
                  ],
                ),
                if (_isLead && declaredCount < totalCount) ...[
                  const SizedBox(height: 12),
                  InkWell(
                    onTap: _copyReminderMessage,
                    borderRadius: BorderRadius.circular(8),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                            color: Colors.white.withValues(alpha: 0.3)),
                      ),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.campaign_outlined,
                              color: Colors.white, size: 16),
                          SizedBox(width: 6),
                          Text(
                            'Remind Teammates to Declare Roles',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          );
        }

        if (index == 1) {
          // Search Bar (expandable)
          if (!_showSearchBar) return const SizedBox.shrink();
          return Container(
            margin: const EdgeInsets.only(bottom: 12),
            child: TextField(
              controller: _searchController,
              autofocus: true,
              decoration: InputDecoration(
                hintText: 'Search by name, email, or role...',
                prefixIcon:
                    const Icon(Icons.search, color: Colors.blueAccent, size: 20),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () {
                          setState(() {
                            _searchQuery = '';
                            _searchController.clear();
                          });
                        },
                      )
                    : null,
                filled: true,
                fillColor: Colors.white,
                contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 12),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: Colors.grey.shade300),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: Colors.grey.shade300),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Colors.blueAccent),
                ),
              ),
              onChanged: (val) {
                setState(() {
                  _searchQuery = val;
                });
              },
            ),
          );
        }

        if (index == 2) {
          // Category Filter Chips
          return Container(
            height: 38,
            margin: const EdgeInsets.only(bottom: 16),
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: _categories.length,
              separatorBuilder: (context, _) => const SizedBox(width: 8),
              itemBuilder: (context, catIdx) {
                final cat = _categories[catIdx];
                final isSelected = _selectedCategory == cat;
                return ChoiceChip(
                  label: Text(cat),
                  selected: isSelected,
                  selectedColor: Colors.blueAccent,
                  labelStyle: TextStyle(
                    color: isSelected ? Colors.white : Colors.grey.shade800,
                    fontSize: 12,
                    fontWeight:
                        isSelected ? FontWeight.bold : FontWeight.normal,
                  ),
                  backgroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20),
                    side: BorderSide(
                      color: isSelected
                          ? Colors.blueAccent
                          : Colors.grey.shade300,
                    ),
                  ),
                  showCheckmark: false,
                  onSelected: (selected) {
                    if (selected) {
                      setState(() {
                        _selectedCategory = cat;
                      });
                    }
                  },
                );
              },
            ),
          );
        }

        if (filteredRoles.isEmpty) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 40.0),
            child: Center(
              child: Column(
                children: [
                  Icon(Icons.filter_list_off_rounded,
                      size: 40, color: Colors.grey.shade400),
                  const SizedBox(height: 10),
                  Text(
                    'No roles found for "$_selectedCategory"',
                    style: TextStyle(
                      fontSize: 15,
                      color: Colors.grey.shade600,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          );
        }

        final agreement = filteredRoles[index - 3];
        return _buildRoleCard(agreement);
      },
    );
  }
}
