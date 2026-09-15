import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/contribution.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';
import '../widgets/empty_state_view.dart';

class PendingConfirmationsScreen extends StatefulWidget {
  static const String routeName = '/pending-confirmations';

  final ProjectService? projectService;
  final StorageService? storageService;

  const PendingConfirmationsScreen({
    super.key,
    this.projectService,
    this.storageService,
  });

  @override
  State<PendingConfirmationsScreen> createState() =>
      _PendingConfirmationsScreenState();
}

class _PendingConfirmationsScreenState
    extends State<PendingConfirmationsScreen> {
  late final ProjectService _projectService;

  bool _isLoading = true;
  String? _errorMessage;
  List<ConfirmationRequest> _requests = [];
  final Set<String> _processingIds = {};
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _loadPendingConfirmations();
  }

  Future<void> _loadPendingConfirmations() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final list = await _projectService.getPendingConfirmations();
      if (!mounted) return;
      setState(() {
        _requests = list;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _confirmRequest(ConfirmationRequest req) async {
    final contribId = req.contributionId;
    if (contribId.isEmpty) return;

    setState(() {
      _processingIds.add(req.id);
    });

    try {
      await _projectService.confirmContribution(contribId);

      if (!mounted) return;
      setState(() {
        _processingIds.remove(req.id);
        _requests.removeWhere((r) => r.id == req.id);
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.check_circle_rounded,
                  color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Confirmed "${req.contributionTitle ?? 'deliverable'}"!',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          backgroundColor: const Color(0xFF10B981),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _processingIds.remove(req.id);
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to confirm: $e'),
          backgroundColor: const Color(0xFFE11D48),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Future<void> _disputeRequest(ConfirmationRequest req) async {
    final contribId = req.contributionId;
    if (contribId.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: Color(0xFFE2E8F0)),
        ),
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Color(0xFFF59E0B), size: 24),
            SizedBox(width: 8),
            Text(
              'Dispute Deliverable?',
              style: TextStyle(
                color: Color(0xFF0F172A),
                fontSize: 17,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        content: Text(
          'Are you sure you want to dispute "${req.contributionTitle ?? 'this deliverable'}"?\n\n'
          'Its status will become "Needs Review" and visibility will be set to Private until the dispute is resolved.',
          style: const TextStyle(
            color: Color(0xFF64748B),
            fontSize: 13,
            height: 1.4,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: Color(0xFF64748B), fontWeight: FontWeight.w600)),
          ),
          ElevatedButton(
            key: const Key('confirm_dispute_dialog_btn'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFE11D48),
              foregroundColor: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Dispute', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    setState(() {
      _processingIds.add(req.id);
    });

    try {
      await _projectService.disputeContribution(contribId);

      if (!mounted) return;
      setState(() {
        _processingIds.remove(req.id);
        _requests.removeWhere((r) => r.id == req.id);
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.info_outline_rounded,
                  color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Disputed "${req.contributionTitle ?? 'deliverable'}". Set to Needs Review.',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          backgroundColor: const Color(0xFFD97706),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _processingIds.remove(req.id);
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to dispute: $e'),
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
            content: Text('Evidence Link: $url'),
            backgroundColor: const Color(0xFF4F46E5),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  List<ConfirmationRequest> get _filteredRequests {
    if (_searchQuery.trim().isEmpty) return _requests;
    final q = _searchQuery.toLowerCase().trim();
    return _requests.where((r) {
      final titleMatch =
          r.contributionTitle?.toLowerCase().contains(q) ?? false;
      final projectMatch = r.projectName?.toLowerCase().contains(q) ?? false;
      final contributorMatch =
          r.contributorName?.toLowerCase().contains(q) ?? false;
      final categoryMatch = r.category?.toLowerCase().contains(q) ?? false;
      return titleMatch || projectMatch || contributorMatch || categoryMatch;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filteredRequests;

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        title: const Text(
          'Pending Confirmations',
          style: TextStyle(
            color: Color(0xFF0F172A),
            fontWeight: FontWeight.w700,
            fontSize: 18,
            letterSpacing: -0.3,
          ),
        ),
        centerTitle: true,
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF0F172A),
        elevation: 0,
        scrolledUnderElevation: 0,
        shape: const Border(
          bottom: BorderSide(color: Color(0xFFE2E8F0), width: 1),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: Color(0xFF4F46E5)),
            tooltip: 'Refresh',
            onPressed: _loadPendingConfirmations,
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadPendingConfirmations,
          color: const Color(0xFF4F46E5),
          backgroundColor: Colors.white,
          child: Column(
            children: [
              // Header banner with count
              Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                decoration: const BoxDecoration(
                  color: Colors.white,
                  border: Border(
                    bottom: BorderSide(color: Color(0xFFE2E8F0)),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: const BoxDecoration(
                        color: Color(0xFFEEF2FF),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.rate_review_outlined,
                        color: Color(0xFF4F46E5),
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Peer Verification Queue',
                            style: TextStyle(
                              color: Color(0xFF0F172A),
                              fontSize: 15,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 2),
                          const Text(
                            'Review and confirm deliverables logged by teammates',
                            style: TextStyle(
                              color: Color(0xFF64748B),
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: _requests.isNotEmpty
                            ? const Color(0xFF4F46E5)
                            : const Color(0xFFE2E8F0),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        '${_requests.length}',
                        style: TextStyle(
                          color: _requests.isNotEmpty ? Colors.white : const Color(0xFF64748B),
                          fontSize: 13,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // Search field if requests exist
              if (_requests.isNotEmpty) ...[
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  child: TextField(
                    onChanged: (val) {
                      setState(() {
                        _searchQuery = val;
                      });
                    },
                    style: const TextStyle(color: Color(0xFF0F172A), fontSize: 14),
                    decoration: InputDecoration(
                      hintText: 'Search by title, teammate, or project...',
                      hintStyle: const TextStyle(
                        color: Color(0xFFB0BEC5),
                        fontSize: 13,
                      ),
                      prefixIcon: const Icon(Icons.search,
                          color: Color(0xFF4F46E5), size: 20),
                      isDense: true,
                      filled: true,
                      fillColor: Colors.white,
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide:
                            const BorderSide(color: Color(0xFFE2E8F0)),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide:
                            const BorderSide(color: Color(0xFFE2E8F0)),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide:
                            const BorderSide(color: Color(0xFF4F46E5), width: 1.5),
                      ),
                    ),
                  ),
                ),
              ],

              // Main body content
              Expanded(
                child: _buildBody(filtered),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(List<ConfirmationRequest> filtered) {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(
              color: Color(0xFF4F46E5),
              strokeWidth: 2.5,
            ),
            SizedBox(height: 16),
            Text(
              'Loading pending confirmations...',
              style: TextStyle(color: Color(0xFF64748B), fontSize: 13),
            ),
          ],
        ),
      );
    }

    if (_errorMessage != null) {
      return Center(
        key: const Key('pending_confirmations_error'),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.cloud_off_rounded,
                  color: Color(0xFFE11D48), size: 48),
              const SizedBox(height: 16),
              const Text(
                'Failed to load requests',
                style: TextStyle(
                  color: Color(0xFF0F172A),
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                _errorMessage!,
                style: const TextStyle(
                  color: Color(0xFF64748B),
                  fontSize: 12,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: _loadPendingConfirmations,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF4F46E5),
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    if (filtered.isEmpty) {
      final isSearching = _requests.isNotEmpty && _searchQuery.trim().isNotEmpty;
      return EmptyStateView(
        key: const Key('pending_confirmations_empty'),
        icon: isSearching
            ? Icons.filter_list_off_rounded
            : Icons.mark_email_read_outlined,
        badgeColor: isSearching
            ? const Color(0xFFEEF2FF)
            : const Color(0xFFECFDF5),
        badgeBorderColor: isSearching
            ? const Color(0xFFC7D2FE)
            : const Color(0xFFA7F3D0),
        iconColor: isSearching
            ? const Color(0xFF4F46E5)
            : const Color(0xFF10B981),
        badgeSize: 84,
        iconSize: 42,
        title: isSearching
            ? 'No Matching Requests'
            : 'All Caught Up!',
        description: isSearching
            ? 'No pending confirmations match "$_searchQuery". Try searching with another keyword.'
            : 'You have no pending confirmations waiting for your review.\nWhen teammates ask you to verify their impact deliverables, they will appear here.',
        primaryAction: isSearching
            ? OutlinedButton.icon(
                onPressed: () {
                  setState(() {
                    _searchQuery = '';
                  });
                },
                icon: const Icon(Icons.clear_rounded, size: 16),
                label: const Text('Clear Search'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF4F46E5),
                  side: const BorderSide(color: Color(0xFFC7D2FE)),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              )
            : null,
      );
    }

    return ListView.separated(
      key: const Key('pending_confirmations_list'),
      padding: const EdgeInsets.all(16),
      itemCount: filtered.length,
      separatorBuilder: (_, _) => const SizedBox(height: 14),
      itemBuilder: (ctx, index) {
        final req = filtered[index];
        final isProcessing = _processingIds.contains(req.id);
        return _buildRequestCard(req, isProcessing);
      },
    );
  }

  Widget _buildRequestCard(ConfirmationRequest req, bool isProcessing) {
    final title = req.contributionTitle ?? 'Untitled Deliverable';
    final projectName = req.projectName ?? 'Project';
    final contributorName = req.contributorName ?? 'Teammate';
    final category = req.category ?? 'general';
    final initial =
        contributorName.isNotEmpty ? contributorName[0].toUpperCase() : 'T';

    return Container(
      key: Key('pending_card_${req.id}'),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE2E8F0), width: 1.0),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.04),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Top Row: Contributor avatar + name + project badge
          Row(
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: const Color(0xFF4F46E5),
                child: Text(
                  initial,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      contributorName,
                      style: const TextStyle(
                        color: Color(0xFF0F172A),
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'in $projectName',
                      style: const TextStyle(
                        color: Color(0xFF4F46E5),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  category.toUpperCase(),
                  style: const TextStyle(
                    color: Color(0xFF64748B),
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Title
          Text(
            title,
            style: const TextStyle(
              color: Color(0xFF0F172A),
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),

          // Description if present
          if (req.description != null && req.description!.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              req.description!,
              style: const TextStyle(
                color: Color(0xFF475569),
                fontSize: 13,
                height: 1.4,
              ),
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
            ),
          ],

          // Evidence Link Card
          if (req.evidenceLink != null && req.evidenceLink!.isNotEmpty) ...[
            const SizedBox(height: 10),
            InkWell(
              onTap: () => _openEvidenceLink(req.evidenceLink!),
              borderRadius: BorderRadius.circular(8),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.link_rounded,
                        color: Color(0xFF4F46E5), size: 16),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        req.evidenceLink!,
                        style: const TextStyle(
                          color: Color(0xFF4F46E5),
                          fontSize: 12,
                          decoration: TextDecoration.underline,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Icon(Icons.arrow_outward_rounded,
                        color: Color(0xFF4F46E5), size: 14),
                  ],
                ),
              ),
            ),
          ],

          const SizedBox(height: 14),
          const Divider(height: 1, color: Color(0xFFF1F5F9)),
          const SizedBox(height: 12),

          // Action Buttons: Confirm & Dispute
          Row(
            children: [
              // Dispute Button
              Expanded(
                child: OutlinedButton.icon(
                  key: Key('dispute_btn_${req.id}'),
                  onPressed: isProcessing ? null : () => _disputeRequest(req),
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
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),

              // Confirm Button
              Expanded(
                flex: 2,
                child: ElevatedButton.icon(
                  key: Key('confirm_btn_${req.id}'),
                  onPressed: isProcessing ? null : () => _confirmRequest(req),
                  icon: isProcessing
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Icon(Icons.check_rounded, size: 18),
                  label: Text(
                    isProcessing ? 'Processing...' : 'Peer Confirm',
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF10B981),
                    foregroundColor: Colors.white,
                    elevation: 0,
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
