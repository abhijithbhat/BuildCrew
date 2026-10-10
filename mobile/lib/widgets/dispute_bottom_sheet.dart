import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

/// Bottom sheet dialog for disputing a deliverable with an optional reason (max 280 characters).
class DisputeBottomSheet extends StatefulWidget {
  final String deliverableTitle;

  const DisputeBottomSheet({
    super.key,
    required this.deliverableTitle,
  });

  /// Shows the dispute bottom sheet and returns the trimmed reason String if submitted,
  /// or null if dismissed/cancelled.
  static Future<String?> show({
    required BuildContext context,
    required String deliverableTitle,
  }) async {
    return showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetContext) => DisputeBottomSheet(
        deliverableTitle: deliverableTitle,
      ),
    );
  }

  @override
  State<DisputeBottomSheet> createState() => _DisputeBottomSheetState();
}

class _DisputeBottomSheetState extends State<DisputeBottomSheet> {
  final TextEditingController _reasonController = TextEditingController();
  int _charCount = 0;

  @override
  void initState() {
    super.initState();
    _reasonController.addListener(() {
      setState(() {
        _charCount = _reasonController.text.length;
      });
    });
  }

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  void _submit() {
    final reason = _reasonController.text.trim();
    Navigator.of(context).pop(reason);
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
                  color: AppColors.divider,
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
                    color: const Color(0xFFFFF1F2),
                    shape: BoxShape.circle,
                    border: Border.all(color: const Color(0xFFFECDD3)),
                  ),
                  child: const Icon(
                    Icons.warning_amber_rounded,
                    color: Color(0xFFE11D48),
                    size: 22,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Dispute Deliverable',
                        style: TextStyle(
                          color: AppColors.emeraldInk,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        widget.deliverableTitle,
                        style: const TextStyle(
                          color: AppColors.textMuted,
                          fontSize: 12,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close_rounded, color: AppColors.textMuted),
                  onPressed: () => Navigator.of(context).pop(null),
                ),
              ],
            ),
            const SizedBox(height: 14),

            // Explanatory note
            const Text(
              'Disputing flags this item as Needs Review and sets its visibility to private until resolved with the author.',
              style: TextStyle(
                color: AppColors.textMuted,
                fontSize: 13,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 16),

            // Reason Text Field
            TextField(
              key: const Key('dispute_reason_field'),
              controller: _reasonController,
              maxLength: 280,
              maxLines: 3,
              style: const TextStyle(
                color: AppColors.emeraldInk,
                fontSize: 14,
              ),
              decoration: InputDecoration(
                hintText: 'Reason for dispute (optional)',
                hintStyle: const TextStyle(
                  color: Color(0xFFB0BEC5),
                  fontSize: 13,
                ),
                helperText: '$_charCount / 280 characters',
                helperStyle: const TextStyle(
                  color: AppColors.textMuted,
                  fontSize: 11,
                ),
                filled: true,
                fillColor: AppColors.champagne.withValues(alpha: 0.3),
                contentPadding: const EdgeInsets.all(12),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: AppColors.inputBorder),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: AppColors.inputBorder),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Color(0xFFE11D48), width: 1.5),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Action Buttons: Cancel and Dispute
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.of(context).pop(null),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.textMuted,
                      side: const BorderSide(color: AppColors.inputBorder),
                      padding: const EdgeInsets.symmetric(vertical: 13),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    child: const Text(
                      'Cancel',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    key: const Key('confirm_dispute_dialog_btn'),
                    onPressed: _submit,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFE11D48),
                      foregroundColor: Colors.white,
                      elevation: 0,
                      padding: const EdgeInsets.symmetric(vertical: 13),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    child: const Text(
                      'Dispute',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
