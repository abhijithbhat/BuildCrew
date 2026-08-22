import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/contribution.dart';

class ContributionCard extends StatelessWidget {
  final Contribution contribution;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final VoidCallback? onDelete;

  const ContributionCard({
    super.key,
    required this.contribution,
    this.onTap,
    this.onLongPress,
    this.onDelete,
  });

  String _formatDate(DateTime? date, String? rawDate) {
    if (date != null) {
      return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    }
    if (rawDate != null && rawDate.isNotEmpty) {
      if (rawDate.contains('T')) {
        return rawDate.split('T')[0];
      }
      return rawDate;
    }
    return '';
  }

  bool _isImageUrl(String? url) {
    if (url == null || url.trim().isEmpty) return false;
    final lower = url.trim().toLowerCase();
    return lower.endsWith('.png') ||
        lower.endsWith('.jpg') ||
        lower.endsWith('.jpeg') ||
        lower.endsWith('.webp') ||
        lower.endsWith('.gif') ||
        (lower.contains('/evidence/') &&
            (lower.contains('.png') ||
                lower.contains('.jpg') ||
                lower.contains('.jpeg') ||
                lower.contains('.webp')));
  }

  String _cleanFileName(String url) {
    try {
      if (url.startsWith('http://') || url.startsWith('https://')) {
        if (!url.contains('/evidence/') && !url.contains('/static/evidence/')) {
          return url;
        }
      }
      final uri = Uri.parse(url);
      final seg = uri.pathSegments.isNotEmpty ? uri.pathSegments.last : url;
      if (seg.contains('_')) {
        final parts = seg.split('_');
        if (parts.length > 1 && parts[0].length <= 16) {
          return parts.sublist(1).join('_');
        }
      }
      return seg;
    } catch (_) {
      return url;
    }
  }

  IconData _getSourceIcon() {
    if (contribution.sourceType == 'github_commit') return Icons.commit_rounded;
    if (contribution.sourceType == 'github_pr') return Icons.merge_type_rounded;
    if (contribution.sourceType == 'github_issue') return Icons.task_alt_rounded;

    final cat = (contribution.category ?? '').toLowerCase();
    switch (cat) {
      case 'design':
        return Icons.palette_outlined;
      case 'research':
        return Icons.science_outlined;
      case 'documentation':
        return Icons.description_outlined;
      case 'presentation':
        return Icons.slideshow_outlined;
      case 'devops':
        return Icons.cloud_sync_outlined;
      case 'testing':
        return Icons.bug_report_outlined;
      case 'code':
        return Icons.terminal_rounded;
      default:
        return Icons.assignment_turned_in_outlined;
    }
  }

  Color _getSourceColor() {
    if (contribution.sourceType == 'github_commit') return const Color(0xFF3B82F6);
    if (contribution.sourceType == 'github_pr') return const Color(0xFF8B5CF6);
    if (contribution.sourceType == 'github_issue') return const Color(0xFF10B981);

    final cat = (contribution.category ?? '').toLowerCase();
    switch (cat) {
      case 'design':
        return const Color(0xFF8B5CF6); // Purple
      case 'research':
        return const Color(0xFFEC4899); // Pink
      case 'documentation':
        return const Color(0xFF10B981); // Emerald Green
      case 'presentation':
        return const Color(0xFFF59E0B); // Amber
      case 'devops':
        return const Color(0xFF06B6D4); // Cyan
      case 'testing':
        return const Color(0xFFEF4444); // Red
      case 'code':
        return const Color(0xFF3B82F6); // Blue
      default:
        return const Color(0xFF6366F1); // Indigo
    }
  }

  String _getSourceLabel() {
    if (contribution.sourceType == 'github_commit') return 'Git Commit';
    if (contribution.sourceType == 'github_pr') return 'Pull Request';
    if (contribution.sourceType == 'github_issue') return 'GitHub Issue';

    final cat = (contribution.category ?? '').toLowerCase();
    switch (cat) {
      case 'design':
        return 'UI/UX Design';
      case 'research':
        return 'User Research';
      case 'documentation':
        return 'Documentation';
      case 'presentation':
        return 'Presentation';
      case 'devops':
        return 'DevOps / Cloud';
      case 'testing':
        return 'QA & Testing';
      case 'code':
        return 'Custom Code';
      default:
        return 'Manual Impact';
    }
  }

  Widget _buildStatusChip() {
    final status = contribution.verificationStatus.toLowerCase();
    Color bg;
    Color border;
    Color text;
    IconData icon;
    String label;

    if (status == 'source-verified') {
      bg = Colors.green.shade50;
      border = Colors.green.shade300;
      text = Colors.green.shade800;
      icon = Icons.verified_rounded;
      label = 'Source Verified';
    } else if (status == 'confirmed') {
      bg = Colors.indigo.shade50;
      border = Colors.indigo.shade300;
      text = Colors.indigo.shade800;
      icon = Icons.check_circle_rounded;
      label = 'Peer Confirmed';
    } else if (status == 'self-declared') {
      bg = const Color(0xFFEFF6FF);
      border = const Color(0xFF93C5FD);
      text = const Color(0xFF1D4ED8);
      icon = Icons.person_pin_outlined;
      label = 'Self Declared';
    } else {
      bg = Colors.amber.shade50;
      border = Colors.amber.shade300;
      text = Colors.amber.shade900;
      icon = Icons.schedule_rounded;
      label = 'Draft Pending';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: border, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: text),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: text,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _openEvidence(BuildContext context, String rawUrl) async {
    final url = rawUrl.trim();
    if (_isImageUrl(url)) {
      _showImageDialog(context, url);
      return;
    }

    try {
      final uri = Uri.parse(url);
      final canLaunch = await canLaunchUrl(uri);
      if (canLaunch) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } else {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Could not open file: $url'),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
            ),
          );
        }
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error launching link: $e'),
            backgroundColor: Colors.red.shade700,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  void _showImageDialog(BuildContext context, String imageUrl) {
    final cleanName = _cleanFileName(imageUrl);
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: const Color(0xFF0F172A),
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Dialog Header
              Container(
                color: const Color(0xFF1E293B),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                child: Row(
                  children: [
                    const Icon(Icons.image_outlined, color: Color(0xFF8B5CF6), size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        cleanName,
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 13,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.open_in_new_rounded, color: Colors.white70, size: 18),
                      tooltip: 'Open in Browser',
                      onPressed: () => launchUrl(Uri.parse(imageUrl), mode: LaunchMode.externalApplication),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded, color: Colors.white, size: 20),
                      onPressed: () => Navigator.pop(ctx),
                    ),
                  ],
                ),
              ),
              // Image Container with InteractiveViewer
              Container(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(context).size.height * 0.65,
                  maxWidth: double.infinity,
                ),
                color: const Color(0xFF0B1120),
                child: InteractiveViewer(
                  panEnabled: true,
                  minScale: 0.8,
                  maxScale: 4.0,
                  child: Image.network(
                    imageUrl,
                    fit: BoxFit.contain,
                    loadingBuilder: (context, child, loadingProgress) {
                      if (loadingProgress == null) return child;
                      return const Center(
                        child: Padding(
                          padding: EdgeInsets.all(40.0),
                          child: CircularProgressIndicator(color: Color(0xFF8B5CF6)),
                        ),
                      );
                    },
                    errorBuilder: (context, error, stackTrace) {
                      return Container(
                        padding: const EdgeInsets.all(32),
                        alignment: Alignment.center,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.broken_image_outlined, color: Colors.white54, size: 48),
                            const SizedBox(height: 8),
                            const Text(
                              'Unable to render image preview',
                              style: TextStyle(color: Colors.white70, fontSize: 13),
                            ),
                            const SizedBox(height: 8),
                            TextButton.icon(
                              onPressed: () => launchUrl(Uri.parse(imageUrl), mode: LaunchMode.externalApplication),
                              icon: const Icon(Icons.open_in_browser_rounded, size: 16),
                              label: const Text('Open External Link'),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final sourceColor = _getSourceColor();
    final dateStr = _formatDate(contribution.createdAt, contribution.dateRange);
    final contributorName = contribution.contributorName ?? 'Team Contributor';
    final initial = contributorName.isNotEmpty ? contributorName[0].toUpperCase() : 'C';
    final hasEvidence = contribution.evidenceLink != null && contribution.evidenceLink!.trim().isNotEmpty;
    final isImage = hasEvidence && _isImageUrl(contribution.evidenceLink);

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.grey.shade200, width: 1.2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          onLongPress: onLongPress ?? onDelete,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top Row: Source badge + Status chip + optional delete action
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: sourceColor.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: sourceColor.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(_getSourceIcon(), size: 13, color: sourceColor),
                          const SizedBox(width: 4),
                          Text(
                            _getSourceLabel(),
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: sourceColor,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _buildStatusChip(),
                        if (onDelete != null) ...[
                          const SizedBox(width: 6),
                          InkWell(
                            onTap: onDelete,
                            borderRadius: BorderRadius.circular(6),
                            child: Padding(
                              padding: const EdgeInsets.all(2.0),
                              child: Icon(
                                Icons.delete_outline_rounded,
                                size: 16,
                                color: Colors.grey.shade400,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 10),

                // Title
                Text(
                  contribution.title,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.bold,
                    color: Colors.black87,
                    height: 1.3,
                  ),
                ),

                // Description if available
                if (contribution.description != null && contribution.description!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    contribution.description!,
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.grey.shade600,
                      height: 1.3,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],

                // Inline Image Preview (if evidence is image / screenshot)
                if (isImage) ...[
                  const SizedBox(height: 10),
                  InkWell(
                    onTap: () => _showImageDialog(context, contribution.evidenceLink!),
                    borderRadius: BorderRadius.circular(10),
                    child: Container(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: Colors.grey.shade200, width: 1),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Stack(
                        children: [
                          Image.network(
                            contribution.evidenceLink!,
                            height: 150,
                            width: double.infinity,
                            fit: BoxFit.cover,
                            loadingBuilder: (context, child, loadingProgress) {
                              if (loadingProgress == null) return child;
                              return Container(
                                height: 120,
                                color: Colors.grey.shade50,
                                child: const Center(
                                  child: SizedBox(
                                    width: 22,
                                    height: 22,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  ),
                                ),
                              );
                            },
                            errorBuilder: (context, error, stackTrace) => Container(
                              height: 60,
                              color: Colors.grey.shade50,
                              padding: const EdgeInsets.symmetric(horizontal: 12),
                              child: const Row(
                                children: [
                                  Icon(Icons.image_outlined, color: Colors.grey, size: 18),
                                  SizedBox(width: 6),
                                  Text(
                                    'Screenshot Attached (Tap to View)',
                                    style: TextStyle(color: Colors.black54, fontSize: 12),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          Positioned(
                            bottom: 8,
                            right: 8,
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.7),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: const Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(Icons.zoom_in_rounded, size: 14, color: Colors.white),
                                  SizedBox(width: 4),
                                  Text(
                                    'View Fullscreen',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],

                // Interactive Evidence Link / File Badge
                if (hasEvidence) ...[
                  const SizedBox(height: 8),
                  InkWell(
                    onTap: () => _openEvidence(context, contribution.evidenceLink!),
                    borderRadius: BorderRadius.circular(6),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2563EB).withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: const Color(0xFF2563EB).withValues(alpha: 0.25)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            isImage
                                ? Icons.image_outlined
                                : (contribution.evidenceLink!.toLowerCase().contains('.pdf')
                                    ? Icons.picture_as_pdf_outlined
                                    : (contribution.evidenceLink!.toLowerCase().contains('.ppt')
                                        ? Icons.slideshow_outlined
                                        : Icons.attachment_rounded)),
                            size: 14,
                            color: const Color(0xFF2563EB),
                          ),
                          const SizedBox(width: 6),
                          Flexible(
                            child: Text(
                              contribution.evidenceLink!,
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: Color(0xFF2563EB),
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 4),
                          const Icon(Icons.arrow_outward_rounded, size: 12, color: Color(0xFF2563EB)),
                        ],
                      ),
                    ),
                  ),
                ],

                const SizedBox(height: 12),
                const Divider(height: 1, thickness: 0.8),
                const SizedBox(height: 10),

                // Bottom Row: Contributor avatar + name + date
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Row(
                        children: [
                          CircleAvatar(
                            radius: 12,
                            backgroundColor: sourceColor.withValues(alpha: 0.15),
                            child: Text(
                              initial,
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: sourceColor,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              contributorName,
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: Colors.black87,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (dateStr.isNotEmpty)
                      Row(
                        children: [
                          Icon(Icons.calendar_today_outlined, size: 12, color: Colors.grey.shade500),
                          const SizedBox(width: 4),
                          Text(
                            dateStr,
                            style: TextStyle(
                              fontSize: 11,
                              color: Colors.grey.shade500,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
