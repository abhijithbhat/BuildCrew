import 'package:flutter/material.dart';
import '../services/github_service.dart';
import '../theme/app_colors.dart';
import '../utils/error_messages.dart';

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
  String? _connectedRepo;
  final TextEditingController _repoNameController = TextEditingController();

  List<Map<String, dynamic>> _availableRepos = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _gitHubService = widget.gitHubService ?? GitHubService();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final projectId = _getEffectiveProjectId();
      if (projectId.isNotEmpty) {
        _checkIfAlreadyConnected(projectId, silent: true);
        _fetchAvailableRepos(projectId);
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _repoNameController.dispose();
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
        setState(() {
          _connectedRepo = repoFullName;
        });
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
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Failed to connect repository: ${friendlyError(e)}';
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
        final inst = data['installation'];
        final repo = inst is Map ? inst['repo_full_name'] as String? : null;
        setState(() {
          _connectedRepo = repo;
        });
        if (!silent) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Row(
                children: [
                  Icon(Icons.check_circle_rounded, color: Colors.white, size: 20),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text('GitHub repository successfully connected!'),
                  ),
                ],
              ),
              backgroundColor: const Color(0xFF10B981),
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          );
        }
      } else if (!silent && mounted) {
        setState(() {
          _errorMessage =
              'No active installation detected yet. Please ensure you clicked "Save" or "Install & Authorize" on GitHub, or use the direct link option below.';
        });
      }
    } catch (e) {
      if (!silent && mounted) {
        setState(() {
          _errorMessage = friendlyError(e);
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
        repoFullName: repoName,
      );

      if (mounted) {
        setState(() {
          _connectedRepo = repoName;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Linked "$repoName" successfully!'),
            backgroundColor: const Color(0xFF10B981),
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
          _errorMessage = 'Failed to link repository: ${friendlyError(e)}';
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
      // 1. Try to link directly without a GitHub trip if the lead already has an installation
      try {
        final installData = await _gitHubService.linkInstallation(projectId);
        if (mounted) {
          final repoLinked = installData['repo_full_name'] as String? ?? '';
          setState(() {
            _connectedRepo = repoLinked.isNotEmpty ? repoLinked : null;
          });
          await _fetchAvailableRepos(projectId);
          if (mounted) {
            _showRepositoryPickerModal(projectId);
          }
          return;
        }
      } catch (linkError) {
        final errStr = linkError.toString().toLowerCase();
        final isNoInstallation = errStr.contains('no active github app installation') ||
            errStr.contains('no installation') ||
            errStr.contains('install the github app first') ||
            errStr.contains('install the app first') ||
            errStr.contains('no active installation') ||
            errStr.contains('400') ||
            errStr.contains('bad request');

        if (!isNoInstallation) {
          // If it was another error (not 'no installation'), display it
          if (mounted) {
            setState(() {
              _errorMessage = friendlyError(linkError);
            });
          }
          return;
        }
      }

      // 2. Only when server answers 'no installation' does the app open install-url
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
            backgroundColor: AppColors.emeraldInk,
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
          _errorMessage = friendlyError(e);
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

  Future<void> _showRepositoryPickerModal(String projectId) async {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
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
                  child: CircularProgressIndicator(color: AppColors.emeraldInk),
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
                      style: const TextStyle(color: AppColors.bodyText, fontSize: 13),
                    ),
                  ],
                ),
              );
            }

            final data = snapshot.data!;
            final currentRepo = _connectedRepo ?? (data['current_repo'] as String? ?? '');
            final rawRepos = data['repositories'] as List<dynamic>? ?? [];
            final repos = rawRepos.map((r) => Map<String, dynamic>.from(r as Map)).toList();

            if (repos.isEmpty) {
              return const Padding(
                padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.folder_open_rounded, color: AppColors.emeraldInk, size: 48),
                    SizedBox(height: 12),
                    Text(
                      'No Repositories Found',
                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                    ),
                    SizedBox(height: 6),
                    Text(
                      'No repositories found under this installation.',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 13),
                    ),
                  ],
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
                          color: AppColors.emeraldInk.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.swap_horiz_rounded, color: AppColors.emeraldInk, size: 20),
                      ),
                      const SizedBox(width: 12),
                      const Text(
                        'Select Repository',
                        style: TextStyle(
                          color: AppColors.emeraldInk,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Choose which repository to link to this project:',
                    style: TextStyle(color: AppColors.bodyText.withValues(alpha: 0.7), fontSize: 13),
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

                        return Material(
                          color: isSelected ? AppColors.champagne : Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: isSelected ? AppColors.emeraldInk : AppColors.inputBorder,
                                width: isSelected ? 1.5 : 1,
                              ),
                            ),
                            child: ListTile(
                            leading: Icon(
                              Icons.code_rounded,
                              color: isSelected ? AppColors.emeraldInk : AppColors.bodyText.withValues(alpha: 0.5),
                            ),
                            title: Text(
                              fullRepoName,
                              style: TextStyle(
                                color: isSelected ? AppColors.emeraldInk : AppColors.bodyText,
                                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                                fontSize: 14,
                              ),
                            ),
                            trailing: isSelected
                                ? const Icon(Icons.check_circle_rounded, color: AppColors.emeraldInk)
                                : null,
                            onTap: () async {
                              Navigator.pop(ctx);
                              await _selectRepoDirectly(projectId, fullRepoName);
                            },
                          ),
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
      backgroundColor: AppColors.champagne,
      appBar: AppBar(
        backgroundColor: AppColors.champagne,
        elevation: 0,
        scrolledUnderElevation: 0,
        shape: const Border(
          bottom: BorderSide(color: AppColors.inputBorder, width: 1),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded,
              color: AppColors.emeraldInk, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Connect Repository',
          style: TextStyle(
            color: AppColors.emeraldInk,
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
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
                  width: 68,
                  height: 68,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [AppColors.emeraldInk, AppColors.emeraldInk],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(20),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.emeraldInk.withValues(alpha: 0.35),
                        blurRadius: 18,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: const Center(
                    child: Icon(
                      Icons.code_rounded,
                      size: 34,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 22),

              // Title & Subtitle
              Text(
                'Link GitHub to\n$effectiveProjectName',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: AppColors.emeraldInk,
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
                style: const TextStyle(
                  color: AppColors.textMuted,
                  fontSize: 14,
                  height: 1.5,
                ),
              ),

              const SizedBox(height: 24),

              // Connected Repository Card (with prominent Change repository action)
              if (_connectedRepo != null && _connectedRepo!.isNotEmpty)
                _buildConnectedRepoCard(effectiveProjectId),

              // Available / Detected GitHub Repositories (1-Tap Direct Connect)
              _buildAvailableRepositoriesSection(effectiveProjectId),

              const SizedBox(height: 8),

              // Feature Highlights Card
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: AppColors.divider,
                    width: 1,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.emeraldInk.withValues(alpha: 0.04),
                      blurRadius: 12,
                      offset: const Offset(0, 3),
                    ),
                  ],
                ),
                child: Column(
                  children: [
                    _buildFeatureRow(
                      icon: Icons.history_rounded,
                      iconColor: const Color(0xFF3B82F6),
                      title: 'Live Commit Sync',
                      subtitle:
                          'Track team branch pushes and commit logs in real-time.',
                    ),
                    const Divider(
                      color: AppColors.divider,
                      height: 28,
                      thickness: 1,
                    ),
                    _buildFeatureRow(
                      icon: Icons.alt_route_rounded,
                      iconColor: const Color(0xFF8B5CF6),
                      title: 'Pull Request Activity',
                      subtitle:
                          'Monitor reviews, approvals, and merged feature branches.',
                    ),
                    const Divider(
                      color: AppColors.divider,
                      height: 28,
                      thickness: 1,
                    ),
                    _buildFeatureRow(
                      icon: Icons.bug_report_outlined,
                      iconColor: const Color(0xFF10B981),
                      title: 'Issue & Milestone Tracking',
                      subtitle:
                          'Stay aligned on bugs, user stories, and tasks.',
                    ),
                    const Divider(
                      color: AppColors.divider,
                      height: 28,
                      thickness: 1,
                    ),
                    _buildFeatureRow(
                      icon: Icons.lock_outline_rounded,
                      iconColor: const Color(0xFFF59E0B),
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
                    color: const Color(0xFFFFF1F2),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: const Color(0xFFFECDD3),
                    ),
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
                            color: Color(0xFFBE123C),
                            fontSize: 13,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],

              // Connect Button
              SizedBox(
                height: 54,
                child: ElevatedButton(
                  onPressed:
                      _isLoading ? null : () => _onConnectPressed(effectiveProjectId),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.emeraldInk,
                    foregroundColor: AppColors.champagne,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                    elevation: 0,
                  ),
                  child: _isLoading
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.5,
                            color: AppColors.champagne,
                          ),
                        )
                      : const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.open_in_browser_rounded,
                                color: AppColors.champagne, size: 20),
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
                height: 50,
                child: OutlinedButton.icon(
                  onPressed: _isLoading
                      ? null
                      : () => _checkIfAlreadyConnected(effectiveProjectId),
                  icon: const Icon(Icons.sync_rounded, color: AppColors.emeraldInk, size: 20),
                  label: const Text(
                    'I\'ve Installed on GitHub → Verify Connection',
                    style: TextStyle(
                      color: AppColors.emeraldInk,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: AppColors.emeraldInk, width: 1.5),
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
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: AppColors.divider),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.emeraldInk.withValues(alpha: 0.04),
                      blurRadius: 10,
                      offset: const Offset(0, 3),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.bolt_rounded, color: Color(0xFFF59E0B), size: 20),
                        SizedBox(width: 8),
                        Text(
                          'Direct Repository Link',
                          style: TextStyle(
                            color: AppColors.emeraldInk,
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'If the app is already installed on your GitHub account, link your repository directly:',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 12, height: 1.4),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _repoNameController,
                      style: const TextStyle(color: AppColors.emeraldInk, fontSize: 14),
                      decoration: InputDecoration(
                        labelText: 'Repository (owner/repo)',
                        hintText: 'e.g. your-username/project-repo',
                        hintStyle: const TextStyle(color: Color(0xFFB0BEC5), fontSize: 13),
                        labelStyle: const TextStyle(color: AppColors.textMuted, fontSize: 13),
                        filled: true,
                        fillColor: AppColors.champagne,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppColors.divider),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppColors.divider),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppColors.emeraldInk, width: 1.5),
                        ),
                        prefixIcon: const Icon(Icons.code_rounded, color: AppColors.emeraldInk, size: 18),
                      ),
                    ),

                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: _isLoading ? null : () => _linkDirectly(effectiveProjectId),
                        icon: const Icon(Icons.link_rounded, size: 18),
                        label: const Text(
                          'Link Repository to Project',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.emeraldInk,
                          foregroundColor: AppColors.champagne,
                          elevation: 0,
                          padding: const EdgeInsets.symmetric(vertical: 13),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 16),

              // Disclaimer
              const Text(
                'Make sure your backend and ngrok tunnel are running during installation.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.hint,
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
                  color: AppColors.emeraldInk,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                subtitle,
                style: const TextStyle(
                  color: AppColors.textMuted,
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

  Widget _buildConnectedRepoCard(String projectId) {
    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF10B981), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF10B981).withValues(alpha: 0.1),
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
                  color: const Color(0xFFECFDF5),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.check_circle_rounded,
                  color: Color(0xFF10B981),
                  size: 22,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Connected Repository',
                      style: TextStyle(
                        color: AppColors.textMuted,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _connectedRepo!,
                      style: const TextStyle(
                        color: AppColors.emeraldInk,
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _isLoading
                      ? null
                      : () => _showRepositoryPickerModal(projectId),
                  icon: const Icon(Icons.swap_horiz_rounded, size: 18),
                  label: const Text(
                    'Change repository',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.emeraldInk,
                    foregroundColor: AppColors.champagne,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              OutlinedButton.icon(
                onPressed: () {
                  Navigator.pushReplacementNamed(
                    context,
                    '/repo-status',
                    arguments: {'projectId': projectId},
                  );
                },
                icon: const Icon(Icons.dashboard_rounded, size: 18),
                label: const Text(
                  'Status',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.emeraldInk,
                  side: const BorderSide(color: AppColors.emeraldInk, width: 1.5),
                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAvailableRepositoriesSection(String projectId) {
    if (_availableRepos.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.emeraldInk.withValues(alpha: 0.3),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.emeraldInk.withValues(alpha: 0.06),
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
                  color: AppColors.champagne,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.auto_awesome_rounded,
                  color: AppColors.emeraldInk,
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
                        color: AppColors.emeraldInk,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Tap to connect directly to this project:',
                      style: TextStyle(
                        color: AppColors.textMuted,
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
              child: Material(
                color: AppColors.champagne,
                borderRadius: BorderRadius.circular(10),
                child: Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppColors.divider),
                  ),
                  child: ListTile(
                dense: true,
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                leading: const Icon(
                  Icons.code_rounded,
                  color: AppColors.emeraldInk,
                  size: 20,
                ),
                title: Text(
                  fullName,
                  style: const TextStyle(
                    color: AppColors.emeraldInk,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
                trailing: ElevatedButton(
                  onPressed: _isLoading ? null : () => _selectRepoDirectly(projectId, fullName),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.emeraldInk,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    elevation: 0,
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
            ),
          ),
        );
      }),
        ],
      ),
    );
  }
}
