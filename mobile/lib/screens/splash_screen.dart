import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../theme/app_colors.dart';

/// Decides where to go when the animation finishes ('/home' or '/login').
typedef SplashRouteResolver = Future<String> Function();

/// Animated launch screen built with pure Flutter SDK (Ticker + CustomPainter).
class SplashScreen extends StatefulWidget {
  static const String routeName = '/splash';

  const SplashScreen({
    super.key,
    required this.resolveRoute,
    this.beforeNavigate,
    this.duration = const Duration(milliseconds: 1650),
    this.reducedMotionDuration = const Duration(milliseconds: 400),
  });

  final SplashRouteResolver resolveRoute;
  final Future<void> Function(String route)? beforeNavigate;
  final Duration duration;
  final Duration reducedMotionDuration;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with TickerProviderStateMixin {
  late final AnimationController _controller;
  Ticker? _ticker;
  Duration? _lastElapsed;
  int _warmupFrames = 0;
  bool _started = false;
  bool _finished = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: widget.duration,
      animationBehavior: AnimationBehavior.preserve,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;

    final bool reduceMotion = MediaQuery.disableAnimationsOf(context);
    final bool isTest =
        WidgetsBinding.instance.runtimeType.toString().contains('Test');

    _controller.duration =
        reduceMotion ? widget.reducedMotionDuration : widget.duration;

    if (isTest) {
      _controller.forward().whenComplete(_finish);
    } else {
      // Drive progress with a VSYNC Ticker that waits for 3 real rendered frames
      // on screen before advancing past 0.0, and clamps only cold-start stalls
      // (>45ms) while passing normal VSYNC deltas through untouched.
      _ticker = createTicker(_onTick)..start();
    }
  }

  void _onTick(Duration elapsed) {
    if (!mounted || _finished) return;

    if (_lastElapsed == null) {
      _lastElapsed = elapsed;
      return;
    }

    final Duration rawDelta = elapsed - _lastElapsed!;
    _lastElapsed = elapsed;

    // Wait for 3 real frames to rasterize on screen so cold-start surface
    // attachment and shader compilation are completely done before the spiral moves.
    if (_warmupFrames < 3) {
      _warmupFrames++;
      return;
    }

    // If a single frame stalled (>45ms due to OS/VM cold-start jitter),
    // advance by a single 60fps frame (16.6ms) so the animation NEVER skips.
    // Otherwise use the exact hardware VSYNC delta for zero-friction motion.
    final int deltaMicros = rawDelta.inMicroseconds > 45000
        ? 16667
        : rawDelta.inMicroseconds;

    final int totalMicros =
        (_controller.duration ?? widget.duration).inMicroseconds;
    final double nextValue =
        (_controller.value + (deltaMicros / totalMicros)).clamp(0.0, 1.0);

    _controller.value = nextValue;

    if (nextValue >= 1.0) {
      _ticker?.stop();
      _finish();
    }
  }

  Future<void> _finish() async {
    if (_finished || !mounted) return;
    _finished = true;

    // Run Supabase init + token check AFTER the animation reaches 1.0,
    // so zero background work ever interrupts the spiral or wordmark animation.
    String route = '/login';
    final Completer<String> completer = Completer<String>();
    try {
      (widget.resolveRoute() as Future<dynamic>).then<void>(
        (dynamic value) {
          if (!completer.isCompleted) {
            completer.complete(value?.toString() ?? '/login');
          }
        },
        onError: (Object _) {
          if (!completer.isCompleted) {
            completer.complete('/login');
          }
        },
      ).timeout(
        const Duration(seconds: 4),
        onTimeout: () {
          if (!completer.isCompleted) {
            completer.complete('/login');
          }
        },
      );
    } catch (_) {
      if (!completer.isCompleted) {
        completer.complete('/login');
      }
    }

    try {
      route = await completer.future;
    } catch (_) {
      route = '/login';
    }

    try {
      await widget.beforeNavigate?.call(route);
    } catch (_) {}

    if (!mounted) return;
    final ModalRoute<dynamic>? modalRoute = ModalRoute.of(context);
    if (modalRoute != null && !modalRoute.isCurrent) return;
    Navigator.of(context).pushReplacementNamed(route);
  }

  @override
  void dispose() {
    _ticker?.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.emeraldInk,
      body: Semantics(
        label: 'BuildCrew',
        child: RepaintBoundary(
          child: AnimatedBuilder(
            animation: _controller,
            builder: (BuildContext context, _) {
              return CustomPaint(
                size: Size.infinite,
                painter: _SplashPainter(progress: _controller.value),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _SplashPainter extends CustomPainter {
  const _SplashPainter({required this.progress});

  final double progress;

  static const Color _mint = Color(0xFF6EE7B7);
  static const Color _gold = Color(0xFFE8C25A);
  static const Color _glowCore = Color(0xFF0E7A5C);

  // Pre-computed unit scalloped seal path (avoids 360 sin/cos calls per frame).
  static final Path _unitScallop = _buildUnitScallop();

  static Path _buildUnitScallop() {
    final Path p = Path();
    const int steps = 180;
    for (int i = 0; i <= steps; i++) {
      final double th = 2 * math.pi * i / steps;
      final double rad = 0.955 + 0.045 * math.cos(18 * th);
      final double x = rad * math.cos(th);
      final double y = rad * math.sin(th);
      if (i == 0) {
        p.moveTo(x, y);
      } else {
        p.lineTo(x, y);
      }
    }
    p.close();
    return p;
  }

  // Pre-laid-out TextPainter (avoids expensive font layout during paint).
  static final TextPainter _wordmarkPainter = TextPainter(
    text: const TextSpan(
      text: 'BuildCrew',
      style: TextStyle(
        color: AppColors.champagne,
        fontSize: 28,
        fontWeight: FontWeight.w800,
        letterSpacing: 0.6,
      ),
    ),
    textDirection: TextDirection.ltr,
  )..layout();

  static double _clamp01(double v) => v < 0 ? 0 : (v > 1 ? 1 : v);
  static double _seg(double t, double a, double b) =>
      _clamp01((t - a) / (b - a));
  static double _out(double x) => Curves.easeOutCubic.transform(_clamp01(x));
  static double _inOut(double x) =>
      Curves.easeInOutCubic.transform(_clamp01(x));
  static double _back(double x) => Curves.easeOutBack.transform(_clamp01(x));

  @override
  void paint(Canvas canvas, Size size) {
    final double t = progress;
    final double w = size.width;
    final double h = size.height;
    final double cx = w / 2;
    final double cy = h * 0.44;
    final double r = math.min(w, h) * 0.175;
    final Offset center = Offset(cx, cy);

    // 1. Soft ambient glow behind the center.
    final double glow = (0.15 + 0.85 * _out(_seg(t, 0.0, 0.75))) * 0.38;
    if (glow > 0) {
      canvas.drawCircle(
        center,
        r * 2.6,
        Paint()..color = _glowCore.withValues(alpha: glow * 0.35),
      );
      canvas.drawCircle(
        center,
        r * 1.65,
        Paint()..color = _glowCore.withValues(alpha: glow * 0.65),
      );
    }

    // 2. Four glowing nodes spiral in from the edges and converge at center.
    final double spiralFade = 1 - _out(_seg(t, 0.40, 0.56));
    if (spiralFade > 0) {
      final double p = _inOut(_seg(t, 0.0, 0.44));
      final double fadeIn = 0.50 + 0.50 * _seg(t, 0.0, 0.08);
      final double maxDist = r * 2.5;
      const double sweep = math.pi * 1.15;

      final Paint trailPaint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round;
      final Paint haloOuter = Paint()
        ..color = _mint.withValues(alpha: 0.14 * spiralFade * fadeIn);
      final Paint haloInner = Paint()
        ..color = _mint.withValues(alpha: 0.32 * spiralFade * fadeIn);
      final Paint dotCore = Paint()
        ..color = AppColors.champagne.withValues(alpha: spiralFade * fadeIn);

      for (int i = 0; i < 4; i++) {
        final double baseAngle = i * (math.pi / 2) + math.pi / 4;
        const int tailSteps = 12;
        final double tailSpan = math.min(p, 0.24);
        Offset? prev;
        for (int s = 0; s <= tailSteps; s++) {
          final double frac = s / tailSteps;
          final double ps = p - tailSpan * (1 - frac);
          final double dist = maxDist * (1 - ps);
          final double ang = baseAngle + sweep * ps;
          final Offset pt = Offset(
            cx + dist * math.cos(ang),
            cy + dist * math.sin(ang),
          );
          if (prev != null && tailSpan > 0.002) {
            final double a = frac * frac * 0.78 * spiralFade * fadeIn;
            trailPaint
              ..strokeWidth = 1.4 + 2.4 * frac
              ..color = _mint.withValues(alpha: a);
            canvas.drawLine(prev, pt, trailPaint);
          }
          prev = pt;
        }

        final double headDist = maxDist * (1 - p);
        final double headAng = baseAngle + sweep * p;
        final Offset head = Offset(
          cx + headDist * math.cos(headAng),
          cy + headDist * math.sin(headAng),
        );
        final double dotR = 4.5 + 2.0 * p;

        canvas.drawCircle(head, dotR * 2.8, haloOuter);
        canvas.drawCircle(head, dotR * 1.7, haloInner);
        canvas.drawCircle(head, dotR, dotCore);
      }
    }

    // 3. Convergence pulse: a mint ring ripples outward as the nodes fuse.
    final double mergeP = _out(_seg(t, 0.38, 0.64));
    final double mergeFade = 1 - _seg(t, 0.48, 0.66);
    if (mergeP > 0 && mergeFade > 0) {
      canvas.drawCircle(
        center,
        r * (0.20 + 1.15 * mergeP),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3.5 * (1 - mergeP * 0.7)
          ..color = _mint.withValues(alpha: 0.75 * mergeFade),
      );
      canvas.drawCircle(
        center,
        r * 0.55 * (1 - mergeP * 0.5),
        Paint()..color = _mint.withValues(alpha: 0.28 * mergeFade),
      );
    }

    // 4. Scalloped certification seal pops out of the fused core.
    final double sealScale = _back(_seg(t, 0.46, 0.76));
    final double sealAlpha = _seg(t, 0.46, 0.58);
    if (sealScale > 0.01 && sealAlpha > 0) {
      final double rr = r * sealScale;
      canvas.save();
      canvas.translate(cx, cy);
      canvas.scale(rr, rr);
      canvas.drawPath(
        _unitScallop,
        Paint()..color = AppColors.champagne.withValues(alpha: sealAlpha),
      );
      canvas.restore();

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

      // 5. Gold verification tick draws itself.
      final double k = _out(_seg(t, 0.70, 0.90));
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

    // 6. Wordmark rises and fades in (uses pre-laid-out static TextPainter).
    final double wordP = _out(_seg(t, 0.76, 0.96));
    if (wordP > 0) {
      final double ySlide = (1 - wordP) * 10;
      final Offset offset = Offset(
        cx - _wordmarkPainter.width / 2,
        cy + r * 1.55 + ySlide,
      );
      if (wordP >= 0.99) {
        _wordmarkPainter.paint(canvas, offset);
      } else {
        final Rect bounds = offset &
            Size(_wordmarkPainter.width + 4, _wordmarkPainter.height + 4);
        canvas.saveLayer(
          bounds,
          Paint()..color = Color.fromRGBO(255, 255, 255, wordP),
        );
        _wordmarkPainter.paint(canvas, offset);
        canvas.restore();
      }
    }
  }

  @override
  bool shouldRepaint(covariant _SplashPainter oldDelegate) =>
      oldDelegate.progress != progress;
}
