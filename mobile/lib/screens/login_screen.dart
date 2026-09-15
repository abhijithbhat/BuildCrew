import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../services/storage_service.dart';

class LoginScreen extends StatefulWidget {
  static const String routeName = '/login';

  final AuthService? authService;
  final StorageService? storageService;

  const LoginScreen({
    super.key,
    this.authService,
    this.storageService,
  });

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _emailController;
  late final TextEditingController _passwordController;
  late final AuthService _authService;

  bool _isPasswordVisible = false;
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _authService = widget.authService ?? AuthService();
    _emailController = TextEditingController();
    _passwordController = TextEditingController();
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final loginData = await _authService.login(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );
      if (mounted) {
        final user = loginData['user'] as Map<String, dynamic>?;
        final dName = (user?['display_name'] as String?) ??
            (user?['name'] as String?) ??
            (user?['full_name'] as String?);
        final arg = (dName != null && dName.trim().isNotEmpty)
            ? dName.trim()
            : _emailController.text.trim();

        // Clear navigation back-stack safely as per AGENTS.md rule 4
        Navigator.pushNamedAndRemoveUntil(
          context,
          '/home',
          (route) => false,
          arguments: arg,
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString();
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const hintStyle = TextStyle(
      color: Color(0xFFB0BEC5),
      fontSize: 13,
    );

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        title: const Text(
          'Login',
          style: TextStyle(
            color: Color(0xFF0F172A),
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 20.0),
            child: Form(
              key: _formKey,
              autovalidateMode: AutovalidateMode.disabled,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Brand Lock Icon Badge
                  Center(
                    child: Container(
                      width: 68,
                      height: 68,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            Color(0xFF4F46E5),
                            Color(0xFF6366F1),
                          ],
                        ),
                        borderRadius: BorderRadius.circular(20),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF6366F1).withValues(alpha: 0.35),
                            blurRadius: 18,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: const Icon(
                        Icons.lock_outline_rounded,
                        size: 32,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  // Header Text
                  const Text(
                    'Welcome Back',
                    style: TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.6,
                      color: Color(0xFF0F172A),
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Sign in to continue to BuildCrew',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w400,
                      color: Color(0xFF64748B),
                      letterSpacing: -0.1,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 32),
                  // Email Input Field
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    enabled: !_isLoading,
                    style: const TextStyle(
                      color: Color(0xFF0F172A),
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                    decoration: InputDecoration(
                      labelText: 'Email',
                      labelStyle: const TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                      floatingLabelStyle: const TextStyle(
                        color: Color(0xFF4F46E5),
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                      hintText: 'enter@example.com',
                      hintStyle: hintStyle,
                      prefixIcon: const Icon(
                        Icons.email_outlined,
                        color: Color(0xFF64748B),
                        size: 20,
                      ),
                      filled: true,
                      fillColor: Colors.white,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 16,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFE2E8F0),
                          width: 1.2,
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFE2E8F0),
                          width: 1.2,
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFF4F46E5),
                          width: 1.8,
                        ),
                      ),
                      errorBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFEF4444),
                          width: 1.2,
                        ),
                      ),
                      focusedErrorBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFDC2626),
                          width: 1.8,
                        ),
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Email is required';
                      }
                      final emailRegExp = RegExp(
                        r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$',
                      );
                      if (!emailRegExp.hasMatch(value.trim())) {
                        return 'Please enter a valid email address';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 18),
                  // Password Input Field
                  TextFormField(
                    controller: _passwordController,
                    obscureText: !_isPasswordVisible,
                    textInputAction: TextInputAction.done,
                    onFieldSubmitted: (_) => _isLoading ? null : _handleLogin(),
                    enabled: !_isLoading,
                    style: const TextStyle(
                      color: Color(0xFF0F172A),
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                    decoration: InputDecoration(
                      labelText: 'Password',
                      labelStyle: const TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                      floatingLabelStyle: const TextStyle(
                        color: Color(0xFF4F46E5),
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                      hintText: '••••••••',
                      hintStyle: hintStyle,
                      prefixIcon: const Icon(
                        Icons.lock_outline,
                        color: Color(0xFF64748B),
                        size: 20,
                      ),
                      suffixIcon: IconButton(
                        splashRadius: 20,
                        icon: Icon(
                          _isPasswordVisible
                              ? Icons.visibility_off
                              : Icons.visibility,
                          color: const Color(0xFF64748B),
                          size: 20,
                        ),
                        onPressed: () {
                          setState(() {
                            _isPasswordVisible = !_isPasswordVisible;
                          });
                        },
                      ),
                      filled: true,
                      fillColor: Colors.white,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 16,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFE2E8F0),
                          width: 1.2,
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFE2E8F0),
                          width: 1.2,
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFF4F46E5),
                          width: 1.8,
                        ),
                      ),
                      errorBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFEF4444),
                          width: 1.2,
                        ),
                      ),
                      focusedErrorBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: Color(0xFFDC2626),
                          width: 1.8,
                        ),
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Password is required';
                      }
                      if (value.length < 6) {
                        return 'Password must be at least 6 characters';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 6),
                  // Forgot Password Link
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton(
                      style: TextButton.styleFrom(
                        foregroundColor: const Color(0xFF4F46E5),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 4,
                          vertical: 4,
                        ),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                      onPressed: _isLoading
                          ? null
                          : () {
                              Navigator.pushNamed(context, '/forgot-password');
                            },
                      child: const Text(
                        'Forgot Password?',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          letterSpacing: -0.1,
                        ),
                      ),
                    ),
                  ),
                  // Error Alert Banner
                  if (_errorMessage != null)
                    Container(
                      margin: const EdgeInsets.only(top: 14),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEF2F2),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: const Color(0xFFFECACA),
                          width: 1,
                        ),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.error_outline_rounded,
                            color: Color(0xFFDC2626),
                            size: 20,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: const TextStyle(
                                color: Color(0xFF991B1B),
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                height: 1.3,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 24),
                  // Submit Login Button
                  ElevatedButton(
                    onPressed: _isLoading ? null : _handleLogin,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF4F46E5),
                      disabledBackgroundColor:
                          const Color(0xFF818CF8).withValues(alpha: 0.6),
                      foregroundColor: Colors.white,
                      elevation: 2,
                      shadowColor: const Color(0xFF4F46E5).withValues(alpha: 0.35),
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.2,
                              color: Colors.white,
                            ),
                          )
                        : const Text(
                            'Login',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.3,
                              color: Colors.white,
                            ),
                          ),
                  ),
                  const SizedBox(height: 20),
                  // Sign Up Footer Link
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Text(
                        "Don't have an account?",
                        style: TextStyle(
                          fontSize: 14,
                          color: Color(0xFF64748B),
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                      const SizedBox(width: 4),
                      TextButton(
                        style: TextButton.styleFrom(
                          foregroundColor: const Color(0xFF4F46E5),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 4,
                          ),
                          minimumSize: Size.zero,
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                        onPressed: _isLoading
                            ? null
                            : () {
                                Navigator.pushNamed(context, '/signup');
                              },
                        child: const Text(
                          'Sign Up',
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
