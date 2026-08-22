import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/contribution.dart';
import '../models/project.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';
import '../widgets/contribution_card.dart';
import 'add_contribution_screen.dart';
import 'my_contributions_screen.dart';
import 'repo_status_screen.dart';
import 'team_roles_screen.dart';




class ProjectDetailScreen extends StatefulWidget {
  static const String routeName = '/project-detail';

  final ProjectService? projectService;
  final StorageService? storageService;

  const ProjectDetailScreen({
    super.key,
    this.projectService,
    this.storageService,
  });

  @override
  State<ProjectDetailScreen> createState() => _ProjectDetailScreenState();
}

class _ProjectDetailScreenState extends State<ProjectDetailScreen> {
  late final ProjectService _projectService;
  late final StorageService _storageService;
  String? _currentUserId;
  bool _isGeneratingInvite = false;
  bool _isGeneratingDraft = false;
  List<Contribution> _contributions = [];
  bool _isLoadingContributions = false;
  String? _contributionsError;
  String _selectedFilter = 'all';
  bool _hasInitialLoadedContributions = false;
  Project? _resolvedProject;
  bool _isLoadingProject = false;

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _storageService = widget.storageService ?? StorageService();
    _loadCurrentUser();
  }

  Future<void> _loadProjectById(String projectId) async {
    setState(() {
      _isLoadingProject = true;
    });
    try {
      final list = await _projectService.listProjects();
      final match = list.firstWhere(
        (p) => p.id == projectId,
        orElse: () => Project(
          id: projectId,
          name: 'Project',
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );
      if (mounted) {
        setState(() {
          _resolvedProject = match;
          _isLoadingProject = false;
          _hasInitialLoadedContributions = true;
        });
        _loadContributions(projectId);
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _resolvedProject = Project(
            id: projectId,
            name: 'Project',
            createdAt: DateTime.now(),
            updatedAt: DateTime.now(),
          );
          _isLoadingProject = false;
          _hasInitialLoadedContributions = true;
        });
        _loadContributions(projectId);
      }
    }
  }

  Future<void> _loadCurrentUser() async {
    final uid = await _storageService.getUserId();
    if (mounted) {
      setState(() {
        _currentUserId = uid;
      });
    }
  }

  Future<void> _shareInvite(Project project, {bool isOwner = false}) async {
    setState(() {
      _isGeneratingInvite = true;
    });

    try {
      final inviteData = await _projectService.generateInviteCode(project.id);
      if (!mounted) return;

      String currentCode = inviteData['invite_code'] as String? ?? 'N/A';
      String currentUrl = inviteData['invite_url'] as String? ?? '';

      showDialog(
        context: context,
        builder: (ctx) => StatefulBuilder(
          builder: (context, setDialogState) {
            bool isRegenerating = false;

            Future<void> handleRegenerate() async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (c) => AlertDialog(
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                  title: const Row(
                    children: [
                      Icon(Icons.security_update_warning_rounded,
                          color: Colors.amber, size: 24),
                      SizedBox(width: 8),
                      Text('Regenerate Code?'),
                    ],
                  ),
                  content: const Text(
                    'This will immediately revoke the current invite code. Anyone with the old code will no longer be able to join.',
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(c, false),
                      child: const Text('Cancel'),
                    ),
                    ElevatedButton(
                      onPressed: () => Navigator.pop(c, true),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.red.shade700,
                        foregroundColor: Colors.white,
                      ),
                      child: const Text('Yes, Regenerate'),
                    ),
                  ],
                ),
              );

              if (confirm == true) {
                setDialogState(() {
                  isRegenerating = true;
                });
                try {
                  final newInviteData =
                      await _projectService.regenerateInviteCode(project.id);
                  setDialogState(() {
                    currentCode =
                        newInviteData['invite_code'] as String? ?? currentCode;
                    currentUrl =
                        newInviteData['invite_url'] as String? ?? currentUrl;
                    isRegenerating = false;
                  });
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('New permanent invite code generated!'),
                        backgroundColor: Colors.green,
                        behavior: SnackBarBehavior.floating,
                      ),
                    );
                  }
                } catch (err) {
                  setDialogState(() {
                    isRegenerating = false;
                  });
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('Failed to regenerate: $err'),
                        backgroundColor: Colors.red.shade700,
                        behavior: SnackBarBehavior.floating,
                      ),
                    );
                  }
                }

              }
            }

            return AlertDialog(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              title: const Row(
                children: [
                  Icon(Icons.share_outlined, color: Colors.blueAccent),
                  SizedBox(width: 8),
                  Text('Project Invite Code'),
                ],
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Share this permanent code with teammates to join "${project.name}":',
                    style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding:
                        const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    decoration: BoxDecoration(
                      color: Colors.blue.shade50.withValues(alpha: 0.5),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.blue.shade200),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        isRegenerating
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : Text(
                                currentCode,
                                style: const TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 2,
                                  color: Colors.blueAccent,
                                ),
                              ),
                        IconButton(
                          icon: const Icon(Icons.copy, color: Colors.blueAccent),
                          tooltip: 'Copy Code',
                          onPressed: () {
                            Clipboard.setData(ClipboardData(text: currentCode));
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Code copied to clipboard!'),
                                behavior: SnackBarBehavior.floating,
                              ),
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Icon(Icons.check_circle_outline_rounded,
                          size: 14, color: Colors.green.shade700),
                      const SizedBox(width: 4),
                      Text(
                        'Permanent project code (never expires)',
                        style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: Colors.green.shade800),
                      ),
                    ],
                  ),
                  if (currentUrl.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      currentUrl,
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                    ),
                  ],
                  if (isOwner) ...[
                    const SizedBox(height: 14),
                    const Divider(),
                    const SizedBox(height: 6),
                    SizedBox(
                      width: double.infinity,
                      child: TextButton.icon(
                        onPressed: isRegenerating ? null : handleRegenerate,
                        icon: const Icon(Icons.refresh_rounded,
                            size: 16, color: Colors.redAccent),
                        label: const Text(
                          'Regenerate Code for Security',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: Colors.redAccent,
                          ),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('Done'),
                ),
              ],
            );
          },
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Could not generate invite: $e'),
            backgroundColor: Colors.red.shade700,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isGeneratingInvite = false;
        });
      }
    }
  }

  bool _isProcessingAction = false;

  Future<void> _dismantleProject(Project project) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: const Row(
          children: [
            Icon(Icons.delete_forever_rounded, color: Colors.red, size: 24),
            SizedBox(width: 8),
            Text('Dismantle Project?'),
          ],
        ),
        content: Text(
          'Are you sure you want to permanently dismantle "${project.name}"? All member roles, milestones, and project data will be deleted permanently.',
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
            child: const Text('Yes, Dismantle'),
          ),
        ],
      ),
    );

    if (confirm == true) {
      setState(() {
        _isProcessingAction = true;
      });

      try {
        await _projectService.deleteProject(project.id);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content:
                  Text('Project "${project.name}" dismantled successfully.'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
          Navigator.pop(context, true);
        }
      } catch (e) {
        if (mounted) {
          setState(() {
            _isProcessingAction = false;
          });
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to dismantle project: $e'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      }
    }
  }

  Future<void> _leaveProject(Project project) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: const Row(
          children: [
            Icon(Icons.exit_to_app_rounded, color: Colors.amber, size: 24),
            SizedBox(width: 8),
            Text('Leave Project?'),
          ],
        ),
        content: Text(
          'Are you sure you want to leave "${project.name}"? Your declared role and milestones will be removed from the team roster.',
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
            child: const Text('Yes, Leave'),
          ),
        ],
      ),
    );

    if (confirm == true) {
      setState(() {
        _isProcessingAction = true;
      });

      try {
        await _projectService.leaveProject(project.id);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('You have left "${project.name}".'),
              backgroundColor: Colors.blueAccent,
              behavior: SnackBarBehavior.floating,
            ),
          );
          Navigator.pop(context, true);
        }
      } catch (e) {
        if (mounted) {
          setState(() {
            _isProcessingAction = false;
          });
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to leave project: $e'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      }
    }
  }

  Future<void> _generateContributionDraft(Project project) async {
    setState(() {
      _isGeneratingDraft = true;
    });

    try {
      final result = await _projectService.generateDraft(project.id);
      if (!mounted) return;

      setState(() {
        _isGeneratingDraft = false;
      });

      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFF2563EB).withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.auto_awesome_rounded,
                  color: Color(0xFF2563EB),
                  size: 22,
                ),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Drafts Generated',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                result.generatedCount > 0
                    ? 'Successfully imported ${result.generatedCount} contribution draft(s) from GitHub with status "source-verified".'
                    : 'GitHub activity is already up to date. No new unimported commits or PRs found.',
                style: const TextStyle(
                  fontSize: 14,
                  height: 1.4,
                ),
              ),
              if (result.generatedCount > 0) ...[
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.green.shade50,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: Colors.green.shade200),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.verified_outlined, color: Colors.green.shade700, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '${result.generatedCount} record(s) marked as source-verified',
                          style: TextStyle(
                            color: Colors.green.shade800,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
          actions: [
              ElevatedButton(
                onPressed: () {
                  Navigator.pop(ctx);
                  _loadContributions(project.id);
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF2563EB),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: const Text('OK'),
              ),
            ],
          ),
        );

        // Refresh contributions list immediately
        _loadContributions(project.id);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isGeneratingDraft = false;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.error_outline_rounded, color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Failed to generate draft: $e',
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ],
          ),
          backgroundColor: Colors.red.shade800,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      );
    }
  }

  Future<void> _loadContributions(String projectId) async {
    setState(() {
      _isLoadingContributions = true;
      _contributionsError = null;
    });

    try {
      final list = await _projectService.listContributions(projectId);
      if (!mounted) return;
      setState(() {
        _contributions = list;
        _isLoadingContributions = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _contributionsError = e.toString();
        _isLoadingContributions = false;
      });
    }
  }

  Future<void> _confirmAndDeleteContribution(Contribution c, Project project) async {
    final isOwner = (project.role ?? '').toLowerCase() == 'owner' ||
        (project.role ?? '').toLowerCase() == 'lead';
    final isAuthor = _currentUserId != null &&
        c.contributor == _currentUserId;

    // 1. If not the author and not team lead
    if (!isAuthor && !isOwner) {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.shield_outlined, color: Colors.amber, size: 22),
              SizedBox(width: 8),
              Text('Action Restricted', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            ],
          ),
          content: const Text(
            'You can only delete impact entries that you created. Other members\' contributions can only be managed by them or the Team Lead.',
            style: TextStyle(fontSize: 13, height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('OK'),
            ),
          ],
        ),
      );
      return;
    }

    if (c.sourceType == 'github_commit' || c.sourceType == 'github_pr') {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.info_outline_rounded, color: Color(0xFF2563EB), size: 22),
              SizedBox(width: 8),
              Text('GitHub Contribution', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            ],
          ),
          content: const Text(
            'This contribution was automatically synced from GitHub. To modify or remove it, please update your repository commits on GitHub.',
            style: TextStyle(fontSize: 13, height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('OK'),
            ),
          ],
        ),
      );
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.delete_forever_rounded, color: Colors.redAccent, size: 24),
            SizedBox(width: 8),
            Text('Delete Impact Log?', style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Text(
          'Are you sure you want to delete "${c.title}"?\n\nThis will remove the logged deliverable and its attached evidence from the contribution stream.',
          style: const TextStyle(fontSize: 13, height: 1.4, color: Colors.black87),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
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
        await _projectService.deleteContribution(c.id, projectId: project.id);
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
          _loadContributions(project.id);
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
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_hasInitialLoadedContributions) {
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is Project) {
        _resolvedProject = args;
        _hasInitialLoadedContributions = true;
        _loadContributions(args.id);
      } else if (args is Map<String, dynamic>) {
        if (args['project'] is Project) {
          _resolvedProject = args['project'] as Project;
          _hasInitialLoadedContributions = true;
          _loadContributions(_resolvedProject!.id);
        } else if (args['projectId'] != null) {
          _hasInitialLoadedContributions = true;
          _loadProjectById(args['projectId'].toString());
        }
      } else if (args is String && args.isNotEmpty) {
        _hasInitialLoadedContributions = true;
        _loadProjectById(args);
      }
    }
  }

  Widget _buildFilterChip(String filterKey, String label) {
    final isSelected = _selectedFilter == filterKey;
    return InkWell(
      onTap: () {
        setState(() {
          _selectedFilter = filterKey;
        });
      },
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? const Color(0xFF2563EB) : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? const Color(0xFF2563EB) : Colors.grey.shade300,
            width: 1.2,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: const Color(0xFF2563EB).withValues(alpha: 0.25),
                    blurRadius: 6,
                    offset: const Offset(0, 2),
                  ),
                ]
              : null,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
            color: isSelected ? Colors.white : Colors.grey.shade700,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final project = _resolvedProject ??
        (ModalRoute.of(context)?.settings.arguments as Project?);

    if (_isLoadingProject) {
      return Scaffold(
        backgroundColor: const Color(0xFF0B0F19),
        appBar: AppBar(
          backgroundColor: const Color(0xFF0B0F19),
          title: const Text('Loading Project...'),
        ),
        body: const Center(
          child: CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF2563EB)),
          ),
        ),
      );
    }

    if (project == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Project Detail')),
        body: const Center(
          child: Text('No project selected.'),
        ),
      );
    }

    final isOwner = (project.role ?? '').toLowerCase() == 'owner' ||
        (project.role ?? '').toLowerCase() == 'lead' ||
        (project.role ?? '').toLowerCase() == 'creator';

    final filteredContributions = _contributions.where((c) {
      if (_selectedFilter == 'source-verified') return c.isSourceVerified;
      if (_selectedFilter == 'confirmed') return c.isConfirmed;
      return true;
    }).toList();

    return Scaffold(
      backgroundColor: Colors.grey.shade50,
      appBar: AppBar(
        title: Text(
          project.name,
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
        actions: [
          IconButton(
            icon: _isGeneratingInvite
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.share_outlined, color: Colors.blueAccent),
            tooltip: 'Invite Members',
            onPressed: () => _shareInvite(project),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24.0),
          children: [
            // Project Summary Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.grey.shade200),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 10,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: isOwner
                              ? Colors.amber.withValues(alpha: 0.1)
                              : Colors.blue.withValues(alpha: 0.1),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          isOwner ? Icons.military_tech_rounded : Icons.folder_outlined,
                          color: isOwner ? Colors.amber.shade800 : Colors.blueAccent,
                          size: 28,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              project.name,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                color: Colors.black87,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: isOwner
                                    ? Colors.amber.shade50
                                    : Colors.blue.shade50,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(
                                  color: isOwner
                                      ? Colors.amber.shade300
                                      : Colors.blue.shade200,
                                ),
                              ),
                              child: Text(
                                isOwner ? '👑 Team Lead (Owner)' : 'Member',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  color: isOwner
                                      ? Colors.amber.shade900
                                      : Colors.blue.shade800,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),

                  if (project.description != null &&
                      project.description!.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Text(
                      'About Project',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.bold,
                        color: Colors.grey.shade600,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      project.description!,
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.grey.shade800,
                        height: 1.4,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 20),

            // View Team Roles Button
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {
                  Navigator.pushNamed(
                    context,
                    TeamRolesScreen.routeName,
                    arguments: project,
                  );
                },
                icon: const Icon(Icons.badge_outlined, color: Colors.blueAccent),
                label: const Text(
                  'View Team Roles & Responsibilities',
                  style: TextStyle(
                    color: Colors.blueAccent,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  side: const BorderSide(color: Colors.blueAccent),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),

            // GitHub Repository Status & Activity Button
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {
                  Navigator.pushNamed(
                    context,
                    RepoStatusScreen.routeName,
                    arguments: {
                      'projectId': project.id,
                      'projectName': project.name,
                      'isOwner': isOwner,
                    },
                  );
                },
                icon: const Icon(Icons.code_rounded, color: Color(0xFF2563EB)),
                label: const Text(
                  'GitHub Integration & Status',
                  style: TextStyle(
                    color: Color(0xFF2563EB),
                    fontWeight: FontWeight.w600,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  side: const BorderSide(color: Color(0xFF2563EB)),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Generate Contribution Draft Button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _isGeneratingDraft ? null : () => _generateContributionDraft(project),
                icon: _isGeneratingDraft
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.auto_awesome_rounded, color: Colors.white),
                label: Text(
                  _isGeneratingDraft ? 'Syncing GitHub Activity...' : 'Generate Contribution Draft',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                    color: Colors.white,
                  ),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF2563EB),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  elevation: 2,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),

            // View My Contributions Button
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                key: const Key('project_detail_my_contributions_btn'),
                onPressed: () {
                  Navigator.pushNamed(
                    context,
                    MyContributionsScreen.routeName,
                    arguments: {'projectId': project.id, 'project': project},
                  );
                },
                icon: const Icon(Icons.person_pin_outlined, color: Color(0xFF10B981)),
                label: const Text(
                  'My Contributions & Impact Log',
                  style: TextStyle(
                    color: Color(0xFF10B981),
                    fontWeight: FontWeight.w600,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  side: const BorderSide(color: Color(0xFF10B981)),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Share Invite Button
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _isGeneratingInvite ? null : () => _shareInvite(project, isOwner: isOwner),
                icon: const Icon(Icons.person_add_alt_1_outlined, color: Colors.blueAccent),
                label: const Text(
                  'Generate Team Invite Code',
                  style: TextStyle(color: Colors.blueAccent, fontWeight: FontWeight.w600),
                ),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  side: const BorderSide(color: Colors.blueAccent),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),

            if (isOwner) ...[
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: TextButton.icon(
                  onPressed: () {
                    final reminderText =
                        '🚀 BuildCrew Reminder: Please declare your project role and milestone deadlines for project "${project.name}" on the BuildCrew app!';
                    Clipboard.setData(ClipboardData(text: reminderText));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Copied team reminder message to clipboard!'),
                        backgroundColor: Colors.blueAccent,
                        behavior: SnackBarBehavior.floating,
                      ),
                    );
                  },
                  icon: const Icon(Icons.campaign_outlined, color: Colors.indigo),
                  label: const Text(
                    'Remind Teammates to Declare Roles',
                    style: TextStyle(
                      color: Colors.indigo,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  style: TextButton.styleFrom(
                    backgroundColor: Colors.indigo.shade50,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),
            ],

            const SizedBox(height: 24),

            // Contribution Stream Header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.history_edu_rounded, color: Color(0xFF2563EB), size: 22),
                    const SizedBox(width: 8),
                    const Text(
                      'Contribution Stream',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Colors.black87,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2563EB).withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '${_contributions.length}',
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF2563EB),
                        ),
                      ),
                    ),
                  ],
                ),
                IconButton(
                  icon: const Icon(Icons.refresh_rounded, size: 20, color: Colors.blueAccent),
                  tooltip: 'Refresh Contributions',
                  onPressed: _isLoadingContributions ? null : () => _loadContributions(project.id),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Action & Filter Chips Row
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  // Add Impact Action Button
                  InkWell(
                    key: const Key('project_detail_add_contribution_btn'),
                    onTap: () async {
                      final result = await Navigator.pushNamed(
                        context,
                        AddContributionScreen.routeName,
                        arguments: {'projectId': project.id},
                      );
                      if (result != null) {
                        _loadContributions(project.id);
                      }
                    },
                    borderRadius: BorderRadius.circular(20),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2563EB),
                        borderRadius: BorderRadius.circular(20),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF2563EB).withValues(alpha: 0.25),
                            blurRadius: 4,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.add_circle_outline_rounded,
                            size: 15,
                            color: Colors.white,
                          ),
                          SizedBox(width: 6),
                          Text(
                            'Add Impact',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  _buildFilterChip('all', 'All (${_contributions.length})'),
                  const SizedBox(width: 8),
                  _buildFilterChip(
                    'source-verified',
                    'Verified (${_contributions.where((c) => c.isSourceVerified).length})',
                  ),
                  const SizedBox(width: 8),
                  _buildFilterChip(
                    'confirmed',
                    'Confirmed (${_contributions.where((c) => c.isConfirmed).length})',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),

            // Contribution Stream List Body
            if (_isLoadingContributions)
              Container(
                padding: const EdgeInsets.all(32),
                alignment: Alignment.center,
                child: const Column(
                  children: [
                    CircularProgressIndicator(strokeWidth: 2.5),
                    SizedBox(height: 12),
                    Text(
                      'Loading contributions stream...',
                      style: TextStyle(color: Colors.grey, fontSize: 13),
                    ),
                  ],
                ),
              )
            else if (_contributionsError != null)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.red.shade200),
                ),
                child: Row(
                  children: [
                    Icon(Icons.error_outline_rounded, color: Colors.red.shade700),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Failed to load stream',
                            style: TextStyle(
                              color: Colors.red.shade900,
                              fontWeight: FontWeight.bold,
                              fontSize: 13,
                            ),
                          ),
                          Text(
                            _contributionsError!,
                            style: TextStyle(color: Colors.red.shade700, fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.replay_rounded, color: Colors.red),
                      onPressed: () => _loadContributions(project.id),
                    ),
                  ],
                ),
              )
            else if (filteredContributions.isEmpty)
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Colors.grey.shade200),
                ),
                child: Column(
                  children: [
                    Icon(Icons.auto_awesome_motion_outlined, color: Colors.grey.shade400, size: 40),
                    const SizedBox(height: 10),
                    Text(
                      _selectedFilter == 'all'
                          ? 'No contributions imported yet'
                          : 'No ${_selectedFilter.replaceAll('-', ' ')} contributions found',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: Colors.grey.shade800,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Tap "Generate Contribution Draft" above to automatically pull and match GitHub activity.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.grey.shade600,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              )
            else
              ...filteredContributions.map(
                (c) {
                  final canDelete = isOwner ||
                      (_currentUserId != null &&
                          c.contributor == _currentUserId);
                  return ContributionCard(
                    contribution: c,
                    onTap: () {
                      // Item tap interaction
                    },
                    onLongPress: () => _confirmAndDeleteContribution(c, project),
                    onDelete: canDelete ? () => _confirmAndDeleteContribution(c, project) : null,
                  );
                },
              ),

            const SizedBox(height: 24),
            const Divider(),
            const SizedBox(height: 12),

            // Lifecycle Actions: Dismantle (Team Lead) or Leave (Teammate)
            if (isOwner)
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _isProcessingAction ? null : () => _dismantleProject(project),
                  icon: const Icon(Icons.delete_forever_rounded, color: Colors.red),
                  label: _isProcessingAction
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.red),
                        )
                      : const Text(
                          'Dismantle / Delete Project',
                          style: TextStyle(
                            color: Colors.red,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    side: BorderSide(color: Colors.red.shade300),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              )
            else
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: _isProcessingAction ? null : () => _leaveProject(project),
                  icon: Icon(Icons.exit_to_app_rounded, color: Colors.red.shade700),
                  label: _isProcessingAction
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.red),
                        )
                      : Text(
                          'Leave Project',
                          style: TextStyle(
                            color: Colors.red.shade700,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    side: BorderSide(color: Colors.red.shade300),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
