import 'package:flutter/material.dart';
import '../models/project.dart';
import '../services/project_service.dart';
import '../theme/app_colors.dart';

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
              primary: AppColors.emeraldInk,
              onPrimary: Colors.white,
              onSurface: AppColors.emeraldInk,
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
          backgroundColor: const Color(0xFF10B981),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
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
      backgroundColor: AppColors.champagne,
      appBar: AppBar(
        title: Text(
          _isEditing ? 'Update Your Role' : 'Declare Your Role',
          style: const TextStyle(
            color: AppColors.emeraldInk,
            fontSize: 18,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
          ),
        ),
        centerTitle: true,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: Colors.transparent,
        foregroundColor: AppColors.emeraldInk,
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
                      width: 68,
                      height: 68,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            AppColors.emeraldInk,
                            AppColors.emeraldInk,
                          ],
                        ),
                        borderRadius: BorderRadius.circular(20),
                        boxShadow: [
                          BoxShadow(
                            color: AppColors.emeraldInk.withValues(alpha: 0.35),
                            blurRadius: 18,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: Icon(
                        _isEditing
                            ? Icons.edit_note_rounded
                            : Icons.badge_outlined,
                        size: 32,
                        color: AppColors.champagne,
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    _isEditing
                        ? 'Update Your Role Agreement'
                        : 'Declare Your Project Role',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.6,
                      color: AppColors.emeraldInk,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _isEditing
                        ? 'Modify your declared title, responsibilities, or milestone timeline.'
                        : 'Define your title, responsibilities, and target milestones to align with your crew.',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Color(0xFF64748B),
                      fontSize: 14,
                      letterSpacing: -0.1,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 28),

                  // Error Message Banner
                  if (_errorMessage != null) ...[
                    Container(
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
                    const SizedBox(height: 20),
                  ],

                  // Role Title Input Card
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: const Color(0xFFE2E8F0),
                        width: 1.2,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.emeraldInk.withValues(alpha: 0.04),
                          blurRadius: 16,
                          offset: const Offset(0, 4),
                        ),
                      ],
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
                            color: Color(0xFF64748B),
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextFormField(
                          controller: _roleController,
                          textInputAction: TextInputAction.next,
                          enabled: !_isLoading,
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                            color: AppColors.emeraldInk,
                          ),
                          decoration: InputDecoration(
                            hintText:
                                'e.g., Lead Frontend Engineer, Backend Architect',
                            hintStyle: hintStyle,
                            prefixIcon: const Icon(
                              Icons.work_outline_rounded,
                              color: Color(0xFF64748B),
                              size: 20,
                            ),
                            filled: true,
                            fillColor: AppColors.champagne,
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 16,
                            ),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFE2E8F0),
                                width: 1.2,
                              ),
                            ),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFE2E8F0),
                                width: 1.2,
                              ),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: AppColors.emeraldInk,
                                width: 1.8,
                              ),
                            ),
                            errorBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFEF4444),
                                width: 1.2,
                              ),
                            ),
                            focusedErrorBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFDC2626),
                                width: 1.8,
                              ),
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
                  const SizedBox(height: 18),

                  // Responsibilities Text Area Card
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: const Color(0xFFE2E8F0),
                        width: 1.2,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.emeraldInk.withValues(alpha: 0.04),
                          blurRadius: 16,
                          offset: const Offset(0, 4),
                        ),
                      ],
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
                            color: Color(0xFF64748B),
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextFormField(
                          controller: _responsibilitiesController,
                          minLines: 3,
                          maxLines: 5,
                          textInputAction: TextInputAction.newline,
                          enabled: !_isLoading,
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            color: AppColors.emeraldInk,
                            height: 1.45,
                          ),
                          decoration: InputDecoration(
                            hintText:
                                'Outline your core duties, deliverables, technical areas, or scope...',
                            hintStyle: hintStyle,
                            alignLabelWithHint: true,
                            prefixIcon: const Padding(
                              padding: EdgeInsets.only(bottom: 50.0),
                              child: Icon(
                                Icons.assignment_outlined,
                                color: Color(0xFF64748B),
                                size: 20,
                              ),
                            ),
                            filled: true,
                            fillColor: AppColors.champagne,
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 16,
                            ),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFE2E8F0),
                                width: 1.2,
                              ),
                            ),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFE2E8F0),
                                width: 1.2,
                              ),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: AppColors.emeraldInk,
                                width: 1.8,
                              ),
                            ),
                            errorBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFEF4444),
                                width: 1.2,
                              ),
                            ),
                            focusedErrorBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(
                                color: Color(0xFFDC2626),
                                width: 1.8,
                              ),
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
                  const SizedBox(height: 18),

                  // Deadline Picker Card
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: const Color(0xFFE2E8F0),
                        width: 1.2,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.emeraldInk.withValues(alpha: 0.04),
                          blurRadius: 16,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: const [
                            Text(
                              'TARGET DEADLINE',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 1.1,
                                color: Color(0xFF64748B),
                              ),
                            ),
                            Text(
                              'Optional',
                              style: TextStyle(
                                fontSize: 11,
                                color: Color(0xFF94A3B8),
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
                              color: AppColors.champagne,
                              border: Border.all(
                                color: const Color(0xFFE2E8F0),
                                width: 1.2,
                              ),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.event_available_rounded,
                                  color: AppColors.emeraldInk,
                                  size: 20,
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
                                            color: AppColors.emeraldInk,
                                          )
                                        : hintStyle,
                                  ),
                                ),
                                if (_selectedDeadline != null)
                                  IconButton(
                                    icon: const Icon(
                                      Icons.close_rounded,
                                      size: 18,
                                      color: Color(0xFF64748B),
                                    ),
                                    onPressed: _clearDeadline,
                                    tooltip: 'Clear deadline',
                                    padding: EdgeInsets.zero,
                                    constraints: const BoxConstraints(),
                                  )
                                else
                                  const Icon(
                                    Icons.arrow_drop_down,
                                    color: Color(0xFF64748B),
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
                      backgroundColor: AppColors.emeraldInk,
                      disabledBackgroundColor:
                          AppColors.emeraldInk.withValues(alpha: 0.6),
                      foregroundColor: AppColors.champagne,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                      elevation: 2,
                      shadowColor: AppColors.emeraldInk.withValues(alpha: 0.35),
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.2,
                              valueColor:
                                  AlwaysStoppedAnimation<Color>(AppColors.champagne),
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
                                  fontSize: 15,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: 0.3,
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
