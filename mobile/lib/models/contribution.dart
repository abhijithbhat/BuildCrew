class Contribution {
  final String id;
  final String contributor;
  final String project;
  final String title;
  final String? category;
  final String? description;
  final String? dateRange;
  final String? sourceType;
  final String? evidenceLink;
  final String verificationStatus;
  final String? confirmedBy;
  final String visibility;
  final String disputeState;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final String? contributorName;
  final Map<String, dynamic>? contributorProfile;
  final String? disputedByName;
  final String? disputeReason;
  final bool isDisputeOrphaned;
  final bool canReopen;
  final List<ConfirmationVoteInfo> confirmations;
  final int confirmCount;
  final int teamSize;

  Contribution({
    required this.id,
    required this.contributor,
    required this.project,
    required this.title,
    this.category,
    this.description,
    this.dateRange,
    this.sourceType,
    this.evidenceLink,
    this.verificationStatus = 'pending',
    this.confirmedBy,
    this.visibility = 'private',
    this.disputeState = 'none',
    this.createdAt,
    this.updatedAt,
    this.contributorName,
    this.contributorProfile,
    this.disputedByName,
    this.disputeReason,
    this.isDisputeOrphaned = false,
    this.canReopen = false,
    this.confirmations = const [],
    this.confirmCount = 0,
    this.teamSize = 0,
  });

  factory Contribution.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(dynamic value) {
      if (value == null) return null;
      if (value is DateTime) return value;
      try {
        return DateTime.parse(value.toString());
      } catch (_) {
        return null;
      }
    }

    final rawConfirmations = json['confirmations'] as List<dynamic>? ?? [];

    return Contribution(
      id: json['id']?.toString() ?? '',
      contributor: json['contributor']?.toString() ?? '',
      project: json['project']?.toString() ?? '',
      title: json['title']?.toString() ?? 'Untitled Contribution',
      category: json['category']?.toString(),
      description: json['description']?.toString(),
      dateRange: json['date_range']?.toString(),
      sourceType: json['source_type']?.toString(),
      evidenceLink: json['evidence_link']?.toString(),
      verificationStatus: json['verification_status']?.toString() ?? 'pending',
      confirmedBy: json['confirmed_by']?.toString(),
      visibility: json['visibility']?.toString() ?? 'private',
      disputeState: json['dispute_state']?.toString() ?? 'none',
      createdAt: parseDate(json['created_at']),
      updatedAt: parseDate(json['updated_at']),
      contributorName: json['contributor_name']?.toString() ??
          json['contributor_profile']?['display_name']?.toString() ??
          json['contributor_profile']?['email']?.toString(),
      contributorProfile: json['contributor_profile'] is Map<String, dynamic>
          ? json['contributor_profile'] as Map<String, dynamic>
          : null,
      disputedByName: json['disputed_by_name']?.toString(),
      disputeReason: json['dispute_reason']?.toString(),
      isDisputeOrphaned: json['is_dispute_orphaned'] == true || json['can_reopen'] == true,
      canReopen: json['can_reopen'] == true || json['is_dispute_orphaned'] == true,
      confirmations: rawConfirmations
          .map((c) => ConfirmationVoteInfo.fromJson(Map<String, dynamic>.from(c as Map)))
          .toList(),
      confirmCount: json['confirm_count'] as int? ?? rawConfirmations.length,
      teamSize: json['team_size'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'contributor': contributor,
      'project': project,
      'title': title,
      'category': category,
      'description': description,
      'date_range': dateRange,
      'source_type': sourceType,
      'evidence_link': evidenceLink,
      'verification_status': verificationStatus,
      'confirmed_by': confirmedBy,
      'visibility': visibility,
      'dispute_state': disputeState,
      'created_at': createdAt?.toIso8601String(),
      'updated_at': updatedAt?.toIso8601String(),
      if (contributorName != null) 'contributor_name': contributorName,
      if (contributorProfile != null) 'contributor_profile': contributorProfile,
      if (disputedByName != null) 'disputed_by_name': disputedByName,
      if (disputeReason != null) 'dispute_reason': disputeReason,
      'is_dispute_orphaned': isDisputeOrphaned,
      'can_reopen': canReopen,
      'confirm_count': confirmCount,
      'team_size': teamSize,
    };
  }

  bool get isSourceVerified => verificationStatus == 'source-verified';
  bool get isConfirmed =>
      verificationStatus == 'confirmed' || verificationStatus == 'peer-confirmed';
  bool get isDisputed =>
      disputeState == 'disputed' || verificationStatus == 'disputed';
  bool get needsReview =>
      verificationStatus == 'needs-review' || disputeState == 'disputed';
  bool get isPendingConfirmation =>
      verificationStatus == 'confirmation-pending' ||
      verificationStatus == 'pending-confirmation';
  bool get isDraft => !isConfirmed;
}

class ConfirmationVoteInfo {
  final String name;
  final DateTime? at;

  ConfirmationVoteInfo({
    required this.name,
    this.at,
  });

  factory ConfirmationVoteInfo.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(dynamic value) {
      if (value == null) return null;
      if (value is DateTime) return value;
      try {
        return DateTime.parse(value.toString());
      } catch (_) {
        return null;
      }
    }

    return ConfirmationVoteInfo(
      name: json['name']?.toString() ?? 'Teammate',
      at: parseDate(json['at']),
    );
  }

  Map<String, dynamic> toJson() => {
    'name': name,
    if (at != null) 'at': at!.toIso8601String(),
  };
}

class LedgerEntry {
  final String id;
  final String contributorId;
  final String? contributorName;
  final String title;
  final String? category;
  final String? description;
  final String? evidenceLink;
  final String verificationStatus;
  final List<ConfirmationVoteInfo> confirmations;
  final bool waitingOnMe;
  final DateTime? createdAt;

  LedgerEntry({
    required this.id,
    required this.contributorId,
    this.contributorName,
    required this.title,
    this.category,
    this.description,
    this.evidenceLink,
    required this.verificationStatus,
    this.confirmations = const [],
    this.waitingOnMe = false,
    this.createdAt,
  });

  factory LedgerEntry.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(dynamic value) {
      if (value == null) return null;
      if (value is DateTime) return value;
      try {
        return DateTime.parse(value.toString());
      } catch (_) {
        return null;
      }
    }

    final rawConfirmations = json['confirmations'] as List<dynamic>? ?? [];
    return LedgerEntry(
      id: json['id']?.toString() ?? '',
      contributorId: json['contributor_id']?.toString() ?? '',
      contributorName: json['contributor_name']?.toString(),
      title: json['title']?.toString() ?? 'Untitled Deliverable',
      category: json['category']?.toString(),
      description: json['description']?.toString(),
      evidenceLink: json['evidence_link']?.toString(),
      verificationStatus: json['verification_status']?.toString() ?? 'pending',
      confirmations: rawConfirmations
          .map((c) => ConfirmationVoteInfo.fromJson(Map<String, dynamic>.from(c as Map)))
          .toList(),
      waitingOnMe: json['waiting_on_me'] == true,
      createdAt: parseDate(json['created_at']),
    );
  }
}

class ConfirmationRequest {
  final String id;
  final String contributionId;
  final String projectId;
  final String requestedBy;
  final String reviewerId;
  final String status;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final String? contributionTitle;
  final String? projectName;
  final String? contributorName;
  final String? category;
  final String? description;
  final String? evidenceLink;
  final Contribution? contribution;

  ConfirmationRequest({
    required this.id,
    required this.contributionId,
    required this.projectId,
    required this.requestedBy,
    required this.reviewerId,
    this.status = 'pending',
    this.createdAt,
    this.updatedAt,
    this.contributionTitle,
    this.projectName,
    this.contributorName,
    this.category,
    this.description,
    this.evidenceLink,
    this.contribution,
  });

  factory ConfirmationRequest.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(dynamic value) {
      if (value == null) return null;
      if (value is DateTime) return value;
      try {
        return DateTime.parse(value.toString());
      } catch (_) {
        return null;
      }
    }

    return ConfirmationRequest(
      id: json['id']?.toString() ?? '',
      contributionId: json['contribution_id']?.toString() ?? '',
      projectId: json['project_id']?.toString() ?? '',
      requestedBy: json['requested_by']?.toString() ?? '',
      reviewerId: json['reviewer_id']?.toString() ?? '',
      status: json['status']?.toString() ?? 'pending',
      createdAt: parseDate(json['created_at']),
      updatedAt: parseDate(json['updated_at']),
      contributionTitle: json['contribution_title']?.toString(),
      projectName: json['project_name']?.toString(),
      contributorName: json['contributor_name']?.toString(),
      category: json['category']?.toString(),
      description: json['description']?.toString(),
      evidenceLink: json['evidence_link']?.toString(),
      contribution: json['contribution'] is Map<String, dynamic>
          ? Contribution.fromJson(json['contribution'] as Map<String, dynamic>)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'contribution_id': contributionId,
      'project_id': projectId,
      'requested_by': requestedBy,
      'reviewer_id': reviewerId,
      'status': status,
      'created_at': createdAt?.toIso8601String(),
      'updated_at': updatedAt?.toIso8601String(),
      if (contributionTitle != null) 'contribution_title': contributionTitle,
      if (projectName != null) 'project_name': projectName,
      if (contributorName != null) 'contributor_name': contributorName,
      if (category != null) 'category': category,
      if (description != null) 'description': description,
      if (evidenceLink != null) 'evidence_link': evidenceLink,
      if (contribution != null) 'contribution': contribution!.toJson(),
    };
  }

  bool get isPending => status == 'pending';
  bool get isConfirmed => status == 'confirmed';
  bool get isDisputed => status == 'disputed';
}

class DraftGenerationResult {
  final String message;
  final String projectId;
  final int generatedCount;
  final List<Contribution> contributions;
  final String lastGeneratedAt;

  DraftGenerationResult({
    required this.message,
    required this.projectId,
    required this.generatedCount,
    required this.contributions,
    required this.lastGeneratedAt,
  });

  factory DraftGenerationResult.fromJson(Map<String, dynamic> json) {
    final rawContribs = json['contributions'] as List<dynamic>? ?? [];
    return DraftGenerationResult(
      message: json['message']?.toString() ?? 'Drafts generated successfully.',
      projectId: json['project_id']?.toString() ?? '',
      generatedCount: json['generated_count'] as int? ?? rawContribs.length,
      contributions: rawContribs
          .map((item) => Contribution.fromJson(item as Map<String, dynamic>))
          .toList(),
      lastGeneratedAt: json['last_generated_at']?.toString() ??
          DateTime.now().toUtc().toIso8601String(),
    );
  }
}

