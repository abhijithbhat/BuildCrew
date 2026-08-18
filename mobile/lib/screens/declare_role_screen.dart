import 'package:flutter/material.dart';
import '../models/project.dart';
import '../services/project_service.dart';

class DeclareRoleScreen extends StatefulWidget {
  static const String routeName = '/declare-role';

  final String? initialRole;
  final String? initialResponsibilities;
  final DateTime? initialDeadline;
  final String? projectId;
  final ProjectService? projectService;

  const DeclareRoleScreen({
    super.key,
    this.initialRole,
    this.initialResponsibilities,
    this.initialDeadline,
    this.projectId,
    this.projectService,
  });

  @override
  State<DeclareRoleScreen> createState() => _DeclareRoleScreenState();
}

class _DeclareRoleScreenState extends State<DeclareRoleScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _roleController;
  late final TextEditingController _responsibilitiesController;
  late final ProjectService _projectService;
  DateTime? _selectedDeadline;
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _roleController = TextEditingController(text: widget.initialRole ?? '');
    _responsibilitiesController =
        TextEditingController(text: widget.initialResponsibilities ?? '');
    _selectedDeadline = widget.initialDeadline;
  }

  bool _initializedFromArgs = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initializedFromArgs) {
      _initializedFromArgs = true;
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is Map<String, dynamic>) {
        if (_roleController.text.isEmpty && args['initialRole'] != null) {
          _roleController.text = args['initialRole'].toString();
        }
        if (_responsibilitiesController.text.isEmpty &&
            args['initialResponsibilities'] != null) {
          _responsibilitiesController.text =
              args['initialResponsibilities'].toString();
        }
        if (_selectedDeadline == null && args['initialDeadline'] != null) {
          if (args['initialDeadline'] is DateTime) {
            _selectedDeadline = args['initialDeadline'] as DateTime;
          } else {
            try {
              _selectedDeadline =
                  DateTime.parse(args['initialDeadline'].toString());
            } catch (_) {}
          }
        }
      }
    }
  }


  @override
  void dispose() {
    _roleController.dispose();
    _responsibilitiesController.dispose();
    super.dispose();
  }

  Future<void> _pickDeadline() async {
    final now = DateTime.now();
    final initialDate = _selectedDeadline ?? now.add(const Duration(days: 30));
    final picked = await showDatePicker(
      context: context,
      initialDate: initialDate.isAfter(now) ? initialDate : now,
      firstDate: now,
      lastDate: now.add(const Duration(days: 365 * 5)),
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.light(
              primary: Colors.blueAccent,
              onPrimary: Colors.white,
              onSurface: Colors.black87,
            ),
          ),
          child: child!,
        );
      },
    );

    if (picked != null) {
      setState(() {
        _selectedDeadline = picked;
      });
    }
  }

  void _clearDeadline() {
    setState(() {
      _selectedDeadline = null;
    });
  }

  String _formatDate(DateTime date) {
    const months = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec'
    ];
    return '${months[date.month - 1]} ${date.day}, ${date.year}';
  }

  bool get _isEditing =>
      widget.initialRole != null && widget.initialRole!.trim().isNotEmpty;

  Future<void> _handleFormSubmit() async {
    if (!_formKey.currentState!.validate()) return;

    String? projId = widget.projectId;
    if (projId == null || projId.isEmpty) {
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is Project) {
        projId = args.id;
      } else if (args is String) {
        projId = args;
      } else if (args is Map<String, dynamic>) {
        projId = args['projectId'] as String? ?? args['id'] as String?;
      }
    }

    if (projId == null || projId.isEmpty) {
      setState(() {
        _errorMessage = 'Project ID is required to declare a role.';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final result = await _projectService.declareRole(
        projectId: projId,
        declaredRole: _roleController.text.trim(),
        responsibilities: _responsibilitiesController.text.trim(),
        deadline: _selectedDeadline,
      );

      if (!mounted) return;

      final roleAgreement = result['role_agreement'] as Map<String, dynamic>?;
      final roleName =
          roleAgreement?['declared_role'] ?? _roleController.text.trim();

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _isEditing
                ? 'Successfully updated role "$roleName"!'
                : 'Successfully declared role "$roleName"!',
          ),
          backgroundColor: Colors.green.shade700,
          behavior: SnackBarBehavior.floating,
        ),
      );

      if (Navigator.canPop(context)) {
        Navigator.pop(context, result);
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
  Widget build(BuildContext context) {
    const hintStyle = TextStyle(
      color: Color(0xFFB0BEC5),
      fontSize: 13,
    );

    return Scaffold(
      backgroundColor: Colors.grey.shade50,
      appBar: AppBar(
        title: Text(
          _isEditing ? 'Update Your Role' : 'Declare Your Role',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 20.0),
            child: Form(
              key: _formKey,
              autovalidateMode: AutovalidateMode.disabled,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Top Hero Badge
                  Center(
                    child: Container(
                      width: 80,
                      height: 80,
                      decoration: BoxDecoration(
                        color: Colors.blue.withValues(alpha: 0.1),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        _isEditing
                            ? Icons.edit_note_rounded
                            : Icons.badge_outlined,
                        size: 42,
                        color: Colors.blueAccent,
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    _isEditing
                        ? 'Update Your Role Agreement'
                        : 'Declare Your Project Role',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: Colors.black87,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _isEditing
                        ? 'Modify your declared title, responsibilities, or milestone timeline.'
                        : 'Define your title, responsibilities, and target milestones to align with your crew.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey.shade600,
                      fontSize: 14,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 28),


                  // Error Message Banner
                  if (_errorMessage != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.red.shade50,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.red.shade200),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.error_outline,
                              color: Colors.red.shade700, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: TextStyle(
                                color: Colors.red.shade800,
                                fontSize: 13,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),
                  ],

                  // Role Title Input Card
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.grey.shade200),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'ROLE TITLE',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.1,
                            color: Colors.grey,
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextFormField(
                          controller: _roleController,
                          textInputAction: TextInputAction.next,
                          decoration: InputDecoration(
                            hintText: 'e.g., Lead Frontend Engineer, Backend Architect',
                            hintStyle: hintStyle,
                            prefixIcon: const Icon(Icons.work_outline_rounded),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 14,
                            ),
                          ),
                          validator: (val) {
                            if (val == null || val.trim().isEmpty) {
                              return 'Please enter your role title';
                            }
                            if (val.trim().length < 2) {
                              return 'Role title must be at least 2 characters';
                            }
                            return null;
                          },
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Responsibilities Text Area Card
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.grey.shade200),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'KEY RESPONSIBILITIES',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.1,
                            color: Colors.grey,
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextFormField(
                          controller: _responsibilitiesController,
                          minLines: 3,
                          maxLines: 5,
                          textInputAction: TextInputAction.newline,
                          decoration: InputDecoration(
                            hintText:
                                'Outline your core duties, deliverables, technical areas, or scope...',
                            hintStyle: hintStyle,
                            alignLabelWithHint: true,
                            prefixIcon: const Padding(
                              padding: EdgeInsets.only(bottom: 50.0),
                              child: Icon(Icons.assignment_outlined),
                            ),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 14,
                            ),
                          ),
                          validator: (val) {
                            if (val == null || val.trim().isEmpty) {
                              return 'Please enter your key responsibilities';
                            }
                            return null;
                          },
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Deadline Picker Card
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.grey.shade200),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text(
                              'TARGET DEADLINE',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 1.1,
                                color: Colors.grey,
                              ),
                            ),
                            Text(
                              'Optional',
                              style: TextStyle(
                                fontSize: 11,
                                color: Colors.grey.shade500,
                                fontStyle: FontStyle.italic,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        InkWell(
                          onTap: _pickDeadline,
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 14,
                            ),
                            decoration: BoxDecoration(
                              border: Border.all(color: Colors.grey.shade400),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.event_available_rounded,
                                  color: Colors.blueAccent,
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Text(
                                    _selectedDeadline != null
                                        ? _formatDate(_selectedDeadline!)
                                        : 'Select target completion deadline',
                                    style: _selectedDeadline != null
                                        ? const TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.w600,
                                            color: Colors.black87,
                                          )
                                        : hintStyle,
                                  ),
                                ),
                                if (_selectedDeadline != null)
                                  IconButton(
                                    icon: const Icon(Icons.close_rounded,
                                        size: 18, color: Colors.grey),
                                    onPressed: _clearDeadline,
                                    tooltip: 'Clear deadline',
                                    padding: EdgeInsets.zero,
                                    constraints: const BoxConstraints(),
                                  )
                                else
                                  const Icon(
                                    Icons.arrow_drop_down,
                                    color: Colors.grey,
                                  ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 32),

                  // Submit Action Button
                  ElevatedButton(
                    onPressed: _isLoading ? null : _handleFormSubmit,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blueAccent,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                      elevation: 2,
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor:
                                  AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                _isEditing
                                    ? Icons.check_circle_rounded
                                    : Icons.check_circle_outline_rounded,
                                size: 20,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                _isEditing
                                    ? 'Update Role Agreement'
                                    : 'Declare Role',
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
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
