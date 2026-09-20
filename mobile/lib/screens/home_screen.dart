import 'package:flutter/material.dart';
import '../models/role_agreement.dart';
import '../services/auth_service.dart';
import '../services/storage_service.dart';
import '../theme/app_colors.dart';

class HomeScreen extends StatefulWidget {
  static const String routeName = '/home';

  final String? userName;
  final StorageService? storageService;

  const HomeScreen({
    super.key,
    this.userName,
    this.storageService,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final StorageService _storageService;
  String? _storedUserName;

  @override
  void initState() {
    super.initState();
    _storageService = widget.storageService ?? StorageService();
    _loadStoredUserName();
  }

  Future<void> _loadStoredUserName() async {
    final name = await _storageService.getUserName();
    if (name != null && name.trim().isNotEmpty && mounted) {
      setState(() {
        _storedUserName = name.trim();
      });
    }
  }

  String _formatDisplayName(String input) {
    return RoleAgreement.formatEmailToHumanName(input);
  }

  @override
  Widget build(BuildContext context) {
    final routeArg = ModalRoute.of(context)?.settings.arguments as String?;
    final String rawInput = widget.userName ??
        _storedUserName ??
        routeArg ??
        'User';

    final String displayName = _formatDisplayName(rawInput);

    return Scaffold(
      backgroundColor: AppColors.champagne,
      appBar: AppBar(
        title: const Text(
          'Home',
          style: TextStyle(
            color: AppColors.emeraldInk,
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
        centerTitle: true,
        backgroundColor: AppColors.champagne,
        foregroundColor: AppColors.emeraldInk,
        elevation: 0,
        scrolledUnderElevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: AppColors.emeraldInk),
            tooltip: 'Logout',
            onPressed: () async {
              await AuthService(storageService: _storageService).logout();
              if (context.mounted) {
                Navigator.pushReplacementNamed(context, '/login');
              }
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const CircleAvatar(
                  radius: 40,
                  backgroundColor: AppColors.emeraldInk,
                  child: Icon(
                    Icons.person,
                    size: 48,
                    color: AppColors.champagne,
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'Welcome, $displayName',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: AppColors.emeraldInk,
                      ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'You are successfully logged in.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppColors.bodyText.withValues(alpha: 0.7),
                      ),
                ),
                const SizedBox(height: 40),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.folder_shared_outlined, color: AppColors.emeraldInk),
                    label: const Text(
                      'My Projects',
                      style: TextStyle(
                        color: AppColors.emeraldInk,
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: AppColors.emeraldInk,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 24,
                        vertical: 14,
                      ),
                      side: const BorderSide(color: AppColors.emeraldInk, width: 1.2),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    onPressed: () =>
                        Navigator.pushNamed(context, '/projects'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    key: const Key('home_pending_confirmations_btn'),
                    icon: const Icon(Icons.rate_review_outlined, color: AppColors.emeraldInk),
                    label: const Text(
                      'Pending Confirmations',
                      style: TextStyle(
                        color: AppColors.emeraldInk,
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: AppColors.emeraldInk,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 24,
                        vertical: 14,
                      ),
                      side: const BorderSide(color: AppColors.emeraldInk, width: 1.2),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    onPressed: () =>
                        Navigator.pushNamed(context, '/pending-confirmations'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.group_add_outlined, color: AppColors.emeraldInk),
                    label: const Text(
                      'Join Project with Code',
                      style: TextStyle(
                        color: AppColors.emeraldInk,
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: AppColors.emeraldInk,
                      side: const BorderSide(color: AppColors.emeraldInk, width: 1.2),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 24,
                        vertical: 14,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    onPressed: () =>
                        Navigator.pushNamed(context, '/join-project'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.add_circle_outline, color: AppColors.emeraldInk),
                    label: const Text(
                      'Create New Project',
                      style: TextStyle(
                        color: AppColors.emeraldInk,
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                    style: OutlinedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: AppColors.emeraldInk,
                      side: const BorderSide(color: AppColors.emeraldInk, width: 1.2),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 24,
                        vertical: 14,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    onPressed: () =>
                        Navigator.pushNamed(context, '/create-project'),
                  ),
                ),
                const SizedBox(height: 24),
                TextButton.icon(
                  icon: const Icon(Icons.logout, color: Color(0xFFDC2626)),
                  label: const Text(
                    'Logout',
                    style: TextStyle(
                      color: Color(0xFFDC2626),
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  onPressed: () async {
                    await AuthService(storageService: _storageService).logout();
                    if (context.mounted) {
                      Navigator.pushReplacementNamed(context, '/login');
                    }
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
