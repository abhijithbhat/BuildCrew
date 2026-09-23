import 'package:flutter/material.dart';
import '../models/project.dart';
import '../theme/app_colors.dart';

class ProjectCard extends StatelessWidget {
  final Project project;
  final VoidCallback? onTap;
  final VoidCallback? onInviteTap;

  const ProjectCard({
    super.key,
    required this.project,
    this.onTap,
    this.onInviteTap,
  });

  bool get isOwner {
    final r = (project.role ?? '').toLowerCase();
    return r == 'owner' || r == 'lead' || r == 'creator';
  }

  String _formatDate(DateTime? date) {
    if (date == null) return '';
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final roleColor = isOwner ? const Color(0xFFB45309) : AppColors.emeraldInk;
    final roleBgColor = isOwner ? const Color(0xFFFEF3C7) : AppColors.champagne;
    final roleBorderColor = isOwner ? const Color(0xFFFDE68A) : AppColors.inputBorder;
    final roleLabel = isOwner ? 'Team Lead' : 'Member';

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFFE2E8F0),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.04),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header Row: Avatar + Title + Role Badge
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Container(
                      width: 46,
                      height: 46,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: isOwner
                              ? [AppColors.emeraldInk, const Color(0xFF047857)]
                              : [const Color(0xFF065F46), const Color(0xFF0D9488)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(13),
                        boxShadow: [
                          BoxShadow(
                            color: (isOwner
                                    ? AppColors.emeraldInk
                                    : const Color(0xFF065F46))
                                .withValues(alpha: 0.25),
                            blurRadius: 8,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: Center(
                        child: Text(
                          project.name.isNotEmpty
                              ? project.name.substring(0, 1).toUpperCase()
                              : 'P',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
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
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF0F172A),
                              letterSpacing: -0.2,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          if (project.createdAt != null) ...[
                            const SizedBox(height: 3),
                            Text(
                              'Created ${_formatDate(project.createdAt)}',
                              style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xFF94A3B8),
                                fontWeight: FontWeight.w400,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: roleBgColor,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: roleBorderColor,
                          width: 1,
                        ),
                      ),
                      child: Text(
                        roleLabel,
                        style: TextStyle(
                          color: roleColor,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.1,
                        ),
                      ),
                    ),
                  ],
                ),

                // Description
                if (project.description != null &&
                    project.description!.trim().isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    project.description!.trim(),
                    style: const TextStyle(
                      fontSize: 13,
                      color: Color(0xFF475569),
                      height: 1.45,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],

                const SizedBox(height: 14),
                const Divider(height: 1, color: Color(0xFFF1F5F9)),
                const SizedBox(height: 10),

                // Bottom Actions Row
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.group_outlined,
                          size: 16,
                          color: const Color(0xFF64748B),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          isOwner ? 'Crew Admin' : 'Collaborator',
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(0xFF64748B),
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                    Row(
                      children: [
                        if (onInviteTap != null)
                          InkWell(
                            onTap: onInviteTap,
                            borderRadius: BorderRadius.circular(8),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 4,
                              ),
                              child: Row(
                                children: const [
                                  Icon(
                                    Icons.share_outlined,
                                    size: 14,
                                    color: AppColors.emeraldInk,
                                  ),
                                  SizedBox(width: 4),
                                  Text(
                                    'Invite',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: AppColors.emeraldInk,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        const SizedBox(width: 4),
                        const Icon(
                          Icons.arrow_forward_ios_rounded,
                          size: 12,
                          color: Color(0xFF94A3B8),
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
