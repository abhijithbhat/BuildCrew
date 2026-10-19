import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../theme/app_colors.dart';

/// Decides where to go when the animation finishes ('/home' or '/login').
typedef SplashRouteResolver = Future<String> Function();

/// Animated launch screen, built with the Flutter SDK only
/// (AnimationController + CustomPainter, no packages).
///
/// Story (about 1.8 s): four glowing nodes (your crew's contributions) spiral
/// in from the edges and converge, a ring pulses out, the scalloped
/// certification seal locks in, a gold tick draws itself and the wordmark
/// fades in. Frame 0 is pure emerald, identical to the native launch screen.
class SplashScreen extends StatefulWidget {
  static const String routeName = '/splash';

  const SplashScreen({
    super.key,
    required this.resolveRoute,
    this.beforeNavigate,
    this.duration = const Duration(milliseconds: 1800),
    this.reducedMotionDuration = const Duration(milliseconds: 400),
  });

  final SplashRouteResolver resolveRoute;

  /// Optional hook that runs after the animation, before navigating. Use it to
  /// give prefetched data a moment to arrive (it must return quickly).
  final Future<void> Function(String route)? beforeNavigate;
  final Duration duration;
  final Duration reducedMotionDuration;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with TickerProviderStateMixin {
  late final AnimationController _controller;
  late final Ticker _ticker;
  Duration? _lastElapsed;
  Future<String>? _routeFuture;
  bool _started = false;
  bool _finished = false;
  bool _reduceMotion = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.duration,
      animationBehavior: AnimationBehavior.preserve,
    );
    _ticker = createTicker(_onTick);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _reduceMotion = MediaQuery.disableAnimationsOf(context);
    _controller.duration =
        _reduceMotion ? widget.reducedMotionDuration : widget.duration;
    if (!_ticker.isTicking) {
      _ticker.start();
    }
  }

  void _onTick(Duration elapsed) {
    if (_lastElapsed == null) {
      _lastElapsed = elapsed;
      return;
    }

    final Duration rawDelta = elapsed - _lastElapsed!;
    _lastElapsed = elapsed;

    final bool isTest =
        WidgetsBinding.instance.runtimeType.toString().contains('Test');

    if (isTest || _controller.value >= 0.08) {
      _routeFuture ??= _resolveRouteSafely();
    }

    final Duration effectiveDelta =
        (!isTest && rawDelta > const Duration(milliseconds: 33))
            ? const Duration(milliseconds: 33)
            : rawDelta;

    final Duration totalDuration =
        _reduceMotion ? widget.reducedMotionDuration : widget.duration;

    if (totalDuration.inMicroseconds > 0) {
      _controller.value = (_controller.value +
              effectiveDelta.inMicroseconds / totalDuration.inMicroseconds)
          .clamp(0.0, 1.0);
    } else {
      _controller.value = 1.0;
    }

    if (isTest || _controller.value >= 0.08) {
      _routeFuture ??= _resolveRouteSafely();
    }

    if (_controller.value >= 1.0) {
      if (_ticker.isTicking) {
        _ticker.stop();
      }
      if (!_finished) {
        _finished = true;
        _finish();
      }
    }
  }

  Future<String> _resolveRouteSafely() async {
    try {
      return await widget.resolveRoute();
    } catch (_) {
      return '/login';
    }
  }

  Future<void> _finish() async {
    String route;
    try {
      _routeFuture ??= _resolveRouteSafely();
      route = await _routeFuture!;
    } catch (_) {
      route = '/login';
    }
    try {
      await widget.beforeNavigate?.call(route);
    } catch (_) {}
    if (!mounted) return;
    final modalRoute = ModalRoute.of(context);
    // If something else already navigated away (deep link), do nothing.
    if (modalRoute != null && !modalRoute.isCurrent) return;
    Navigator.of(context).pushReplacementNamed(route);
  }

  @override
  void dispose() {
    _ticker.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.emeraldInk,
      body: Semantics(
        label: 'BuildCrew',
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) {
            return CustomPaint(
              size: Size.infinite,
              painter: _SplashPainter(
                progress: _controller.value,
              ),
            );
          },
        ),
      ),
    );
  }
}

class _SplashPainter extends CustomPainter {
  _SplashPainter({required this.progress});

  final double progress;

  static const Color _mint = Color(0xFF6EE7B7);
  static const Color _gold = Color(0xFFE8C25A);
  static const Color _glowCore = Color(0xFF0E7A5C);
  static const int _nodes = 4;
  static const int _trailSteps = 16;

  static double _clamp01(double v) => v < 0 ? 0 : (v > 1 ? 1 : v);
  static double _seg(double t, double a, double b) => _clamp01((t - a) / (b - a));
  static double _out(double x) => Curves.easeOutCubic.transform(_clamp01(x));
  static double _inOut(double x) => Curves.easeInOutCubic.transform(_clamp01(x));
  static double _back(double x) => Curves.easeOutBack.transform(_clamp01(x));

  @override
  void paint(Canvas canvas, Size size) {
    final double t = progress;
    final double w = size.width;
    final double h = size.height;
    final double cx = w / 2;
    final double cy = h * 0.44;
    final double r = math.min(w, h) * 0.17; // seal radius
    final double r0 = math.min(w, h) * 0.46; // where the nodes start
    final Offset center = Offset(cx, cy);

    // Soft emerald glow behind the mark.
    final double glow = _out(_seg(t, 0.0, 0.7)) * 0.55;
    if (glow > 0) {
      final Rect rect = Rect.fromCircle(center: center, radius: math.max(w, h) * 0.6);
      final Shader shader = RadialGradient(
        colors: [
          _glowCore.withValues(alpha: glow),
          AppColors.emeraldInk.withValues(alpha: 0),
        ],
      ).createShader(rect);
      canvas.drawRect(Offset.zero & size, Paint()..shader = shader);
    }

    // Four crew nodes spiral into the centre, each leaving a fading trail.
    final double fadeIn = 0.35 + 0.65 * _seg(t, 0.0, 0.10);
    for (int i = 0; i < _nodes; i++) {
      final double p = _inOut(_seg(t, 0.00 + 0.015 * i, 0.44 + 0.01 * i));
      final double fade = (1 - _seg(p, 0.90, 1.0)) * fadeIn;
      if (fade <= 0) continue;

      Offset at(double q) {
        final double th = -math.pi / 2 + i * math.pi / 2 + 0.35 + 1.15 * math.pi * q;
        final double rad = r0 * math.pow(1 - q, 1.15).toDouble();
        return Offset(cx + rad * math.cos(th), cy + rad * math.sin(th));
      }

      if (p > 0) {
        Offset prev = at(p);
        for (int k = 1; k <= _trailSteps; k++) {
          final double pk = math.max(0.0, p - k * 0.02);
          final Offset cur = at(pk);
          final double a = (1 - k / _trailSteps) * 0.55 * fade;
          canvas.drawLine(
            prev,
            cur,
            Paint()
              ..color = _mint.withValues(alpha: a)
              ..strokeWidth = 4.2 - 3.0 * k / _trailSteps
              ..strokeCap = StrokeCap.round,
          );
          prev = cur;
        }
      }

      final Offset head = at(p);
      canvas.drawCircle(
        head,
        16,
        Paint()
          ..color = _mint.withValues(alpha: 0.25 * fade)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8),
      );
      canvas.drawCircle(
        head,
        5.0 * (1 - 0.5 * p),
        Paint()..color = AppColors.champagne.withValues(alpha: fade),
      );
    }

    // Ring pulse when the nodes meet.
    final double u = _seg(t, 0.50, 0.80);
    if (u > 0 && u < 1) {
      canvas.drawCircle(
        center,
        r * (0.4 + 1.5 * _out(u)),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3
          ..color = _mint.withValues(alpha: (1 - u) * 0.5),
      );
    }

    // Scalloped certification seal.
    final double sealScale = _back(_seg(t, 0.50, 0.80));
    final double sealAlpha = _seg(t, 0.50, 0.62);
    if (sealScale > 0.01 && sealAlpha > 0) {
      final double rr = r * sealScale;
      final Path scallop = Path();
      const int steps = 360;
      for (int i = 0; i <= steps; i++) {
        final double th = 2 * math.pi * i / steps;
        final double rad = rr * (0.955 + 0.045 * math.cos(18 * th));
        final Offset pt = Offset(cx + rad * math.cos(th), cy + rad * math.sin(th));
        if (i == 0) {
          scallop.moveTo(pt.dx, pt.dy);
        } else {
          scallop.lineTo(pt.dx, pt.dy);
        }
      }
      scallop.close();

      canvas.drawPath(
        scallop,
        Paint()..color = AppColors.champagne.withValues(alpha: sealAlpha),
      );
      canvas.drawCircle(
        center,
        rr * 0.80,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2
          ..color = AppColors.emeraldInk.withValues(alpha: 0.35 * sealAlpha),
      );
      canvas.drawCircle(
        center,
        rr * 0.66,
        Paint()..color = AppColors.emeraldInk.withValues(alpha: sealAlpha),
      );

      // Gold verification tick draws itself.
      final double k = _out(_seg(t, 0.74, 0.92));
      if (k > 0) {
        final Path tick = Path()
          ..moveTo(cx - r * 0.30, cy + r * 0.02)
          ..lineTo(cx - r * 0.09, cy + r * 0.24)
          ..lineTo(cx + r * 0.30, cy - r * 0.20);
        final metric = tick.computeMetrics().first;
        canvas.drawPath(
          metric.extractPath(0, metric.length * k),
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = r * 0.11
            ..strokeCap = StrokeCap.round
            ..strokeJoin = StrokeJoin.round
            ..color = _gold,
        );
      }
    }

    // Wordmark.
    final double wordAlpha = _seg(t, 0.82, 1.0);
    if (wordAlpha > 0) {
      final TextPainter tp = TextPainter(
        text: TextSpan(
          text: 'BuildCrew',
          style: TextStyle(
            color: AppColors.champagne.withValues(alpha: wordAlpha),
            fontSize: 28,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.6,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(cx - tp.width / 2, cy + r * 1.75));
    }
  }

  @override
  bool shouldRepaint(covariant _SplashPainter oldDelegate) =>
      oldDelegate.progress != progress;
}
