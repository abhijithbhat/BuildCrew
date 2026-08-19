import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/project.dart';
import '../services/project_service.dart';
import 'repo_status_screen.dart';
import 'team_roles_screen.dart';



class ProjectDetailScreen extends StatefulWidget {
  static const String routeName = '/project-detail';

  const ProjectDetailScreen({super.key});

  @override
  State<ProjectDetailScreen> createState() => _ProjectDetailScreenState();
}

class _ProjectDetailScreenState extends State<ProjectDetailScreen> {
  final ProjectService _projectService = ProjectService();
  bool _isGeneratingInvite = false;

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

  @override
  Widget build(BuildContext context) {
    final project = ModalRoute.of(context)?.settings.arguments as Project?;

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

            // Share Invite Button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _isGeneratingInvite ? null : () => _shareInvite(project, isOwner: isOwner),
                icon: const Icon(Icons.person_add_alt_1_outlined),
                label: const Text('Generate Team Invite Code'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blueAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
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
