import 'package:flutter/material.dart';
import '../models/contribution.dart';
import '../models/role_agreement.dart';
import '../services/project_service.dart';
import '../theme/app_colors.dart';

class RequestConfirmationModal {
  static Future<void> show({
    required BuildContext context,
    required Contribution contribution,
    required String projectId,
    required ProjectService projectService,
    String? currentUserId,
    required VoidCallback onSuccess,
  }) async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF0F172A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetContext) {
        return RequestConfirmationModalContent(
          contribution: contribution,
          projectId: projectId,
          projectService: projectService,
          currentUserId: currentUserId,
          onSuccess: onSuccess,
        );
      },
    );
  }
}

class RequestConfirmationModalContent extends StatefulWidget {
  final Contribution contribution;
  final String projectId;
  final ProjectService projectService;
  final String? currentUserId;
  final VoidCallback onSuccess;

  const RequestConfirmationModalContent({
    super.key,
    required this.contribution,
    required this.projectId,
    required this.projectService,
    required this.currentUserId,
    required this.onSuccess,
  });

  @override
  State<RequestConfirmationModalContent> createState() =>
      _RequestConfirmationModalContentState();
}

class _RequestConfirmationModalContentState
    extends State<RequestConfirmationModalContent> {
  bool _isLoading = true;
  String? _fetchError;
  List<RoleAgreement> _teammates = [];
  final Set<String> _selectedReviewerIds = {};
  bool _isSubmitting = false;
  String? _submitError;

  @override
  void initState() {
    super.initState();
    _loadTeammates();
  }

  Future<void> _loadTeammates() async {
    setState(() {
      _isLoading = true;
      _fetchError = null;
    });

    try {
      final rawRoles =
          await widget.projectService.listProjectRoles(widget.projectId);
      final parsed = rawRoles
          .map((r) => RoleAgreement.fromJson(r))
          .where((r) => r.userId.isNotEmpty && r.userId != widget.currentUserId)
          .toList();

      if (!mounted) return;
      setState(() {
        _teammates = parsed;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _fetchError = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _submitRequest() async {
    if (_selectedReviewerIds.isEmpty) {
      setState(() {
        _submitError =
            'Please select at least one teammate to request confirmation.';
      });
      return;
    }

    setState(() {
      _isSubmitting = true;
      _submitError = null;
    });

    try {
      await widget.projectService.requestConfirmation(
        contributionId: widget.contribution.id,
        reviewerIds: _selectedReviewerIds.toList(),
      );

      if (!mounted) return;
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.check_circle_rounded,
                  color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Confirmation requested from ${_selectedReviewerIds.length} teammate(s)!',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          backgroundColor: const Color(0xFF10B981),
          behavior: SnackBarBehavior.floating,
        ),
      );
      widget.onSuccess();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _submitError = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 12,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Drag handle
            Center(
              child: Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: Colors.grey.shade700,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),

            // Header Row
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: AppColors.emeraldInk.withValues(alpha: 0.15),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.how_to_reg_outlined,
                    color: AppColors.champagne,
                    size: 24,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Request Confirmation',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Ask teammates to verify "${widget.contribution.title}"',
                        style: const TextStyle(
                          color: Color(0xFF94A3B8),
                          fontSize: 12,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close_rounded, color: Colors.white70),
                  onPressed: () => Navigator.pop(context),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Error banner if any
            if (_submitError != null) ...[
              Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.withAlpha(30),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Colors.red.withAlpha(80)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline_rounded,
                        color: Colors.redAccent, size: 20),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _submitError!,
                        style: const TextStyle(
                            color: Colors.redAccent, fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // Content section
            if (_isLoading) ...[
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 40),
                child: Center(
                  child: Column(
                    children: [
                      CircularProgressIndicator(
                        color: AppColors.emeraldInk,
                        strokeWidth: 2.5,
                      ),
                      SizedBox(height: 12),
                      Text(
                        'Loading project teammates...',
                        style:
                            TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                      ),
                    ],
                  ),
                ),
              ),
            ] else if (_fetchError != null) ...[
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Column(
                  children: [
                    Text(
                      'Failed to load teammates: $_fetchError',
                      style: const TextStyle(
                          color: Colors.redAccent, fontSize: 13),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 12),
                    ElevatedButton(
                      onPressed: _loadTeammates,
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            ] else if (_teammates.isEmpty) ...[
              Container(
                padding: const EdgeInsets.all(24),
                alignment: Alignment.center,
                child: const Column(
                  children: [
                    Icon(Icons.group_off_outlined,
                        color: Colors.white38, size: 40),
                    SizedBox(height: 12),
                    Text(
                      'No other teammates found',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.bold),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'You are the only member in this project. Invite teammates first to request peer confirmations.',
                      style:
                          TextStyle(color: Color(0xFF94A3B8), fontSize: 12),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ] else ...[
              // Select all row
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Teammates (${_selectedReviewerIds.length}/${_teammates.length} selected)',
                    style: const TextStyle(
                      color: Color(0xFF94A3B8),
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  TextButton(
                    onPressed: () {
                      setState(() {
                        if (_selectedReviewerIds.length == _teammates.length) {
                          _selectedReviewerIds.clear();
                        } else {
                          _selectedReviewerIds
                              .addAll(_teammates.map((t) => t.userId));
                        }
                      });
                    },
                    child: Text(
                      _selectedReviewerIds.length == _teammates.length
                          ? 'Deselect All'
                          : 'Select All',
                      style: const TextStyle(
                        color: AppColors.emeraldInk,
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),

              // Teammates scroll list
              ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(context).size.height * 0.35,
                ),
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: _teammates.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 6),
                  itemBuilder: (ctx, index) {
                    final member = _teammates[index];
                    final isSelected =
                        _selectedReviewerIds.contains(member.userId);
                    final displayName = member.profile?['display_name'] ??
                        RoleAgreement.formatEmailToHumanName(
                            member.profile?['email'] ?? member.userId);
                    final initial = displayName.isNotEmpty
                        ? displayName[0].toUpperCase()
                        : 'M';

                    return InkWell(
                      key: Key('reviewer_checkbox_${member.userId}'),
                      onTap: () {
                        setState(() {
                          if (isSelected) {
                            _selectedReviewerIds.remove(member.userId);
                          } else {
                            _selectedReviewerIds.add(member.userId);
                          }
                        });
                      },
                      borderRadius: BorderRadius.circular(10),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 10),
                        decoration: BoxDecoration(
                          color: isSelected
                              ? AppColors.emeraldInk.withValues(alpha: 0.2)
                              : const Color(0xFF1E293B),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: isSelected
                                ? AppColors.emeraldInk
                                : const Color(0xFF334155),
                            width: 1.2,
                          ),
                        ),
                        child: Row(
                          children: [
                            CircleAvatar(
                              radius: 16,
                              backgroundColor: isSelected
                                  ? AppColors.emeraldInk
                                  : const Color(0xFF475569),
                              child: Text(
                                initial,
                                style: TextStyle(
                                  color: isSelected
                                      ? AppColors.champagne
                                      : Colors.white,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Flexible(
                                        child: Text(
                                          displayName,
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.bold,
                                            fontSize: 14,
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                      if (member.isLead) ...[
                                        const SizedBox(width: 6),
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 6, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFFF59E0B)
                                                .withAlpha(40),
                                            borderRadius:
                                                BorderRadius.circular(4),
                                          ),
                                          child: const Text(
                                            'Lead',
                                            style: TextStyle(
                                              color: Color(0xFFFBBF24),
                                              fontSize: 10,
                                              fontWeight: FontWeight.bold,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    member.declaredRole,
                                    style: const TextStyle(
                                      color: Color(0xFF94A3B8),
                                      fontSize: 12,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ],
                              ),
                            ),
                            Checkbox(
                              value: isSelected,
                              activeColor: AppColors.emeraldInk,
                              checkColor: AppColors.champagne,
                              onChanged: (val) {
                                setState(() {
                                  if (val == true) {
                                    _selectedReviewerIds.add(member.userId);
                                  } else {
                                    _selectedReviewerIds.remove(member.userId);
                                  }
                                });
                              },
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),

              // Submit Button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  key: const Key('submit_request_confirmation_btn'),
                  onPressed: _isSubmitting ? null : _submitRequest,
                  icon: _isSubmitting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Icon(Icons.send_rounded, size: 18),
                  label: Text(
                    _isSubmitting
                        ? 'Sending Request...'
                        : 'Send Confirmation Request (${_selectedReviewerIds.length})',
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.emeraldInk,
                    foregroundColor: AppColors.champagne,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
