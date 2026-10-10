import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/contribution.dart';
import '../services/project_service.dart';
import '../theme/app_colors.dart';
import '../utils/error_messages.dart';
import '../widgets/connection_error_retry_widget.dart';
import '../widgets/dispute_bottom_sheet.dart';
import '../widgets/empty_state_view.dart';

class TeamLedgerScreen extends StatefulWidget {
  static const String routeName = '/team-ledger';

  final String projectId;
  final String? projectName;
  final ProjectService? projectService;

  const TeamLedgerScreen({
    super.key,
    required this.projectId,
    this.projectName,
    this.projectService,
  });

  @override
  State<TeamLedgerScreen> createState() => _TeamLedgerScreenState();
}

class _TeamLedgerScreenState extends State<TeamLedgerScreen> {
  late final ProjectService _projectService;

  bool _isLoading = true;
  String? _errorMessage;
  List<LedgerEntry> _entries = [];
  final Set<String> _processingIds = {};

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _loadLedger();
  }

  Future<void> _loadLedger() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final list = await _projectService.getProjectLedger(widget.projectId);
      if (!mounted) return;
      setState(() {
        _entries = list;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = friendlyError(e);
        _isLoading = false;
      });
    }
  }

  Future<void> _openReviewSheet(LedgerEntry entry) async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
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
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: const BoxDecoration(
                        color: Color(0xFFEFF6FF),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.rate_review_outlined,
                        color: Color(0xFF2563EB),
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Review Deliverable',
                            style: TextStyle(
                              color: AppColors.emeraldInk,
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'By ${entry.contributorName ?? "Teammate"}',
                            style: const TextStyle(
                              color: AppColors.textMuted,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded,
                          color: AppColors.textMuted),
                      onPressed: () => Navigator.of(sheetContext).pop(),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: AppColors.champagne.withValues(alpha: 0.25),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: AppColors.inputBorder),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        entry.title,
                        style: const TextStyle(
                          color: AppColors.emeraldInk,
                          fontSize: 15,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      if (entry.category != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          entry.category!.toUpperCase(),
                          style: const TextStyle(
                            color: AppColors.textMuted,
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                      if (entry.description != null &&
                          entry.description!.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          entry.description!,
                          style: const TextStyle(
                            color: AppColors.emeraldInk,
                            fontSize: 13,
                            height: 1.35,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Confirm disclaimer note
                const Center(
                  child: Text(
                    'Your name will appear next to this item if the author publishes it.',
                    style: TextStyle(
                      color: AppColors.textMuted,
                      fontSize: 12,
                      fontStyle: FontStyle.italic,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: 14),

                // Review Action Buttons: Dispute & Confirm
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        key: const Key('ledger_review_dispute_btn'),
                        onPressed: () async {
                          Navigator.of(sheetContext).pop();
                          final reason = await DisputeBottomSheet.show(
                            context: context,
                            deliverableTitle: entry.title,
                          );
                          if (reason == null) return;
                          _disputeEntry(entry, reason: reason);
                        },
                        icon: const Icon(Icons.close_rounded,
                            color: Color(0xFFE11D48), size: 16),
                        label: const Text(
                          'Dispute',
                          style: TextStyle(
                            color: Color(0xFFE11D48),
                            fontWeight: FontWeight.bold,
                            fontSize: 13,
                          ),
                        ),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(
                            color: Color(0xFFFECDD3),
                            width: 1.2,
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      flex: 2,
                      child: ElevatedButton.icon(
                        key: const Key('ledger_review_confirm_btn'),
                        onPressed: () {
                          Navigator.of(sheetContext).pop();
                          _confirmEntry(entry);
                        },
                        icon: const Icon(Icons.check_rounded,
                            size: 18, color: Colors.white),
                        label: const Text(
                          'Peer Confirm',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 13,
                            color: Colors.white,
                          ),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF10B981),
                          foregroundColor: Colors.white,
                          elevation: 0,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _confirmEntry(LedgerEntry entry) async {
    setState(() {
      _processingIds.add(entry.id);
    });

    try {
      await _projectService.confirmContribution(entry.id);
      if (!mounted) return;
      setState(() {
        _processingIds.remove(entry.id);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Confirmed "${entry.title}"!'),
          backgroundColor: const Color(0xFF10B981),
          behavior: SnackBarBehavior.floating,
        ),
      );
      _loadLedger();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _processingIds.remove(entry.id);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to confirm: ${friendlyError(e)}'),
          backgroundColor: const Color(0xFFE11D48),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Future<void> _disputeEntry(LedgerEntry entry, {String? reason}) async {
    setState(() {
      _processingIds.add(entry.id);
    });

    try {
      await _projectService.disputeContribution(
        entry.id,
        reason: (reason != null && reason.trim().isNotEmpty) ? reason.trim() : null,
      );
      if (!mounted) return;
      setState(() {
        _processingIds.remove(entry.id);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Disputed "${entry.title}". Set to Needs Review.'),
          backgroundColor: const Color(0xFFD97706),
          behavior: SnackBarBehavior.floating,
        ),
      );
      _loadLedger();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _processingIds.remove(entry.id);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to dispute: ${friendlyError(e)}'),
          backgroundColor: const Color(0xFFE11D48),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Future<void> _openEvidenceLink(String url) async {
    final uri = Uri.tryParse(url);
    if (uri != null) {
      try {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } catch (_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Evidence: $url'),
            backgroundColor: AppColors.emeraldInk,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  String _formatProofTag(LedgerEntry entry) {
    if (entry.verificationStatus == 'source-verified') {
      return 'GitHub-verified';
    }
    if (entry.confirmations.isNotEmpty) {
      final names = entry.confirmations.map((c) => c.name).join(', ');
      return 'Confirmed by $names';
    }
    if (entry.verificationStatus == 'confirmed' ||
        entry.verificationStatus == 'peer-confirmed') {
      return 'Confirmed';
    }
    return 'Waiting for review';
  }

  Color _getStatusColor(String status) {
    final s = status.toLowerCase();
    if (s == 'confirmed' || s == 'peer-confirmed' || s == 'source-verified') {
      return const Color(0xFF10B981);
    }
    if (s == 'needs-review' || s == 'disputed') {
      return const Color(0xFFE11D48);
    }
    return const Color(0xFFD97706);
  }

  @override
  Widget build(BuildContext context) {
    // Group entries by teammate
    final Map<String, List<LedgerEntry>> groupedByTeammate = {};
    for (final entry in _entries) {
      final key = entry.contributorName?.isNotEmpty == true
          ? entry.contributorName!
          : (entry.contributorId.isNotEmpty ? entry.contributorId : 'Teammate');
      groupedByTeammate.putIfAbsent(key, () => []).add(entry);
    }

    return Scaffold(
      backgroundColor: AppColors.champagne,
      appBar: AppBar(
        title: Column(
          children: [
            const Text(
              'Team Ledger',
              style: TextStyle(
                color: AppColors.emeraldInk,
                fontWeight: FontWeight.w700,
                fontSize: 18,
                letterSpacing: -0.3,
              ),
            ),
            if (widget.projectName != null)
              Text(
                widget.projectName!,
                style: const TextStyle(
                  color: AppColors.emeraldInk,
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
          ],
        ),
        centerTitle: true,
        backgroundColor: AppColors.champagne,
        foregroundColor: AppColors.emeraldInk,
        elevation: 0,
        scrolledUnderElevation: 0,
        shape: const Border(
          bottom: BorderSide(color: AppColors.inputBorder, width: 1),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: AppColors.emeraldInk),
            tooltip: 'Refresh',
            onPressed: _loadLedger,
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadLedger,
          color: AppColors.emeraldInk,
          backgroundColor: AppColors.champagne,
          child: _isLoading
              ? const Center(
                  child: CircularProgressIndicator(
                    color: AppColors.emeraldInk,
                    strokeWidth: 2.5,
                  ),
                )
              : _errorMessage != null
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: ConnectionErrorRetryWidget(
                          message: _errorMessage,
                          onRetry: _loadLedger,
                        ),
                      ),
                    )
                  : _entries.isEmpty
                      ? ListView(
                          children: const [
                            SizedBox(height: 60),
                            EmptyStateView(
                              icon: Icons.menu_book_rounded,
                              title: 'No Deliverables Logged',
                              description:
                                  'Deliverables declared or verified by team members will appear in this ledger.',
                            ),
                          ],
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 14),
                          itemCount: groupedByTeammate.keys.length,
                          itemBuilder: (context, index) {
                            final teammate =
                                groupedByTeammate.keys.elementAt(index);
                            final teammateEntries = groupedByTeammate[teammate]!;
                            final initial = teammate.isNotEmpty
                                ? teammate[0].toUpperCase()
                                : 'T';

                            return Container(
                              margin: const EdgeInsets.only(bottom: 16),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(14),
                                border: Border.all(color: AppColors.divider),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.03),
                                    blurRadius: 8,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  // Teammate Header
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 14, vertical: 12),
                                    decoration: BoxDecoration(
                                      color: AppColors.emeraldInk
                                          .withValues(alpha: 0.05),
                                      borderRadius: const BorderRadius.vertical(
                                          top: Radius.circular(14)),
                                    ),
                                    child: Row(
                                      children: [
                                        CircleAvatar(
                                          radius: 14,
                                          backgroundColor: AppColors.emeraldInk,
                                          child: Text(
                                            initial,
                                            style: const TextStyle(
                                              color: AppColors.champagne,
                                              fontSize: 12,
                                              fontWeight: FontWeight.bold,
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 10),
                                        Expanded(
                                          child: Text(
                                            teammate,
                                            style: const TextStyle(
                                              color: AppColors.emeraldInk,
                                              fontWeight: FontWeight.bold,
                                              fontSize: 15,
                                            ),
                                          ),
                                        ),
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 8, vertical: 3),
                                          decoration: BoxDecoration(
                                            color: AppColors.champagne,
                                            borderRadius:
                                                BorderRadius.circular(12),
                                            border: Border.all(
                                                color: AppColors.inputBorder),
                                          ),
                                          child: Text(
                                            '${teammateEntries.length} item${teammateEntries.length == 1 ? "" : "s"}',
                                            style: const TextStyle(
                                              color: AppColors.emeraldInk,
                                              fontSize: 11,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const Divider(
                                      height: 1, color: AppColors.divider),

                                  // Teammate Deliverables
                                  ...teammateEntries.asMap().entries.map((itemEntry) {
                                    final entryIndex = itemEntry.key;
                                    final entry = itemEntry.value;
                                    final proofTag = _formatProofTag(entry);
                                    final statusColor =
                                        _getStatusColor(entry.verificationStatus);
                                    final isProcessing =
                                        _processingIds.contains(entry.id);

                                    return Column(
                                      children: [
                                        if (entryIndex > 0)
                                          const Divider(
                                              height: 1,
                                              color: AppColors.divider),
                                        Padding(
                                          padding: const EdgeInsets.all(14),
                                          child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              // Deliverable Category & Status row
                                              Row(
                                                children: [
                                                  if (entry.category != null) ...[
                                                    Container(
                                                      padding:
                                                          const EdgeInsets.symmetric(
                                                              horizontal: 7,
                                                              vertical: 2.5),
                                                      decoration: BoxDecoration(
                                                        color: AppColors.champagne
                                                            .withValues(alpha: 0.5),
                                                        borderRadius:
                                                            BorderRadius.circular(6),
                                                      ),
                                                      child: Text(
                                                        entry.category!.toUpperCase(),
                                                        style: const TextStyle(
                                                          color:
                                                              AppColors.emeraldInk,
                                                          fontSize: 10,
                                                          fontWeight:
                                                              FontWeight.bold,
                                                        ),
                                                      ),
                                                    ),
                                                    const SizedBox(width: 8),
                                                  ],
                                                  Container(
                                                    padding:
                                                        const EdgeInsets.symmetric(
                                                            horizontal: 7,
                                                            vertical: 2.5),
                                                    decoration: BoxDecoration(
                                                      color: statusColor
                                                          .withValues(alpha: 0.12),
                                                      borderRadius:
                                                          BorderRadius.circular(6),
                                                    ),
                                                    child: Text(
                                                      entry.verificationStatus
                                                          .toUpperCase(),
                                                      style: TextStyle(
                                                        color: statusColor,
                                                        fontSize: 10,
                                                        fontWeight:
                                                            FontWeight.bold,
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 8),

                                              // Title
                                              Text(
                                                entry.title,
                                                style: const TextStyle(
                                                  color: AppColors.emeraldInk,
                                                  fontSize: 15,
                                                  fontWeight: FontWeight.bold,
                                                ),
                                              ),

                                              // Description if present
                                              if (entry.description != null &&
                                                  entry.description!.isNotEmpty) ...[
                                                const SizedBox(height: 4),
                                                Text(
                                                  entry.description!,
                                                  style: const TextStyle(
                                                    color: AppColors.textMuted,
                                                    fontSize: 13,
                                                    height: 1.35,
                                                  ),
                                                  maxLines: 2,
                                                  overflow:
                                                      TextOverflow.ellipsis,
                                                ),
                                              ],

                                              // Evidence Link
                                              if (entry.evidenceLink != null &&
                                                  entry.evidenceLink!.isNotEmpty) ...[
                                                const SizedBox(height: 8),
                                                InkWell(
                                                  onTap: () => _openEvidenceLink(
                                                      entry.evidenceLink!),
                                                  child: Row(
                                                    mainAxisSize: MainAxisSize.min,
                                                    children: [
                                                      const Icon(Icons.link_rounded,
                                                          size: 14,
                                                          color:
                                                              AppColors.emeraldInk),
                                                      const SizedBox(width: 4),
                                                      Flexible(
                                                        child: Text(
                                                          entry.evidenceLink!,
                                                          style: const TextStyle(
                                                            color:
                                                                AppColors.emeraldInk,
                                                            fontSize: 12,
                                                            decoration:
                                                                TextDecoration
                                                                    .underline,
                                                          ),
                                                          maxLines: 1,
                                                          overflow:
                                                              TextOverflow.ellipsis,
                                                        ),
                                                      ),
                                                    ],
                                                  ),
                                                ),
                                              ],

                                              const SizedBox(height: 10),

                                              // Proof Tag & Review Button Row
                                              Row(
                                                mainAxisAlignment:
                                                    MainAxisAlignment
                                                        .spaceBetween,
                                                children: [
                                                  Expanded(
                                                    child: Row(
                                                      children: [
                                                        Icon(
                                                          entry.verificationStatus ==
                                                                  'source-verified'
                                                              ? Icons
                                                                  .verified_rounded
                                                              : (entry.confirmations
                                                                      .isNotEmpty
                                                                  ? Icons
                                                                      .check_circle_outline_rounded
                                                                  : Icons
                                                                      .hourglass_top_rounded),
                                                          size: 14,
                                                          color: entry.confirmations
                                                                      .isNotEmpty ||
                                                                  entry.verificationStatus ==
                                                                      'source-verified'
                                                              ? const Color(
                                                                  0xFF10B981)
                                                              : AppColors
                                                                  .textMuted,
                                                        ),
                                                        const SizedBox(width: 5),
                                                        Flexible(
                                                          child: Text(
                                                            proofTag,
                                                            style: TextStyle(
                                                              color: entry.confirmations
                                                                          .isNotEmpty ||
                                                                      entry.verificationStatus ==
                                                                          'source-verified'
                                                                  ? const Color(
                                                                      0xFF065F46)
                                                                  : AppColors
                                                                      .textMuted,
                                                              fontSize: 12,
                                                              fontWeight:
                                                                  FontWeight.w500,
                                                            ),
                                                            overflow: TextOverflow
                                                                .ellipsis,
                                                          ),
                                                        ),
                                                      ],
                                                    ),
                                                  ),
                                                  if (entry.waitingOnMe) ...[
                                                    const SizedBox(width: 8),
                                                    ElevatedButton.icon(
                                                      key: Key(
                                                          'ledger_review_btn_${entry.id}'),
                                                      onPressed: isProcessing
                                                          ? null
                                                          : () => _openReviewSheet(
                                                              entry),
                                                      icon: const Icon(
                                                          Icons
                                                              .rate_review_outlined,
                                                          size: 14,
                                                          color: Colors.white),
                                                      label: const Text(
                                                        'Review',
                                                        style: TextStyle(
                                                          fontSize: 12,
                                                          fontWeight:
                                                              FontWeight.bold,
                                                          color: Colors.white,
                                                        ),
                                                      ),
                                                      style: ElevatedButton
                                                          .styleFrom(
                                                        backgroundColor:
                                                            AppColors.emeraldInk,
                                                        foregroundColor:
                                                            Colors.white,
                                                        elevation: 0,
                                                        padding: const EdgeInsets
                                                            .symmetric(
                                                            horizontal: 12,
                                                            vertical: 6),
                                                        shape:
                                                            RoundedRectangleBorder(
                                                          borderRadius:
                                                              BorderRadius
                                                                  .circular(8),
                                                        ),
                                                      ),
                                                    ),
                                                  ],
                                                ],
                                              ),
                                            ],
                                          ),
                                        ),
                                      ],
                                    );
                                  }),
                                ],
                              ),
                            );
                          },
                        ),
        ),
      ),
    );
  }
}
