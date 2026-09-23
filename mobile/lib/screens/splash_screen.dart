import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// A production-quality splash screen for BuildCrew.
/// Matches the native Android launch theme seamlessly with deep slate background,
/// branded collaboration emblem, smooth loading animation, and Play Store typography.
class SplashScreen extends StatelessWidget {
  static const String routeName = '/splash';

  final String? message;

  const SplashScreen({
    super.key,
    this.message,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.emeraldInk,
      body: SafeArea(
        child: Stack(
          children: [
            // Main Centered Brand Content
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Brand Logo Emblem (Solid #064E3B shield with #F8E7C9 checkmark)
                    const ShieldCheckMark(size: 104),
                    const SizedBox(height: 24),

                    // App Title
                    const Text(
                      'BuildCrew',
                      style: TextStyle(
                        fontSize: 30,
                        fontWeight: FontWeight.w800,
                        color: AppColors.champagne,
                        letterSpacing: -0.6,
                      ),
                    ),
                    const SizedBox(height: 6),

                    // Tagline Badge
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: AppColors.champagne.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: AppColors.champagne.withValues(alpha: 0.35),
                          width: 1,
                        ),
                      ),
                      child: const Text(
                        'AUTONOMOUS WORKSPACE',
                        style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          color: AppColors.champagne,
                          letterSpacing: 1.3,
                        ),
                      ),
                    ),
                    const SizedBox(height: 36),

                    // Loading Indicator
                    const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.6,
                        valueColor:
                            AlwaysStoppedAnimation<Color>(AppColors.champagne),
                      ),
                    ),
                    const SizedBox(height: 14),

                    // Status Message
                    Text(
                      message ?? 'Initializing workspace...',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 13,
                        color: AppColors.champagne.withValues(alpha: 0.8),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Bottom Footer
            Positioned(
              left: 0,
              right: 0,
              bottom: 24,
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.shield_outlined,
                        size: 13,
                        color: AppColors.champagne.withValues(alpha: 0.6),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Peer-Verified Deliverables • Cryptographic Trust',
                        style: TextStyle(
                          fontSize: 11,
                          color: AppColors.champagne.withValues(alpha: 0.6),
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'v1.0.0',
                    style: TextStyle(
                      fontSize: 10,
                      color: AppColors.champagne.withValues(alpha: 0.4),
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A custom widget rendering the solid #064E3B shield containing the #F8E7C9 checkmark.
class ShieldCheckMark extends StatelessWidget {
  final double size;

  const ShieldCheckMark({super.key, this.size = 100});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _ShieldCheckPainter(),
      ),
    );
  }
}

class _ShieldCheckPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final double s = size.width / 108.0;

    // Subtle ambient glow ring in Champagne
    final Paint glowPaint = Paint()
      ..color = AppColors.champagne.withValues(alpha: 0.12)
      ..style = PaintingStyle.fill;
    canvas.drawCircle(
      Offset(size.width / 2, size.height / 2),
      40 * s,
      glowPaint,
    );

    // Shield path (matching Android vector coordinates in 108x108 space)
    final Path shieldPath = Path()
      ..moveTo(33 * s, 26 * s)
      ..cubicTo(29 * s, 26 * s, 26 * s, 29 * s, 26 * s, 33 * s)
      ..lineTo(26 * s, 54 * s)
      ..cubicTo(26 * s, 67 * s, 38 * s, 78 * s, 54 * s, 84 * s)
      ..cubicTo(70 * s, 78 * s, 82 * s, 67 * s, 82 * s, 54 * s)
      ..lineTo(82 * s, 33 * s)
      ..cubicTo(82 * s, 29 * s, 79 * s, 26 * s, 75 * s, 26 * s)
      ..close();

    // Solid #064E3B shield fill
    final Paint shieldFill = Paint()
      ..color = AppColors.emeraldInk
      ..style = PaintingStyle.fill;
    canvas.drawPath(shieldPath, shieldFill);

    // Shield accent border: #F8E7C9
    final Paint shieldStroke = Paint()
      ..color = AppColors.champagne
      ..strokeWidth = 2.5 * s
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(shieldPath, shieldStroke);

    // Checkmark path: clean 45-degree checkmark (~50% width)
    // Start: (36, 54), Apex: (49, 67), End: (72, 44)
    final Path checkPath = Path()
      ..moveTo(36 * s, 54 * s)
      ..lineTo(49 * s, 67 * s)
      ..lineTo(72 * s, 44 * s);

    final Paint checkPaint = Paint()
      ..color = AppColors.champagne
      ..strokeWidth = 6.0 * s
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(checkPath, checkPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
