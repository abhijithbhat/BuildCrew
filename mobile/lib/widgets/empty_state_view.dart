import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// A reusable, production-quality empty state view for BuildCrew list screens.
/// Follows the unified Emerald-Champagne design system with dual-tinted illustration
/// badges, crisp typography, and actionable CTA buttons.
class EmptyStateView extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? description;
  final Widget? primaryAction;
  final Widget? secondaryAction;
  final Color? iconColor;
  final Color? badgeColor;
  final Color? badgeBorderColor;
  final double badgeSize;
  final double iconSize;
  final bool isDark;
  final EdgeInsetsGeometry padding;

  const EmptyStateView({
    super.key,
    required this.icon,
    required this.title,
    this.description,
    this.primaryAction,
    this.secondaryAction,
    this.iconColor,
    this.badgeColor,
    this.badgeBorderColor,
    this.badgeSize = 84,
    this.iconSize = 40,
    this.isDark = false,
    this.padding = const EdgeInsets.symmetric(horizontal: 24, vertical: 36),
  });

  @override
  Widget build(BuildContext context) {
    final effectiveBadgeColor = badgeColor ??
        (isDark ? const Color(0xFF151C2C) : AppColors.champagne);
    final effectiveBorderColor = badgeBorderColor ??
        (isDark ? const Color(0xFF1E293B) : AppColors.inputBorder);
    final effectiveIconColor = iconColor ??
        (isDark ? const Color(0xFF60A5FA) : AppColors.emeraldInk);
    final effectiveTitleColor =
        isDark ? Colors.white : const Color(0xFF0F172A);
    final effectiveDescColor =
        isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B);

    return Center(
      child: Padding(
        padding: padding,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // Illustration Badge
            Container(
              width: badgeSize,
              height: badgeSize,
              decoration: BoxDecoration(
                color: effectiveBadgeColor,
                shape: BoxShape.circle,
                border: Border.all(color: effectiveBorderColor, width: 1.5),
                boxShadow: isDark
                    ? [
                        BoxShadow(
                          color: effectiveIconColor.withValues(alpha: 0.12),
                          blurRadius: 20,
                          offset: const Offset(0, 6),
                        ),
                      ]
                    : [
                        BoxShadow(
                          color: AppColors.emeraldInk.withValues(alpha: 0.12),
                          blurRadius: 18,
                          offset: const Offset(0, 6),
                        ),
                      ],
              ),
              child: Center(
                child: Icon(
                  icon,
                  size: iconSize,
                  color: effectiveIconColor,
                ),
              ),
            ),
            const SizedBox(height: 20),

            // Title
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: effectiveTitleColor,
                letterSpacing: -0.3,
              ),
            ),

            // Description
            if (description != null && description!.isNotEmpty) ...[
              const SizedBox(height: 8),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 380),
                child: Text(
                  description!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 13.5,
                    color: effectiveDescColor,
                    height: 1.45,
                  ),
                ),
              ),
            ],

            // Action Buttons
            if (primaryAction != null || secondaryAction != null) ...[
              const SizedBox(height: 24),
              Wrap(
                alignment: WrapAlignment.center,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 12,
                runSpacing: 10,
                children: [
                  ?primaryAction,
                  ?secondaryAction,
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
