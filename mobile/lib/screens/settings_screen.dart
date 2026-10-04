import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/role_agreement.dart';
import '../services/api_client.dart';
import '../services/auth_service.dart';
import '../services/storage_service.dart';
import '../theme/app_colors.dart';
import '../utils/error_messages.dart';
import 'login_screen.dart';

class SettingsScreen extends StatefulWidget {
  static const String routeName = '/settings';

  final StorageService? storageService;
  final AuthService? authService;

  const SettingsScreen({
    super.key,
    this.storageService,
    this.authService,
  });

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final StorageService _storageService;
  late final AuthService _authService;

  String? _displayName;
  String? _email;
  bool _isLoading = true;
  bool _isDeleting = false;
  bool _pushNotificationsEnabled = false;

  static const String _privacyPolicyUrl =
      'https://github.com/abhijithbhat/BuildCrew/blob/main/PRIVACY.md';

  @override
  void initState() {
    super.initState();
    _storageService = widget.storageService ?? StorageService();
    _authService = widget.authService ?? AuthService(storageService: _storageService);
    _loadUserData();
  }

  Future<void> _loadUserData() async {
    final name = await _storageService.getUserName();
    final email = await _storageService.getUserEmail();
    if (mounted) {
      setState(() {
        _displayName = (name != null && name.trim().isNotEmpty) ? name.trim() : null;
        _email = (email != null && email.trim().isNotEmpty) ? email.trim() : null;
        _isLoading = false;
      });
    }
  }

  String _resolvedName() {
    if (_displayName != null && _displayName!.isNotEmpty) {
      return RoleAgreement.formatEmailToHumanName(_displayName!);
    }
    if (_email != null && _email!.isNotEmpty) {
      return RoleAgreement.formatEmailToHumanName(_email!);
    }
    return 'Developer';
  }

  Future<void> _handleLogout() async {
    final shouldLogout = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: AppColors.inputBorder, width: 1.2),
        ),
        title: const Text(
          'Log Out',
          style: TextStyle(
            color: AppColors.emeraldInk,
            fontWeight: FontWeight.w700,
            fontSize: 18,
          ),
        ),
        content: const Text(
          'Are you sure you want to log out of BuildCrew?',
          style: TextStyle(
            color: AppColors.bodyText,
            fontSize: 14,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text(
              'Cancel',
              style: TextStyle(
                color: AppColors.emeraldInk,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.emeraldInk,
              foregroundColor: AppColors.champagne,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Log Out'),
          ),
        ],
      ),
    );

    if (shouldLogout == true && mounted) {
      await _authService.logout();
      if (mounted) {
        Navigator.of(context).pushNamedAndRemoveUntil(
          LoginScreen.routeName,
          (route) => false,
        );
      }
    }
  }

  Future<void> _handleDeleteAccount() async {
    final shouldDelete = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: AppColors.inputBorder, width: 1.2),
        ),
        title: const Text(
          'Delete Account Permanently?',
          style: TextStyle(
            color: AppColors.emeraldInk,
            fontWeight: FontWeight.w700,
            fontSize: 18,
          ),
        ),
        content: const Text(
          'Your account, contributions and uploaded files will be permanently deleted.',
          style: TextStyle(
            color: AppColors.bodyText,
            fontSize: 14,
            height: 1.4,
          ),
        ),
        actions: [
          OutlinedButton(
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.emeraldInk,
              side: const BorderSide(color: AppColors.inputBorder),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text(
              'Cancel',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red.shade700,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete Forever'),
          ),
        ],
      ),
    );

    if (shouldDelete == true && mounted) {
      setState(() {
        _isDeleting = true;
      });

      try {
        await _authService.deleteAccount();
        if (mounted) {
          ApiClient.scaffoldMessengerKey.currentState?.showSnackBar(
            SnackBar(
              content: const Text(
                'Account deleted successfully',
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
              ),
              backgroundColor: AppColors.emeraldInk,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          );
          Navigator.of(context).pushNamedAndRemoveUntil(
            '/login',
            (route) => false,
          );
        }
      } catch (e) {
        if (mounted) {
          setState(() {
            _isDeleting = false;
          });
          final errorMsg = friendlyError(e);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                errorMsg.startsWith('Failed to delete') || errorMsg.startsWith('Cannot connect')
                    ? errorMsg
                    : 'Failed to delete account: $errorMsg',
              ),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          );
        }
      }
    }
  }

  Future<void> _openPrivacyPolicy() async {
    final uri = Uri.parse(_privacyPolicyUrl);
    try {
      final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        _showPrivacyPolicyModal();
      }
    } catch (_) {
      if (mounted) {
        _showPrivacyPolicyModal();
      }
    }
  }

  void _showPrivacyPolicyModal() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.privacy_tip_outlined, color: AppColors.emeraldInk, size: 24),
                const SizedBox(width: 10),
                const Text(
                  'Privacy Policy',
                  style: TextStyle(
                    color: AppColors.emeraldInk,
                    fontWeight: FontWeight.w700,
                    fontSize: 18,
                  ),
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.close, color: AppColors.bodyText),
                  onPressed: () => Navigator.of(ctx).pop(),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              'BuildCrew respects developer privacy. Your email, name, and GitHub handles are stored '
              'solely for authentication, role tracking, and verifiable contribution logs. '
              'We never sell your data or share code repository contents without authorization.\n\n'
              'You can request complete account and data removal at any time using the "Delete My Account" action.',
              style: TextStyle(
                color: AppColors.bodyText,
                fontSize: 14,
                height: 1.45,
              ),
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.emeraldInk,
                  foregroundColor: AppColors.champagne,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('Understood'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final name = _resolvedName();
    final email = _email ?? 'No email associated';

    return Scaffold(
      backgroundColor: AppColors.champagne,
      appBar: AppBar(
        title: const Text(
          'Settings',
          style: TextStyle(
            color: AppColors.emeraldInk,
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
        centerTitle: true,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: AppColors.champagne,
        foregroundColor: AppColors.emeraldInk,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(
            color: AppColors.inputBorder,
            height: 1.0,
          ),
        ),
      ),
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.emeraldInk),
            )
          : _isDeleting
              ? const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      CircularProgressIndicator(color: AppColors.emeraldInk),
                      SizedBox(height: 16),
                      Text(
                        'Deleting account and data...',
                        style: TextStyle(
                          color: AppColors.emeraldInk,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                )
              : SafeArea(
                  child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 20.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Section 1: Account
                    _buildSectionHeader('Account'),
                    const SizedBox(height: 8),
                    Material(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      clipBehavior: Clip.antiAlias,
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppColors.inputBorder, width: 1.2),
                        ),
                        child: Column(
                        children: [
                          ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            leading: CircleAvatar(
                              radius: 24,
                              backgroundColor: AppColors.emeraldInk,
                              child: Text(
                                name.isNotEmpty ? name[0].toUpperCase() : 'U',
                                style: const TextStyle(
                                  color: AppColors.champagne,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 18,
                                ),
                              ),
                            ),
                            title: Text(
                              name,
                              style: const TextStyle(
                                color: AppColors.emeraldInk,
                                fontWeight: FontWeight.w700,
                                fontSize: 16,
                              ),
                            ),
                            subtitle: Text(
                              email,
                              style: TextStyle(
                                color: AppColors.bodyText.withValues(alpha: 0.7),
                                fontSize: 13,
                              ),
                            ),
                          ),
                          const Divider(height: 1, color: AppColors.inputBorder),
                          ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            leading: Icon(
                              Icons.delete_forever_outlined,
                              color: Colors.red.shade700,
                            ),
                            title: Text(
                              'Delete My Account',
                              style: TextStyle(
                                color: Colors.red.shade700,
                                fontWeight: FontWeight.w600,
                                fontSize: 14,
                              ),
                            ),
                            subtitle: const Text(
                              'Permanently remove account & data (Play Store)',
                              style: TextStyle(
                                fontSize: 12,
                                color: AppColors.bodyText,
                              ),
                            ),
                            trailing: Icon(
                              Icons.arrow_forward_ios_rounded,
                              size: 14,
                              color: Colors.red.shade700,
                            ),
                            onTap: _handleDeleteAccount,
                          ),
                        ],
                      ),
                    ),
                    ),

                    const SizedBox(height: 24),

                    // Section 2: Notifications
                    _buildSectionHeader('Notifications'),
                    const SizedBox(height: 8),
                    Container(
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: AppColors.inputBorder, width: 1.2),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: AppColors.emeraldInk.withValues(alpha: 0.08),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: const Icon(
                              Icons.notifications_outlined,
                              color: AppColors.emeraldInk,
                              size: 22,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Wrap(
                                  crossAxisAlignment: WrapCrossAlignment.center,
                                  spacing: 6,
                                  runSpacing: 4,
                                  children: [
                                    const Text(
                                      'Push Notifications',
                                      style: TextStyle(
                                        color: AppColors.emeraldInk,
                                        fontWeight: FontWeight.w600,
                                        fontSize: 14,
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: AppColors.emeraldInk.withValues(alpha: 0.1),
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: const Text(
                                        'Coming Soon',
                                        style: TextStyle(
                                          color: AppColors.emeraldInk,
                                          fontSize: 10,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Alerts for peer reviews and role updates',
                                  style: TextStyle(
                                    color: AppColors.bodyText.withValues(alpha: 0.65),
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          Switch(
                            value: _pushNotificationsEnabled,
                            activeThumbColor: AppColors.emeraldInk,
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            onChanged: (val) {
                              if (val) {
                                setState(() {
                                  _pushNotificationsEnabled = false;
                                });
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                        'Push notifications will be available in an upcoming update.'),
                                    behavior: SnackBarBehavior.floating,
                                    duration: Duration(seconds: 2),
                                  ),
                                );
                              }
                            },
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 24),

                    // Section 3: App Info
                    _buildSectionHeader('App Info'),
                    const SizedBox(height: 8),
                    Material(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      clipBehavior: Clip.antiAlias,
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppColors.inputBorder, width: 1.2),
                        ),
                        child: Column(
                        children: [
                          ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            leading: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: AppColors.emeraldInk.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: const Icon(
                                Icons.info_outline,
                                color: AppColors.emeraldInk,
                                size: 22,
                              ),
                            ),
                            title: const Text(
                              'Version',
                              style: TextStyle(
                                color: AppColors.emeraldInk,
                                fontWeight: FontWeight.w600,
                                fontSize: 14,
                              ),
                            ),
                            trailing: const Text(
                              '1.0.0 (Build 1)',
                              style: TextStyle(
                                color: AppColors.bodyText,
                                fontWeight: FontWeight.w600,
                                fontSize: 13,
                              ),
                            ),
                          ),
                          const Divider(height: 1, color: AppColors.inputBorder),
                          ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            leading: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: AppColors.emeraldInk.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: const Icon(
                                Icons.privacy_tip_outlined,
                                color: AppColors.emeraldInk,
                                size: 22,
                              ),
                            ),
                            title: const Text(
                              'Privacy Policy',
                              style: TextStyle(
                                color: AppColors.emeraldInk,
                                fontWeight: FontWeight.w600,
                                fontSize: 14,
                              ),
                            ),
                            subtitle: Text(
                              'Read our data & privacy policy',
                              style: TextStyle(
                                color: AppColors.bodyText.withValues(alpha: 0.65),
                                fontSize: 12,
                              ),
                            ),
                            trailing: const Icon(
                              Icons.open_in_new_rounded,
                              size: 16,
                              color: AppColors.emeraldInk,
                            ),
                            onTap: _openPrivacyPolicy,
                          ),
                        ],
                      ),
                    ),
                    ),

                    const SizedBox(height: 32),

                    // Section 4: Single Logout Action
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        key: const Key('settings_logout_btn'),
                        icon: const Icon(Icons.logout_rounded, color: AppColors.emeraldInk),
                        label: const Text(
                          'Log Out',
                          style: TextStyle(
                            color: AppColors.emeraldInk,
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                        ),
                        style: OutlinedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: AppColors.emeraldInk,
                          side: const BorderSide(color: AppColors.emeraldInk, width: 1.5),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                          ),
                        ),
                        onPressed: _handleLogout,
                      ),
                    ),
                    const SizedBox(height: 20),
                  ],
                ),
              ),
            ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0),
      child: Text(
        title.toUpperCase(),
        style: const TextStyle(
          color: AppColors.emeraldInk,
          fontWeight: FontWeight.w700,
          fontSize: 12,
          letterSpacing: 0.8,
        ),
      ),
    );
  }
}
