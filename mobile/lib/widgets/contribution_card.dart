import 'package:flutter/material.dart';
import '../models/contribution.dart';

class ContributionCard extends StatelessWidget {
  final Contribution contribution;
  final VoidCallback? onTap;

  const ContributionCard({
    super.key,
    required this.contribution,
    this.onTap,
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

  IconData _getSourceIcon() {
    switch (contribution.sourceType) {
      case 'github_commit':
        return Icons.commit_rounded;
      case 'github_pr':
        return Icons.merge_type_rounded;
      case 'github_issue':
        return Icons.task_alt_rounded;
      default:
        return Icons.code_rounded;
    }
  }

  Color _getSourceColor() {
    switch (contribution.sourceType) {
      case 'github_commit':
        return const Color(0xFF3B82F6); // Blue
      case 'github_pr':
        return const Color(0xFF8B5CF6); // Purple
      case 'github_issue':
        return const Color(0xFF10B981); // Emerald Green
      default:
        return const Color(0xFF64748B);
    }
  }

  String _getSourceLabel() {
    switch (contribution.sourceType) {
      case 'github_commit':
        return 'Git Commit';
      case 'github_pr':
        return 'Pull Request';
      case 'github_issue':
        return 'GitHub Issue';
      default:
        return 'GitHub Activity';
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

  @override
  Widget build(BuildContext context) {
    final sourceColor = _getSourceColor();
    final dateStr = _formatDate(contribution.createdAt, contribution.dateRange);
    final contributorName = contribution.contributorName ?? 'Team Contributor';
    final initial = contributorName.isNotEmpty ? contributorName[0].toUpperCase() : 'C';

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
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top Row: Source badge + Status chip
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
                    _buildStatusChip(),
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
