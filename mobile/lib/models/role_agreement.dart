class RoleAgreement {
  final String id;
  final String projectId;
  final String userId;
  final String declaredRole;
  final String? responsibilities;
  final DateTime? deadline;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final Map<String, dynamic>? profile;
  final String? projectCreatedBy;
  final bool isDeclared;

  RoleAgreement({
    required this.id,
    required this.projectId,
    required this.userId,
    required this.declaredRole,
    this.responsibilities,
    this.deadline,
    this.createdAt,
    this.updatedAt,
    this.profile,
    this.projectCreatedBy,
    this.isDeclared = true,
  });

  bool get isLead =>
      projectCreatedBy != null &&
      projectCreatedBy!.isNotEmpty &&
      userId == projectCreatedBy;

  factory RoleAgreement.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(dynamic dateVal) {
      if (dateVal == null) return null;
      if (dateVal is DateTime) return dateVal;
      try {
        return DateTime.parse(dateVal.toString());
      } catch (_) {
        return null;
      }
    }

    final profileData = json['profiles'] as Map<String, dynamic>? ??
        json['profile'] as Map<String, dynamic>?;

    final createdBy = json['project_created_by'] as String? ??
        json['created_by'] as String? ??
        json['lead_user_id'] as String?;

    final declaredRoleStr = json['declared_role'] as String? ??
        json['role'] as String? ??
        'Team Member';

    final isDeclaredVal = json['is_declared'] as bool? ??
        (declaredRoleStr != 'Pending Role Declaration' &&
            declaredRoleStr != 'Role Not Declared');

    return RoleAgreement(
      id: json['id'] as String? ?? '',
      projectId: json['project_id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      declaredRole: declaredRoleStr,
      responsibilities: json['responsibilities'] as String?,
      deadline: parseDate(json['deadline']),
      createdAt: parseDate(json['created_at']),
      updatedAt: parseDate(json['updated_at']),
      profile: profileData,
      projectCreatedBy: createdBy,
      isDeclared: isDeclaredVal,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'project_id': projectId,
      'user_id': userId,
      'declared_role': declaredRole,
      'is_declared': isDeclared,
      if (responsibilities != null) 'responsibilities': responsibilities,
      if (deadline != null) 'deadline': deadline?.toIso8601String(),
      if (createdAt != null) 'created_at': createdAt?.toIso8601String(),
      if (updatedAt != null) 'updated_at': updatedAt?.toIso8601String(),
      if (profile != null) 'profiles': profile,
      if (projectCreatedBy != null) 'project_created_by': projectCreatedBy,
    };
  }



  /// Converts emails or concatenated usernames into formatted human names with proper spaces and title-case.
  /// Examples:
  /// - "abhijithmbhat@gmail.com" -> "Abhijith M Bhat"
  /// - "abhijithhubli@gmail.com" -> "Abhijith Hubli"
  /// - "alex.rivers@buildcrew.io" -> "Alex Rivers"
  /// - "Sarah Connor" -> "Sarah Connor"
  static String formatEmailToHumanName(String input) {
    final trimmed = input.trim();
    if (trimmed.isEmpty) return 'Team Member';

    final rawPrefix = trimmed.contains('@') ? trimmed.split('@')[0] : trimmed;
    if (rawPrefix.isEmpty) return 'Team Member';

    // If input already has spaces and is not an email, return clean trimmed string
    if (!trimmed.contains('@') && rawPrefix.contains(' ')) {
      return rawPrefix
          .split(' ')
          .where((p) => p.isNotEmpty)
          .map((p) => '${p[0].toUpperCase()}${p.substring(1)}')
          .join(' ');
    }

    // Handle standard delimiters: dot, underscore, hyphen
    if (rawPrefix.contains(RegExp(r'[\._\-]'))) {
      return rawPrefix
          .split(RegExp(r'[\._\-]'))
          .where((part) => part.isNotEmpty)
          .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
          .join(' ');
    }

    final text = rawPrefix.toLowerCase();

    // Common first names
    const firstNames = [
      'abhijith', 'vishwajith', 'abhishek', 'abhijeet', 'rahul', 'aditya',
      'rohit', 'sachin', 'virat', 'alex', 'elena', 'sarah', 'david', 'john',
      'michael', 'robert', 'emma', 'anand', 'praveen', 'prashant', 'suresh'
    ];

    // Common surnames for 3-part names (FirstName + Middle Initial + Surname)
    const commonSurnames = {
      'bhat', 'kumar', 'singh', 'patel', 'rao', 'pai', 'gowda', 'sharma',
      'verma', 'gupta', 'reddy', 'hegde', 'naik', 'das', 'roy', 'sen',
      'shetty', 'kamath', 'kulkarni', 'deshpande', 'joshi', 'iyer', 'menon',
      'nair', 'rivers', 'rostova', 'connor', 'smith', 'jones', 'williams'
    };

    for (final fn in firstNames) {
      if (text.startsWith(fn) && text.length > fn.length) {
        final rest = text.substring(fn.length);
        final formattedFn = '${fn[0].toUpperCase()}${fn.substring(1)}';

        if (rest.length >= 3) {
          final middleLetter = rest[0];
          final potentialSurname = rest.substring(1);
          if (commonSurnames.contains(potentialSurname)) {
            return '$formattedFn ${middleLetter.toUpperCase()} ${potentialSurname[0].toUpperCase()}${potentialSurname.substring(1)}';
          }
        }

        return '$formattedFn ${rest[0].toUpperCase()}${rest.substring(1)}';
      }
    }

    return '${text[0].toUpperCase()}${text.substring(1)}';
  }

  String get displayName {
    if (profile != null) {
      final name = profile!['display_name'] ??
          profile!['full_name'] ??
          profile!['name'];
      if (name != null && name.toString().trim().isNotEmpty) {
        final nameStr = name.toString().trim();
        // If it's already a clean non-email name with spaces, return formatted title-case
        if (!nameStr.contains('@')) {
          return formatEmailToHumanName(nameStr);
        }
        return formatEmailToHumanName(nameStr);
      }
      final emailVal = profile!['email'];
      if (emailVal != null && emailVal.toString().trim().isNotEmpty) {
        return formatEmailToHumanName(emailVal.toString().trim());
      }
    }
    return userId.length > 8
        ? 'Member (${userId.substring(0, 8)})'
        : (userId.isNotEmpty ? userId : 'Team Member');
  }

  String? get email {
    if (profile != null) {
      if (profile!['email'] != null &&
          profile!['email'].toString().trim().isNotEmpty) {
        return profile!['email'].toString().trim();
      }
      // If profile display_name is an email, extract it
      final name = profile!['display_name'] ??
          profile!['full_name'] ??
          profile!['name'];
      if (name != null && name.toString().contains('@')) {
        return name.toString().trim();
      }
    }
    return null;
  }

  String get avatarInitial {
    final name = displayName;
    if (name.isNotEmpty) {
      return name[0].toUpperCase();
    }
    return 'M';
  }

  String? get formattedDeadline {
    if (deadline == null) return null;
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
    return '${months[deadline!.month - 1]} ${deadline!.day}, ${deadline!.year}';
  }
}
