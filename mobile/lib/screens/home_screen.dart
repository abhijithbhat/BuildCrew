import 'package:flutter/material.dart';
import '../models/role_agreement.dart';
import '../services/auth_service.dart';
import '../services/health_service.dart';
import '../services/storage_service.dart';


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
      appBar: AppBar(
        title: const Text('Home'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
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
                  backgroundColor: Colors.blueAccent,
                  child: Icon(
                    Icons.person,
                    size: 48,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'Welcome, $displayName',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Colors.black87,
                      ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'You are successfully logged in.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: Colors.grey[600],
                      ),
                ),
                const SizedBox(height: 40),
                ElevatedButton.icon(
                  icon: const Icon(Icons.favorite),
                  label: const Text('Check Backend Health'),
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 24,
                      vertical: 12,
                    ),
                  ),
                  onPressed: () async {
                    try {
                      final result = await HealthService().checkHealth();
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            backgroundColor: Colors.green,
                            content:
                                Text('Backend Connected: ${result?["status"]}'),
                          ),
                        );
                      }
                    } catch (e) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            backgroundColor: Colors.red,
                            content: Text('Connection Failed: $e'),
                          ),
                        );
                      }
                    }
                  },
                ),
                const SizedBox(height: 12),
                ElevatedButton.icon(
                  icon: const Icon(Icons.folder_shared_outlined),
                  label: const Text('My Projects'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blueAccent,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 24,
                      vertical: 12,
                    ),
                  ),
                  onPressed: () =>
                      Navigator.pushNamed(context, '/projects'),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.group_add_outlined),
                  label: const Text('Join Project with Code'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 24,
                      vertical: 12,
                    ),
                  ),
                  onPressed: () =>
                      Navigator.pushNamed(context, '/join-project'),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.add_circle_outline),
                  label: const Text('Create New Project'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 24,
                      vertical: 12,
                    ),
                  ),
                  onPressed: () =>
                      Navigator.pushNamed(context, '/create-project'),
                ),
                const SizedBox(height: 24),
                TextButton.icon(
                  icon: const Icon(Icons.logout, color: Colors.red),
                  label: const Text(
                    'Logout',
                    style: TextStyle(color: Colors.red),
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
