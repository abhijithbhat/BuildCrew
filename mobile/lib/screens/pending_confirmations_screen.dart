import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/contribution.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';

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
          backgroundColor: Colors.red.shade700,
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
        backgroundColor: const Color(0xFF151C2C),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: Color(0xFF1E293B)),
        ),
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Colors.amberAccent, size: 24),
            SizedBox(width: 8),
            Text(
              'Dispute Deliverable?',
              style: TextStyle(
                color: Colors.white,
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
            color: Color(0xFF94A3B8),
            fontSize: 13,
            height: 1.4,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: Colors.white70)),
          ),
          ElevatedButton(
            key: const Key('confirm_dispute_dialog_btn'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.redAccent,
              foregroundColor: Colors.white,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Dispute'),
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
          backgroundColor: Colors.red.shade700,
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
            backgroundColor: const Color(0xFF2563EB),
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
      backgroundColor: const Color(0xFF0A0E1A),
      appBar: AppBar(
        title: const Text(
          'Pending Confirmations',
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            fontSize: 18,
          ),
        ),
        centerTitle: true,
        backgroundColor: const Color(0xFF10162A),
        foregroundColor: Colors.white,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: Colors.white70),
            tooltip: 'Refresh',
            onPressed: _loadPendingConfirmations,
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadPendingConfirmations,
          color: const Color(0xFF6366F1),
          backgroundColor: const Color(0xFF1E293B),
          child: Column(
            children: [
              // Header banner with count
              Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                decoration: const BoxDecoration(
                  color: Color(0xFF10162A),
                  border: Border(
                    bottom: BorderSide(color: Color(0xFF1E293B)),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF4F46E5).withAlpha(40),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.rate_review_outlined,
                        color: Color(0xFF818CF8),
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
                              color: Colors.white,
                              fontSize: 15,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Review and confirm deliverables logged by teammates',
                            style: TextStyle(
                              color: Colors.grey.shade400,
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
                            ? const Color(0xFF6366F1)
                            : Colors.grey.shade800,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        '${_requests.length}',
                        style: const TextStyle(
                          color: Colors.white,
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
                    style: const TextStyle(color: Colors.white, fontSize: 14),
                    decoration: InputDecoration(
                      hintText: 'Search by title, teammate, or project...',
                      hintStyle: const TextStyle(
                        color: Color(0xFFB0BEC5),
                        fontSize: 13,
                      ),
                      prefixIcon: const Icon(Icons.search,
                          color: Color(0xFF94A3B8), size: 20),
                      isDense: true,
                      filled: true,
                      fillColor: const Color(0xFF151C2C),
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide:
                            const BorderSide(color: Color(0xFF1E293B)),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide:
                            const BorderSide(color: Color(0xFF1E293B)),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide:
                            const BorderSide(color: Color(0xFF6366F1)),
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
              color: Color(0xFF6366F1),
              strokeWidth: 2.5,
            ),
            SizedBox(height: 16),
            Text(
              'Loading pending confirmations...',
              style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
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
                  color: Colors.redAccent, size: 48),
              const SizedBox(height: 16),
              const Text(
                'Failed to load requests',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                _errorMessage!,
                style: const TextStyle(
                  color: Color(0xFF94A3B8),
                  fontSize: 12,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: _loadPendingConfirmations,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF4F46E5),
                ),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    if (filtered.isEmpty) {
      return Center(
        key: const Key('pending_confirmations_empty'),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: const Color(0xFF151C2C),
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0xFF1E293B)),
                ),
                child: const Icon(
                  Icons.mark_email_read_outlined,
                  color: Color(0xFF10B981),
                  size: 48,
                ),
              ),
              const SizedBox(height: 20),
              const Text(
                'All Caught Up!',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'You have no pending confirmations waiting for your review.\nWhen teammates ask you to verify their impact deliverables, they will appear here.',
                style: TextStyle(
                  color: Color(0xFF94A3B8),
                  fontSize: 13,
                  height: 1.4,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
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
        color: const Color(0xFF151C2C),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1E293B), width: 1.2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(50),
            blurRadius: 8,
            offset: const Offset(0, 2),
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
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'in $projectName',
                      style: const TextStyle(
                        color: Color(0xFF818CF8),
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
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
                  color: const Color(0xFF334155),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  category.toUpperCase(),
                  style: const TextStyle(
                    color: Color(0xFF94A3B8),
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
              color: Colors.white,
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
                color: Color(0xFF94A3B8),
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
                  color: const Color(0xFF1E293B),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFF334155)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.link_rounded,
                        color: Color(0xFF60A5FA), size: 16),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        req.evidenceLink!,
                        style: const TextStyle(
                          color: Color(0xFF60A5FA),
                          fontSize: 12,
                          decoration: TextDecoration.underline,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Icon(Icons.arrow_outward_rounded,
                        color: Color(0xFF60A5FA), size: 14),
                  ],
                ),
              ),
            ),
          ],

          const SizedBox(height: 14),
          const Divider(height: 1, color: Color(0xFF1E293B)),
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
                      color: Colors.redAccent, size: 16),
                  label: const Text(
                    'Dispute',
                    style: TextStyle(
                      color: Colors.redAccent,
                      fontWeight: FontWeight.bold,
                      fontSize: 13,
                    ),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(
                      color: Colors.redAccent.withAlpha(120),
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
