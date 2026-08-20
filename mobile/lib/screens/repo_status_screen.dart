import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/github_service.dart';
import 'connect_repository_screen.dart';

class RepoStatusScreen extends StatefulWidget {
  static const String routeName = '/repo-status';

  final String? projectId;
  final String? projectName;
  final bool isOwner;
  final GitHubService? gitHubService;

  const RepoStatusScreen({
    super.key,
    this.projectId,
    this.projectName,
    this.isOwner = true,
    this.gitHubService,
  });

  @override
  State<RepoStatusScreen> createState() => _RepoStatusScreenState();
}

class _RepoStatusScreenState extends State<RepoStatusScreen> {
  late final GitHubService _gitHubService;
  bool _isLoading = true;
  String? _errorMessage;
  bool _isConnected = false;
  Map<String, dynamic>? _installationData;
  bool _isUnlinking = false;

  @override
  void initState() {
    super.initState();
    _gitHubService = widget.gitHubService ?? GitHubService();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadInstallationStatus();
    });
  }

  String _getEffectiveProjectId() {
    if (widget.projectId != null && widget.projectId!.isNotEmpty) {
      return widget.projectId!;
    }
    final routeArgs =
        ModalRoute.of(context)?.settings.arguments as Map<String, dynamic>?;
    return routeArgs?['projectId'] as String? ?? '';
  }

  String _getEffectiveProjectName() {
    if (widget.projectName != null && widget.projectName!.isNotEmpty) {
      return widget.projectName!;
    }
    final routeArgs =
        ModalRoute.of(context)?.settings.arguments as Map<String, dynamic>?;
    return routeArgs?['projectName'] as String? ?? 'Project';
  }

  bool _getEffectiveIsOwner() {
    final routeArgs =
        ModalRoute.of(context)?.settings.arguments as Map<String, dynamic>?;
    if (routeArgs != null && routeArgs.containsKey('isOwner')) {
      return routeArgs['isOwner'] as bool? ?? false;
    }
    return widget.isOwner;
  }

  Future<void> _loadInstallationStatus() async {
    final projectId = _getEffectiveProjectId();
    if (projectId.isEmpty) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Project ID is missing.';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final data = await _gitHubService.getInstallation(projectId);
      if (mounted) {
        final connected = data['connected'] == true;
        final rawInst = data['installation'];
        final instMap = rawInst is Map ? Map<String, dynamic>.from(rawInst) : null;

        setState(() {
          _isConnected = connected;
          _installationData = instMap;
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

  Future<void> _openRepoOnGitHub(String repoFullName) async {
    final url = 'https://github.com/$repoFullName';
    final uri = Uri.parse(url);
    try {
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Could not open GitHub URL: $e'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    }
  }

  Future<void> _confirmAndUnlink(String projectId) async {
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
            Icon(Icons.link_off_rounded, color: Colors.redAccent, size: 24),
            SizedBox(width: 10),
            Text(
              'Disconnect Repository?',
              style: TextStyle(color: Colors.white, fontSize: 18),
            ),
          ],
        ),
        content: const Text(
          'Disconnecting will unlink commit tracking, pull request reviews, and issue sync for this project. You can reconnect at any time.',
          style: TextStyle(color: Color(0xFF94A3B8), fontSize: 14, height: 1.4),
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
            ),
            child: const Text('Yes, Disconnect'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      setState(() {
        _isUnlinking = true;
      });

      try {
        final success = await _gitHubService.unlinkInstallation(projectId);
        if (success && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('GitHub repository successfully disconnected.'),
              backgroundColor: Color(0xFF2563EB),
              behavior: SnackBarBehavior.floating,
            ),
          );
          _loadInstallationStatus();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to disconnect repository: $e'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      } finally {
        if (mounted) {
          setState(() {
            _isUnlinking = false;
          });
        }
      }
    }
  }

  Future<void> _showRepositorySelectorDialog(String projectId) async {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF151C2C),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return FutureBuilder<Map<String, dynamic>>(
          future: _gitHubService.getInstallationRepositories(projectId),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 40),
                child: Center(
                  child: CircularProgressIndicator(color: Color(0xFF2563EB)),
                ),
              );
            }

            if (snapshot.hasError || !snapshot.hasData) {
              return Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline_rounded, color: Colors.redAccent, size: 36),
                    const SizedBox(height: 12),
                    Text(
                      'Failed to fetch repositories: ${snapshot.error ?? "No data"}',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 13),
                    ),
                  ],
                ),
              );
            }

            final data = snapshot.data!;
            final currentRepo = data['current_repo'] as String? ?? '';
            final rawRepos = data['repositories'] as List<dynamic>? ?? [];
            final repos = rawRepos.map((r) => Map<String, dynamic>.from(r as Map)).toList();

            if (repos.isEmpty) {
              return const Padding(
                padding: EdgeInsets.all(24.0),
                child: Text(
                  'No repositories found under this installation.',
                  style: TextStyle(color: Colors.white70),
                ),
              );
            }

            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF2563EB).withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.swap_horiz_rounded, color: Color(0xFF60A5FA), size: 20),
                      ),
                      const SizedBox(width: 12),
                      const Text(
                        'Select Repository',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Choose which repository to link to this project from your GitHub App installation:',
                    style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                  ),
                  const SizedBox(height: 16),
                  Flexible(
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemCount: repos.length,
                      separatorBuilder: (context, index) => const SizedBox(height: 8),
                      itemBuilder: (context, index) {
                        final r = repos[index];
                        final fullRepoName = r['full_name'] as String? ?? '';
                        final isSelected = fullRepoName == currentRepo;

                        return Container(
                          decoration: BoxDecoration(
                            color: isSelected
                                ? const Color(0xFF2563EB).withValues(alpha: 0.15)
                                : const Color(0xFF0B0F19),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: isSelected
                                  ? const Color(0xFF2563EB)
                                  : const Color(0xFF1E293B),
                              width: isSelected ? 1.5 : 1,
                            ),
                          ),
                          child: ListTile(
                            leading: Icon(
                              Icons.code_rounded,
                              color: isSelected ? const Color(0xFF60A5FA) : const Color(0xFF94A3B8),
                            ),
                            title: Text(
                              fullRepoName,
                              style: TextStyle(
                                color: isSelected ? Colors.white : const Color(0xFFE2E8F0),
                                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                                fontSize: 14,
                              ),
                            ),
                            trailing: isSelected
                                ? const Icon(Icons.check_circle_rounded, color: Color(0xFF10B981))
                                : null,
                            onTap: () async {
                              Navigator.pop(ctx);
                              await _switchRepository(projectId, fullRepoName);
                            },
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _switchRepository(String projectId, String newRepoFullName) async {
    setState(() {
      _isLoading = true;
    });

    try {
      await _gitHubService.selectRepository(projectId, newRepoFullName);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Switched to "$newRepoFullName" successfully!'),
            backgroundColor: const Color(0xFF10B981),
            behavior: SnackBarBehavior.floating,
          ),
        );
        _loadInstallationStatus();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Failed to switch repository: $e';
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final projectName = _getEffectiveProjectName();
    final projectId = _getEffectiveProjectId();
    final isOwner = _getEffectiveIsOwner();

    return Scaffold(
      backgroundColor: const Color(0xFF0B0F19),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded,
              color: Colors.white, size: 20),
          onPressed: () => Navigator.pop(context, true),
        ),
        title: const Text(
          'GitHub Integration',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: Colors.white),
            tooltip: 'Refresh Status',
            onPressed: _isLoading ? null : _loadInstallationStatus,
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          color: const Color(0xFF2563EB),
          backgroundColor: const Color(0xFF151C2C),
          onRefresh: _loadInstallationStatus,
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
            child: _buildBodyContent(projectId, projectName, isOwner),
          ),
        ),
      ),
    );
  }

  Widget _buildBodyContent(
      String projectId, String projectName, bool isOwner) {
    if (_isLoading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: 80),
          child: Column(
            children: [
              CircularProgressIndicator(
                color: Color(0xFF2563EB),
                strokeWidth: 3,
              ),
              SizedBox(height: 20),
              Text(
                'Checking repository link...',
                style: TextStyle(color: Color(0xFF94A3B8), fontSize: 14),
              ),
            ],
          ),
        ),
      );
    }

    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 40),
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.red.shade900.withValues(alpha: 0.2),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.error_outline_rounded,
                    color: Colors.redAccent, size: 40),
              ),
              const SizedBox(height: 16),
              const Text(
                'Could not load repository status',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _errorMessage!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
              ),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: _loadInstallationStatus,
                icon: const Icon(Icons.refresh_rounded, size: 18),
                label: const Text('Try Again'),
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
      );
    }

    if (!_isConnected || _installationData == null) {
      return _buildUnconnectedState(projectId, projectName);
    }

    return _buildConnectedState(projectId, projectName, isOwner);
  }

  Widget _buildUnconnectedState(String projectId, String projectName) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 20),
        Center(
          child: Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              color: const Color(0xFF151C2C),
              shape: BoxShape.circle,
              border: Border.all(color: const Color(0xFF1E293B), width: 2),
            ),
            child: const Center(
              child: Icon(
                Icons.link_off_rounded,
                size: 38,
                color: Color(0xFF64748B),
              ),
            ),
          ),
        ),
        const SizedBox(height: 20),
        const Text(
          'No Repository Connected',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Connect a GitHub repository to track commits, review pull requests, and view issues directly inside "$projectName".',
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: Color(0xFF94A3B8),
            fontSize: 14,
            height: 1.45,
          ),
        ),
        const SizedBox(height: 32),
        ElevatedButton.icon(
          onPressed: () async {
            final result = await Navigator.pushNamed(
              context,
              ConnectRepositoryScreen.routeName,
              arguments: {
                'projectId': projectId,
                'projectName': projectName,
              },
            );
            if (result == true || mounted) {
              _loadInstallationStatus();
            }
          },
          icon: const Icon(Icons.link_rounded, color: Colors.white, size: 20),
          label: const Text(
            'Connect with GitHub',
            style: TextStyle(
              color: Colors.white,
              fontSize: 15,
              fontWeight: FontWeight.bold,
            ),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF2563EB),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 16),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            elevation: 4,
          ),
        ),
      ],
    );
  }

  Widget _buildConnectedState(
      String projectId, String projectName, bool isOwner) {
    final repoFullName =
        _installationData?['repo_full_name'] as String? ?? 'Repository';
    final installationId =
        _installationData?['installation_id']?.toString() ?? 'N/A';
    final connectedAt =
        _installationData?['connected_at'] as String? ?? 'Recently';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Status Badge Header
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF10B981).withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                  color: const Color(0xFF10B981).withValues(alpha: 0.4),
                ),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.check_circle_rounded,
                      color: Color(0xFF10B981), size: 14),
                  SizedBox(width: 6),
                  Text(
                    'Connected & Active',
                    style: TextStyle(
                      color: Color(0xFF10B981),
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
            Text(
              projectName,
              style: const TextStyle(
                color: Color(0xFF94A3B8),
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),

        const SizedBox(height: 16),

        // Repository Hero Card
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF151C2C), Color(0xFF1E293B)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: const Color(0xFF2563EB).withValues(alpha: 0.3),
              width: 1.5,
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF2563EB).withValues(alpha: 0.15),
                blurRadius: 16,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: const Color(0xFF0B0F19),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: const Color(0xFF334155)),
                    ),
                    child: const Icon(
                      Icons.code_rounded,
                      color: Colors.white,
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'GITHUB REPOSITORY',
                          style: TextStyle(
                            color: Color(0xFF60A5FA),
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 1.1,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          repoFullName,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              InkWell(
                onTap: () => _openRepoOnGitHub(repoFullName),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'View on GitHub ($repoFullName)',
                        style: const TextStyle(
                          color: Color(0xFF60A5FA),
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Icon(
                        Icons.open_in_new_rounded,
                        color: Color(0xFF60A5FA),
                        size: 14,
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 20),

        // Installation Details Card
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: const Color(0xFF151C2C),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFF1E293B)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Integration Details',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 14),
              _buildDetailRow(
                icon: Icons.tag_rounded,
                label: 'Installation ID',
                value: '#$installationId',
              ),
              const Divider(color: Color(0xFF1E293B), height: 20),
              _buildDetailRow(
                icon: Icons.calendar_today_rounded,
                label: 'Connected Since',
                value: connectedAt.contains('T')
                    ? connectedAt.split('T')[0]
                    : connectedAt,
              ),
              const Divider(color: Color(0xFF1E293B), height: 20),
              _buildDetailRow(
                icon: Icons.security_rounded,
                label: 'Access Level',
                value: 'Read-Only (Secure RS256)',
              ),
              const Divider(color: Color(0xFF1E293B), height: 20),
              _buildDetailRow(
                icon: Icons.sync_rounded,
                label: 'Sync Status',
                value: 'Live Webhooks Active',
              ),
            ],
          ),
        ),

        const SizedBox(height: 24),

        // Team Lead Repository Actions
        if (isOwner) ...[
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _isLoading ? null : () => _showRepositorySelectorDialog(projectId),
              icon: const Icon(Icons.swap_horiz_rounded, color: Colors.white, size: 20),
              label: const Text(
                'Switch / Change Repository',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF2563EB),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                elevation: 2,
              ),
            ),
          ),
          const SizedBox(height: 12),

          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _isUnlinking ? null : () => _confirmAndUnlink(projectId),
              icon: _isUnlinking
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.redAccent,
                      ),
                    )
                  : const Icon(Icons.link_off_rounded,
                      color: Colors.redAccent, size: 18),
              label: const Text(
                'Disconnect Repository',
                style: TextStyle(
                  color: Colors.redAccent,
                  fontWeight: FontWeight.w600,
                ),
              ),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
                side: BorderSide(
                  color: Colors.redAccent.withValues(alpha: 0.5),
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Only Team Leads can unlink connected repositories.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF64748B), fontSize: 12),
          ),
        ],
      ],
    );
  }

  Widget _buildDetailRow({
    required IconData icon,
    required String label,
    required String value,
  }) {
    return Row(
      children: [
        Icon(icon, color: const Color(0xFF64748B), size: 18),
        const SizedBox(width: 10),
        Text(
          label,
          style: const TextStyle(
            color: Color(0xFF94A3B8),
            fontSize: 13,
          ),
        ),
        const Spacer(),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}
