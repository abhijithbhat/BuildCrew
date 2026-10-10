import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// A small, reusable, production-grade 'Couldn\'t connect — Retry' widget.
/// Used on My Projects, Pending Confirmations, and My Contributions.
/// Conforms to BuildCrew's emerald-champagne design standards.
class ConnectionErrorRetryWidget extends StatelessWidget {
  final String? title;
  final String? message;
  final VoidCallback onRetry;
  final bool isCompact;

  const ConnectionErrorRetryWidget({
    super.key,
    this.title,
    this.message,
    required this.onRetry,
    this.isCompact = false,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveTitle = title ?? "Couldn't connect to server";
    final effectiveMessage = message ?? "Can't reach the server. Please check your network connection and try again.";

    if (isCompact) {
      return Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFFFFF1F2),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFFECDD3)),
        ),
        child: Row(
          children: [
            const Icon(
              Icons.cloud_off_rounded,
              color: Color(0xFFE11D48),
              size: 20,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                effectiveMessage,
                style: const TextStyle(
                  color: Color(0xFFBE123C),
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            const SizedBox(width: 8),
            TextButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 16, color: Color(0xFFE11D48)),
              label: const Text(
                'Retry',
                style: TextStyle(
                  color: Color(0xFFE11D48),
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
      );
    }

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: const Color(0xFFFEF2F2),
                shape: BoxShape.circle,
                border: Border.all(color: const Color(0xFFFECDD3), width: 1.5),
              ),
              child: const Center(
                child: Icon(
                  Icons.cloud_off_rounded,
                  size: 36,
                  color: Color(0xFFE11D48),
                ),
              ),
            ),
            const SizedBox(height: 18),
            Text(
              effectiveTitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: AppColors.emeraldInk,
                letterSpacing: -0.3,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              effectiveMessage,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 13,
                color: AppColors.textMuted,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Retry'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.emeraldInk,
                foregroundColor: Colors.white,
                elevation: 0,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
