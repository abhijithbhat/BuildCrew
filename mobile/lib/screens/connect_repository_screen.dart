import 'package:flutter/material.dart';
import '../services/github_service.dart';

class ConnectRepositoryScreen extends StatefulWidget {
  static const String routeName = '/connect-repository';

  final String? projectId;
  final String? projectName;
  final GitHubService? gitHubService;

  const ConnectRepositoryScreen({
    super.key,
    this.projectId,
    this.projectName,
    this.gitHubService,
  });

  @override
  State<ConnectRepositoryScreen> createState() =>
      _ConnectRepositoryScreenState();
}

class _ConnectRepositoryScreenState extends State<ConnectRepositoryScreen>
    with WidgetsBindingObserver {
  late final GitHubService _gitHubService;
  bool _isLoading = false;
  String? _errorMessage;
  final TextEditingController _repoNameController = TextEditingController();
  final TextEditingController _instIdController = TextEditingController();


  List<Map<String, dynamic>> _availableRepos = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _gitHubService = widget.gitHubService ?? GitHubService();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final projectId = _getEffectiveProjectId();
      if (projectId.isNotEmpty) {
        _fetchAvailableRepos(projectId);
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _repoNameController.dispose();
    _instIdController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      final projectId = _getEffectiveProjectId();
      if (projectId.isNotEmpty) {
        _checkIfAlreadyConnected(projectId, silent: true);
        _fetchAvailableRepos(projectId);
      }
    }
  }

  Future<void> _fetchAvailableRepos(String projectId) async {
    if (projectId.isEmpty) return;
    try {
      final res = await _gitHubService.getInstallationRepositories(projectId);
      final rawList = res['repositories'] as List<dynamic>? ?? [];
      if (mounted) {
        setState(() {
          _availableRepos = rawList.map((e) => Map<String, dynamic>.from(e as Map)).toList();
        });
      }
    } catch (_) {}
  }

  Future<void> _selectRepoDirectly(String projectId, String repoFullName) async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      await _gitHubService.selectRepository(projectId, repoFullName);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle_rounded, color: Colors.white, size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Text('Linked "$repoFullName" to project!'),
                ),
              ],
            ),
            backgroundColor: const Color(0xFF10B981),
            behavior: SnackBarBehavior.floating,
          ),
        );
        Navigator.pop(context, true);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Failed to connect repository: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  String _getEffectiveProjectId() {
    if (widget.projectId != null && widget.projectId!.isNotEmpty) {
      return widget.projectId!;
    }
    final routeArgs =
        ModalRoute.of(context)?.settings.arguments as Map<String, dynamic>?;
    return routeArgs?['projectId'] as String? ?? '';
  }

  Future<void> _checkIfAlreadyConnected(String projectId, {bool silent = false}) async {
    if (projectId.isEmpty) return;

    if (!silent) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
    }

    try {
      final data = await _gitHubService.getInstallation(projectId);
      if (data['connected'] == true && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Row(
              children: [
                Icon(Icons.check_circle_rounded, color: Colors.white, size: 20),
                SizedBox(width: 10),
                Expanded(
                  child: Text('GitHub repository successfully connected!'),
                ),
              ],
            ),
            backgroundColor: Color(0xFF10B981),
            behavior: SnackBarBehavior.floating,
          ),
        );
        Navigator.pop(context, true);
      } else if (!silent && mounted) {
        setState(() {
          _errorMessage =
              'No active installation detected yet. Please ensure you clicked "Save" or "Install & Authorize" on GitHub, or use the direct link option below.';
        });
      }
    } catch (e) {
      if (!silent && mounted) {
        setState(() {
          _errorMessage = e.toString();
        });
      }
    } finally {
      if (mounted && !silent) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _linkDirectly(String projectId) async {
    final repoName = _repoNameController.text.trim();
    final instId = _instIdController.text.trim();

    if (repoName.isEmpty) {
      setState(() {
        _errorMessage = 'Please enter a Repository Name (e.g. your-username/your-repo).';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      await _gitHubService.linkInstallation(
        projectId,
        instId.isNotEmpty ? instId : 'auto',
        repoFullName: repoName,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Linked "$repoName" successfully!'),
            backgroundColor: const Color(0xFF10B981),
            behavior: SnackBarBehavior.floating,
          ),
        );
        Navigator.pop(context, true);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Failed to link repository: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _onConnectPressed(String projectId) async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final launched = await _gitHubService.launchInstallFlow(projectId);
      if (!launched && mounted) {
        setState(() {
          _errorMessage =
              'Could not open browser for GitHub authorization. Please try again.';
        });
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Row(
              children: [
                Icon(Icons.open_in_browser_rounded,
                    color: Colors.white, size: 20),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                      'Opening GitHub in browser... Click "Save" or "Install" on GitHub and return here.'),
                ),
              ],
            ),
            backgroundColor: const Color(0xFF2563EB),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString();
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }




  @override
  Widget build(BuildContext context) {
    final routeArgs =
        ModalRoute.of(context)?.settings.arguments as Map<String, dynamic>?;
    final effectiveProjectName = widget.projectName ??
        routeArgs?['projectName'] as String? ??
        'Your Project';
    final effectiveProjectId = widget.projectId ??
        routeArgs?['projectId'] as String? ??
        '';

    return Scaffold(
      backgroundColor: const Color(0xFF0B0F19),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded,
              color: Colors.white, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Connect Repository',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 20.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 12),

              // Header GitHub Icon & Badge
              Center(
                child: Container(
                  width: 90,
                  height: 90,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF2563EB), Color(0xFF7C3AED)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF7C3AED).withValues(alpha: 0.35),
                        blurRadius: 24,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: const Center(
                    child: Icon(
                      Icons.code_rounded,
                      size: 46,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 24),

              // Title & Subtitle
              Text(
                'Link GitHub to\n$effectiveProjectName',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  height: 1.25,
                  letterSpacing: -0.5,
                ),
              ),

              const SizedBox(height: 10),

              Text(
                'Connect your repository to seamlessly track commits, review pull requests, and log member contributions.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.grey.shade400,
                  fontSize: 14,
                  height: 1.5,
                ),
              ),

              const SizedBox(height: 24),

              // Available / Detected GitHub Repositories (1-Tap Direct Connect)
              _buildAvailableRepositoriesSection(effectiveProjectId),

              const SizedBox(height: 8),

              // Feature Highlights Card
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: const Color(0xFF151C2C),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: const Color(0xFF1E293B),
                    width: 1.2,
                  ),
                ),
                child: Column(
                  children: [
                    _buildFeatureRow(
                      icon: Icons.history_rounded,
                      iconColor: const Color(0xFF60A5FA),
                      title: 'Live Commit Sync',
                      subtitle:
                          'Track team branch pushes and commit logs in real-time.',
                    ),
                    const Divider(
                      color: Color(0xFF1E293B),
                      height: 28,
                      thickness: 1,
                    ),
                    _buildFeatureRow(
                      icon: Icons.alt_route_rounded,
                      iconColor: const Color(0xFFA78BFA),
                      title: 'Pull Request Activity',
                      subtitle:
                          'Monitor reviews, approvals, and merged feature branches.',
                    ),
                    const Divider(
                      color: Color(0xFF1E293B),
                      height: 28,
                      thickness: 1,
                    ),
                    _buildFeatureRow(
                      icon: Icons.bug_report_outlined,
                      iconColor: const Color(0xFF34D399),
                      title: 'Issue & Milestone Tracking',
                      subtitle:
                          'Stay aligned on bugs, user stories, and tasks.',
                    ),
                    const Divider(
                      color: Color(0xFF1E293B),
                      height: 28,
                      thickness: 1,
                    ),
                    _buildFeatureRow(
                      icon: Icons.lock_outline_rounded,
                      iconColor: const Color(0xFFFBBF24),
                      title: 'Secure & Read-Only Access',
                      subtitle:
                          'Fine-grained GitHub App permissions with RS256 token exchange.',
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 24),

              if (_errorMessage != null) ...[
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.red.shade900.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                        color: Colors.red.shade700.withValues(alpha: 0.5)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline_rounded,
                          color: Colors.redAccent, size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _errorMessage!,
                          style: const TextStyle(
                              color: Colors.redAccent, fontSize: 13),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],

              // Connect Button
              SizedBox(
                height: 56,
                child: ElevatedButton(
                  onPressed:
                      _isLoading ? null : () => _onConnectPressed(effectiveProjectId),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2563EB),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                    elevation: 5,
                    shadowColor: const Color(0xFF2563EB).withValues(alpha: 0.5),
                  ),
                  child: _isLoading
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.5,
                            color: Colors.white,
                          ),
                        )
                      : const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.open_in_browser_rounded,
                                color: Colors.white, size: 20),
                            SizedBox(width: 10),
                            Text(
                              'Open GitHub in Browser',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.2,
                              ),
                            ),
                          ],
                        ),
                ),
              ),

              const SizedBox(height: 12),

              // Verify Connection Button
              SizedBox(
                height: 52,
                child: OutlinedButton.icon(
                  onPressed: _isLoading
                      ? null
                      : () => _checkIfAlreadyConnected(effectiveProjectId),
                  icon: const Icon(Icons.sync_rounded, color: Color(0xFF60A5FA), size: 20),
                  label: const Text(
                    'I\'ve Installed on GitHub → Verify Connection',
                    style: TextStyle(
                      color: Color(0xFF60A5FA),
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: Color(0xFF2563EB)),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 24),

              // Direct Link Card
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
                    const Row(
                      children: [
                        Icon(Icons.bolt_rounded, color: Color(0xFFFBBF24), size: 20),
                        SizedBox(width: 8),
                        Text(
                          'Direct Repository Link',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'If the app is already installed on your GitHub account, link your repository directly:',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 12, height: 1.4),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _repoNameController,
                      style: const TextStyle(color: Colors.white, fontSize: 14),
                      decoration: InputDecoration(
                        labelText: 'Repository (owner/repo)',
                        hintText: 'e.g. your-username/project-repo',
                        hintStyle: const TextStyle(color: Color(0xFFB0BEC5), fontSize: 13),
                        labelStyle: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                        filled: true,
                        fillColor: const Color(0xFF0B0F19),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                          borderSide: const BorderSide(color: Color(0xFF334155)),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                          borderSide: const BorderSide(color: Color(0xFF334155)),
                        ),
                        prefixIcon: const Icon(Icons.code_rounded, color: Color(0xFF64748B), size: 18),
                      ),
                    ),

                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: _isLoading ? null : () => _linkDirectly(effectiveProjectId),
                        icon: const Icon(Icons.link_rounded, size: 18),
                        label: const Text('Link Repository to Project'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF10B981),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // Disclaimer
              Text(
                'Make sure your backend and ngrok tunnel are running during installation.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 12,
                  height: 1.4,
                ),
              ),


              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFeatureRow({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String subtitle,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            color: iconColor.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: iconColor, size: 20),
        ),

        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                subtitle,
                style: TextStyle(
                  color: Colors.grey.shade400,
                  fontSize: 12.5,
                  height: 1.35,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAvailableRepositoriesSection(String projectId) {
    if (_availableRepos.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF151C2C),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFF2563EB).withValues(alpha: 0.4),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF2563EB).withValues(alpha: 0.12),
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
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFF2563EB).withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.auto_awesome_rounded,
                  color: Color(0xFF60A5FA),
                  size: 18,
                ),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Your GitHub Repositories',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Tap to connect directly to this project:',
                      style: TextStyle(
                        color: Color(0xFF94A3B8),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ..._availableRepos.map((r) {
            final fullName = r['full_name'] as String? ?? '';
            return Container(
              margin: const EdgeInsets.only(bottom: 8),
              decoration: BoxDecoration(
                color: const Color(0xFF0B0F19),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFF1E293B)),
              ),
              child: ListTile(
                dense: true,
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                leading: const Icon(
                  Icons.code_rounded,
                  color: Color(0xFF60A5FA),
                  size: 20,
                ),
                title: Text(
                  fullName,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
                trailing: ElevatedButton(
                  onPressed: _isLoading ? null : () => _selectRepoDirectly(projectId, fullName),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2563EB),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: const Text(
                    'Connect',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}
