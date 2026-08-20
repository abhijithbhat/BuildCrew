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
    this.visibility = 'public',
    this.disputeState = 'none',
    this.createdAt,
    this.updatedAt,
    this.contributorName,
    this.contributorProfile,
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
      visibility: json['visibility']?.toString() ?? 'public',
      disputeState: json['dispute_state']?.toString() ?? 'none',
      createdAt: parseDate(json['created_at']),
      updatedAt: parseDate(json['updated_at']),
      contributorName: json['contributor_name']?.toString() ??
          json['contributor_profile']?['display_name']?.toString() ??
          json['contributor_profile']?['email']?.toString(),
      contributorProfile: json['contributor_profile'] is Map<String, dynamic>
          ? json['contributor_profile'] as Map<String, dynamic>
          : null,
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
    };
  }

  bool get isSourceVerified => verificationStatus == 'source-verified';
  bool get isConfirmed => verificationStatus == 'confirmed';
  bool get isDraft => !isConfirmed;
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
