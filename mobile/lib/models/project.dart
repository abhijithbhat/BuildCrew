class Project {
  final String id;
  final String name;
  final String? description;
  final String? createdBy;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final String? role;
  final DateTime? joinedAt;

  Project({
    required this.id,
    required this.name,
    this.description,
    this.createdBy,
    this.createdAt,
    this.updatedAt,
    this.role,
    this.joinedAt,
  });

  factory Project.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(dynamic dateVal) {
      if (dateVal == null) return null;
      if (dateVal is DateTime) return dateVal;
      try {
        return DateTime.parse(dateVal.toString());
      } catch (_) {
        return null;
      }
    }

    return Project(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String?,
      createdBy: json['created_by'] as String?,
      createdAt: parseDate(json['created_at']),
      updatedAt: parseDate(json['updated_at']),
      role: json['role'] as String? ?? json['my_role'] as String?,
      joinedAt: parseDate(json['joined_at']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      if (description != null) 'description': description,
      if (createdBy != null) 'created_by': createdBy,
      if (createdAt != null) 'created_at': createdAt?.toIso8601String(),
      if (updatedAt != null) 'updated_at': updatedAt?.toIso8601String(),
      if (role != null) 'role': role,
      if (joinedAt != null) 'joined_at': joinedAt?.toIso8601String(),
    };
  }
}
