import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/contribution.dart';

class ContributionCard extends StatelessWidget {
  final Contribution contribution;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final VoidCallback? onDelete;
  final VoidCallback? onRequestConfirmation;
  final VoidCallback? onConfirm;
  final VoidCallback? onDispute;
  final bool? isContributor;
  final String? currentUserId;

  const ContributionCard({
    super.key,
    required this.contribution,
    this.onTap,
    this.onLongPress,
    this.onDelete,
    this.onRequestConfirmation,
    this.onConfirm,
    this.onDispute,
    this.isContributor,
    this.currentUserId,
  });

  bool get _resolvedIsContributor {
    if (isContributor != null) return isContributor!;
    if (currentUserId != null && currentUserId!.trim().isNotEmpty) {
      if (contribution.contributor == currentUserId) return true;
      if (contribution.contributorProfile != null &&
          contribution.contributorProfile!['user_id'] == currentUserId) {
        return true;
      }
    }
    return false;
  }


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
    } else if (status == 'confirmed' || status == 'peer-confirmed') {
      bg = Colors.indigo.shade50;
      border = Colors.indigo.shade300;
      text = Colors.indigo.shade800;
      icon = Icons.check_circle_rounded;
      label = 'Peer Confirmed';
    } else if (status == 'needs-review' || contribution.isDisputed) {
      if (_resolvedIsContributor) {
        bg = const Color(0xFFFEF2F2);
        border = const Color(0xFFF87171);
        text = const Color(0xFFB91C1C);
        icon = Icons.warning_amber_rounded;
        label = 'Needs Your Review';
      } else {
        bg = Colors.red.shade50;
        border = Colors.red.shade300;
        text = Colors.red.shade800;
        icon = Icons.error_outline_rounded;
        label = 'Needs Review';
      }
    } else if (contribution.isPendingConfirmation || status.contains('pending-confirmation') || status == 'confirmation-pending') {
      bg = const Color(0xFFFEF3C7);
      border = const Color(0xFFFCD34D);
      text = const Color(0xFFB45309);
      icon = Icons.hourglass_top_rounded;
      label = 'Confirmation Pending';
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
          Flexible(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                color: text,
              ),
              overflow: TextOverflow.ellipsis,
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
    final isContributorNeedsReview = contribution.needsReview && _resolvedIsContributor;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isContributorNeedsReview
              ? const Color(0xFFEF4444)
              : Colors.grey.shade200,
          width: isContributorNeedsReview ? 1.6 : 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: isContributorNeedsReview
                ? const Color(0xFFEF4444).withValues(alpha: 0.10)
                : Colors.black.withValues(alpha: 0.03),
            blurRadius: isContributorNeedsReview ? 10 : 8,
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

                // Contributor-Only "Needs Review" Visual Alert Indicator Banner
                if (isContributorNeedsReview) ...[
                  const SizedBox(height: 10),
                  Container(
                    key: Key('needs_review_contributor_indicator_${contribution.id}'),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFEF2F2),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: const Color(0xFFFECACA), width: 1),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(4),
                          decoration: const BoxDecoration(
                            color: Color(0xFFFEE2E2),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.warning_amber_rounded,
                            size: 16,
                            color: Color(0xFFDC2626),
                          ),
                        ),
                        const SizedBox(width: 10),
                        const Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    'Action Required: Needs Review',
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.bold,
                                      color: Color(0xFF991B1B),
                                    ),
                                  ),
                                  Spacer(),
                                  Icon(
                                    Icons.visibility_off_outlined,
                                    size: 13,
                                    color: Color(0xFFDC2626),
                                  ),
                                  SizedBox(width: 3),
                                  Text(
                                    'Hidden from Passport',
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.w600,
                                      color: Color(0xFFDC2626),
                                    ),
                                  ),
                                ],
                              ),
                              SizedBox(height: 4),
                              Text(
                                'A teammate disputed this deliverable. This item is hidden from your public passport and project stream until revised or resolved.',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Color(0xFFB91C1C),
                                  height: 1.35,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ],

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

                // Request Confirmation Button (if not yet confirmed and callback provided)
                if (!contribution.isConfirmed && onRequestConfirmation != null) ...[
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      key: Key('request_confirmation_btn_${contribution.id}'),
                      onPressed: contribution.isPendingConfirmation
                          ? null
                          : onRequestConfirmation,
                      icon: Icon(
                        contribution.isPendingConfirmation
                            ? Icons.hourglass_top_rounded
                            : Icons.how_to_reg_outlined,
                        size: 16,
                      ),
                      label: Text(
                        contribution.isPendingConfirmation
                            ? 'Confirmation Pending'
                            : 'Request Confirmation',
                      ),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: contribution.isPendingConfirmation
                            ? const Color(0xFFD97706)
                            : const Color(0xFF4F46E5),
                        side: BorderSide(
                          color: contribution.isPendingConfirmation
                              ? const Color(0xFFFCD34D)
                              : const Color(0xFFC7D2FE),
                          width: 1.2,
                        ),
                        backgroundColor: contribution.isPendingConfirmation
                            ? const Color(0xFFFEF3C7)
                            : const Color(0xFFEEF2FF),
                        padding: const EdgeInsets.symmetric(
                            vertical: 8, horizontal: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        textStyle: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ],

                // Teammate Review Action Buttons (Confirm / Dispute)
                if (!contribution.isConfirmed && onConfirm != null && onDispute != null) ...[
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          key: Key('stream_dispute_btn_${contribution.id}'),
                          onPressed: onDispute,
                          icon: const Icon(Icons.close_rounded, color: Colors.redAccent, size: 14),
                          label: const Text(
                            'Dispute',
                            style: TextStyle(
                              color: Colors.redAccent,
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          style: OutlinedButton.styleFrom(
                            side: BorderSide(color: Colors.redAccent.withAlpha(120), width: 1.2),
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        flex: 2,
                        child: ElevatedButton.icon(
                          key: Key('stream_confirm_btn_${contribution.id}'),
                          onPressed: onConfirm,
                          icon: const Icon(Icons.check_rounded, size: 16),
                          label: const Text(
                            'Peer Confirm',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF10B981),
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
