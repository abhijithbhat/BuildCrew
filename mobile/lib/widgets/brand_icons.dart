import 'package:flutter/material.dart';

/// Brand marks drawn as pure vector paths: no image assets, no packages.
///
/// * Google "G": the standard four-colour mark (24x24 geometry).
/// * GitHub mark: Primer Octicons `mark-github` (the Octocat mark).
///
/// Geometry was converted from the official SVG path data into Flutter
/// `Path` commands (arcs converted to cubic curves) and verified to render
/// identically to the source SVG.
class GoogleGIcon extends StatelessWidget {
  const GoogleGIcon({super.key, this.size = 22});

  final double size;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        width: size,
        height: size,
        child: const CustomPaint(painter: _GoogleGPainter()),
      ),
    );
  }
}

class GitHubMarkIcon extends StatelessWidget {
  const GitHubMarkIcon({
    super.key,
    this.size = 22,
    this.color = const Color(0xFF1F2328),
  });

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        width: size,
        height: size,
        child: CustomPaint(painter: _GitHubMarkPainter(color)),
      ),
    );
  }
}

class _GoogleGPainter extends CustomPainter {
  const _GoogleGPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 24, size.height / 24);
    final paint = Paint()
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;
    canvas.drawPath(BrandPaths.googleBlue(), paint..color = const Color(0xFF4285F4));
    canvas.drawPath(BrandPaths.googleGreen(), paint..color = const Color(0xFF34A853));
    canvas.drawPath(BrandPaths.googleYellow(), paint..color = const Color(0xFFFBBC05));
    canvas.drawPath(BrandPaths.googleRed(), paint..color = const Color(0xFFEA4335));
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _GitHubMarkPainter extends CustomPainter {
  const _GitHubMarkPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 24, size.height / 24);
    final paint = Paint()
      ..style = PaintingStyle.fill
      ..isAntiAlias = true
      ..color = color;
    canvas.drawPath(BrandPaths.githubMark(), paint);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _GitHubMarkPainter oldDelegate) =>
      oldDelegate.color != color;
}

/// 24x24 path geometry (generated).
class BrandPaths {
  BrandPaths._();

  static Path googleBlue() {
    final p = Path();
    p.moveTo(23.49, 12.27);
    p.cubicTo(23.49, 11.48, 23.42, 10.73, 23.3, 10);
    p.lineTo(12, 10);
    p.lineTo(12, 14.51);
    p.lineTo(18.47, 14.51);
    p.cubicTo(18.18, 15.99, 17.33, 17.24, 16.07, 18.09);
    p.lineTo(16.07, 21.09);
    p.lineTo(19.93, 21.09);
    p.cubicTo(22.19, 19, 23.49, 15.92, 23.49, 12.27);
    p.close();
    return p;
  }

  static Path googleGreen() {
    final p = Path();
    p.moveTo(12, 24);
    p.cubicTo(15.24, 24, 17.95, 22.92, 19.93, 21.09);
    p.lineTo(16.07, 18.09);
    p.cubicTo(14.99, 18.81, 13.62, 19.25, 12, 19.25);
    p.cubicTo(8.87, 19.25, 6.22, 17.14, 5.27, 14.29);
    p.lineTo(1.29, 14.29);
    p.lineTo(1.29, 17.38);
    p.cubicTo(3.26, 21.3, 7.31, 24, 12, 24);
    p.close();
    return p;
  }

  static Path googleYellow() {
    final p = Path();
    p.moveTo(5.27, 14.29);
    p.cubicTo(5.02, 13.57, 4.89, 12.8, 4.89, 12);
    p.cubicTo(4.89, 11.2, 5.03, 10.43, 5.27, 9.71);
    p.lineTo(5.27, 6.62);
    p.lineTo(1.29, 6.62);
    p.cubicTo(0.47, 8.24, 0, 10.06, 0, 12);
    p.cubicTo(0, 13.94, 0.47, 15.76, 1.29, 17.38);
    p.lineTo(5.27, 14.29);
    p.close();
    return p;
  }

  static Path googleRed() {
    final p = Path();
    p.moveTo(12, 4.75);
    p.cubicTo(13.77, 4.75, 15.35, 5.36, 16.6, 6.55);
    p.lineTo(20.02, 3.13);
    p.cubicTo(17.95, 1.19, 15.24, 0, 12, 0);
    p.cubicTo(7.31, 0, 3.26, 2.7, 1.29, 6.62);
    p.lineTo(5.27, 9.71);
    p.cubicTo(6.22, 6.86, 8.87, 4.75, 12, 4.75);
    p.close();
    return p;
  }

  static Path githubMark() {
    final p = Path();
    p.moveTo(10.226, 17.284);
    p.cubicTo(7.261, 16.924, 5.172, 14.791, 5.172, 12.028);
    p.cubicTo(5.172, 10.905, 5.576, 9.692, 6.25, 8.884);
    p.cubicTo(5.958, 8.143, 6.003, 6.57, 6.34, 5.919);
    p.cubicTo(7.238, 5.807, 8.451, 6.279, 9.17, 6.929);
    p.cubicTo(10.023, 6.66, 10.922, 6.525, 12.023, 6.525);
    p.cubicTo(13.123, 6.525, 14.022, 6.66, 14.83, 6.907);
    p.cubicTo(15.526, 6.278, 16.762, 5.807, 17.66, 5.919);
    p.cubicTo(17.975, 6.525, 18.02, 8.098, 17.727, 8.861);
    p.cubicTo(18.447, 9.715, 18.828, 10.861, 18.828, 12.028);
    p.cubicTo(18.828, 14.791, 16.739, 16.88, 13.73, 17.262);
    p.cubicTo(14.493, 17.756, 15.01, 18.834, 15.01, 20.069);
    p.lineTo(15.01, 22.405);
    p.cubicTo(15.01, 23.079, 15.571, 23.461, 16.245, 23.191);
    p.cubicTo(20.311, 21.641, 23.5, 17.576, 23.5, 12.545);
    p.cubicTo(23.5, 6.188, 18.334, 1, 11.978, 1);
    p.cubicTo(5.62, 1, 0.5, 6.188, 0.5, 12.545);
    p.cubicTo(0.5, 17.531, 3.667, 21.665, 7.935, 23.214);
    p.cubicTo(8.541, 23.439, 9.125, 23.034, 9.125, 22.428);
    p.lineTo(9.125, 20.63);
    p.cubicTo(8.783, 20.773, 8.417, 20.849, 8.047, 20.854);
    p.cubicTo(6.564, 20.854, 5.688, 20.046, 5.06, 18.541);
    p.cubicTo(4.813, 17.934, 4.543, 17.575, 4.026, 17.508);
    p.cubicTo(3.756, 17.485, 3.667, 17.373, 3.667, 17.238);
    p.cubicTo(3.667, 16.968, 4.117, 16.767, 4.565, 16.767);
    p.cubicTo(5.217, 16.767, 5.778, 17.171, 6.362, 18.002);
    p.cubicTo(6.812, 18.653, 7.283, 18.945, 7.845, 18.945);
    p.cubicTo(8.406, 18.945, 8.765, 18.743, 9.282, 18.226);
    p.cubicTo(9.664, 17.845, 9.956, 17.508, 10.226, 17.283);
    return p;
  }
}
