import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import 'brand_icons.dart';

/// Two equal-width pill buttons side by side: `[ G  Google ] [ GitHub ]`.
///
/// Used under the "OR" divider on the Login and Sign-up screens.
/// Pass `null` for [onGoogle] / [onGitHub] to disable a button.
class SocialAuthRow extends StatelessWidget {
  const SocialAuthRow({
    super.key,
    required this.onGoogle,
    required this.onGitHub,
    this.isGoogleLoading = false,
    this.isGitHubLoading = false,
    this.googleLabel = 'Google',
    this.githubLabel = 'GitHub',
  });

  final VoidCallback? onGoogle;
  final VoidCallback? onGitHub;
  final bool isGoogleLoading;
  final bool isGitHubLoading;

  /// Visible labels. Google's branding page recommends "Sign in with Google",
  /// "Sign up with Google" or "Continue with Google"; pass one of those if you
  /// ever need strict compliance (it needs more width than a half-width pill).
  final String googleLabel;
  final String githubLabel;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _SocialPillButton(
            key: const Key('social_google_btn'),
            label: googleLabel,
            semanticLabel: 'Continue with Google',
            icon: const GoogleGIcon(size: 22),
            isLoading: isGoogleLoading,
            onPressed: onGoogle,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _SocialPillButton(
            key: const Key('social_github_btn'),
            label: githubLabel,
            semanticLabel: 'Continue with GitHub',
            icon: const GitHubMarkIcon(size: 22),
            isLoading: isGitHubLoading,
            onPressed: onGitHub,
          ),
        ),
      ],
    );
  }
}

class _SocialPillButton extends StatelessWidget {
  const _SocialPillButton({
    super.key,
    required this.label,
    required this.semanticLabel,
    required this.icon,
    required this.isLoading,
    required this.onPressed,
  });

  final String label;
  final String semanticLabel;
  final Widget icon;
  final bool isLoading;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final bool enabled = onPressed != null && !isLoading;
    final bool dimmed = onPressed == null && !isLoading;

    return Semantics(
      button: true,
      enabled: enabled,
      label: semanticLabel,
      excludeSemantics: true,
      child: Opacity(
        opacity: dimmed ? 0.55 : 1.0,
        child: Material(
          color: Colors.white,
          elevation: 0,
          shape: const StadiumBorder(
            side: BorderSide(color: Color(0x73064E3B), width: 1.2),
          ),
          child: InkWell(
            customBorder: const StadiumBorder(),
            onTap: enabled ? onPressed : null,
            splashColor: AppColors.emeraldInk.withValues(alpha: 0.10),
            highlightColor: AppColors.emeraldInk.withValues(alpha: 0.06),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 52),
              child: Center(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 150),
                  child: isLoading
                      ? const SizedBox(
                          key: ValueKey('loading'),
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.2,
                            color: AppColors.emeraldInk,
                          ),
                        )
                      : Row(
                          key: const ValueKey('label'),
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            icon,
                            const SizedBox(width: 10),
                            Text(
                              label,
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.2,
                                color: AppColors.emeraldInk,
                              ),
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
