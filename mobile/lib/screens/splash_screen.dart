import 'package:flutter/material.dart';

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
      backgroundColor: const Color(0xFF0F172A),
      body: SafeArea(
        child: Stack(
          children: [
            // Ambient Radial Glow in the background
            Positioned(
              top: -60,
              right: -60,
              child: Container(
                width: 240,
                height: 240,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF4F46E5).withValues(alpha: 0.12),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF4F46E5).withValues(alpha: 0.12),
                      blurRadius: 100,
                      spreadRadius: 40,
                    ),
                  ],
                ),
              ),
            ),
            Positioned(
              bottom: -40,
              left: -40,
              child: Container(
                width: 200,
                height: 200,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF6366F1).withValues(alpha: 0.08),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF6366F1).withValues(alpha: 0.08),
                      blurRadius: 90,
                      spreadRadius: 30,
                    ),
                  ],
                ),
              ),
            ),

            // Main Centered Brand Content
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Brand Logo Emblem Container
                    Container(
                      width: 92,
                      height: 92,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            Color(0xFF1E293B),
                            Color(0xFF0F172A),
                          ],
                        ),
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: const Color(0xFF6366F1).withValues(alpha: 0.4),
                          width: 1.8,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF4F46E5).withValues(alpha: 0.25),
                            blurRadius: 28,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      child: Center(
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            Container(
                              width: 54,
                              height: 54,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: const Color(0xFF4F46E5).withValues(alpha: 0.25),
                              ),
                            ),
                            const Icon(
                              Icons.groups_rounded,
                              size: 46,
                              color: Color(0xFF818CF8),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),

                    // App Title
                    const Text(
                      'BuildCrew',
                      style: TextStyle(
                        fontSize: 30,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                        letterSpacing: -0.6,
                      ),
                    ),
                    const SizedBox(height: 6),

                    // Tagline Badge
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFF6366F1).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: const Color(0xFF6366F1).withValues(alpha: 0.25),
                          width: 1,
                        ),
                      ),
                      child: const Text(
                        'AUTONOMOUS WORKSPACE',
                        style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFFA5B4FC),
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
                            AlwaysStoppedAnimation<Color>(Color(0xFF6366F1)),
                      ),
                    ),
                    const SizedBox(height: 14),

                    // Status Message
                    Text(
                      message ?? 'Initializing workspace...',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF64748B),
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
                      const Icon(
                        Icons.shield_outlined,
                        size: 13,
                        color: Color(0xFF475569),
                      ),
                      const SizedBox(width: 6),
                      const Text(
                        'Peer-Verified Deliverables • Cryptographic Trust',
                        style: TextStyle(
                          fontSize: 11,
                          color: Color(0xFF475569),
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'v1.0.0',
                    style: TextStyle(
                      fontSize: 10,
                      color: Color(0xFF334155),
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
