import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/models/project.dart';
import 'package:mobile/services/project_service.dart';

/// Network-free ProjectService for HomeScreen tests.
class FakeHomeProjectService extends ProjectService {
  FakeHomeProjectService({this.projects = const <Project>[], this.pendingCount = 0}) {
    FlutterSecureStorage.setMockInitialValues({});
  }

  final List<Project> projects;
  final int pendingCount;

  @override
  Future<List<Project>> listProjects({bool includeArchived = false}) async => projects;

  @override
  Future<List<ConfirmationRequest>> getPendingConfirmations() async =>
      List<ConfirmationRequest>.generate(
        pendingCount,
        (int i) => ConfirmationRequest(
          id: 'r$i',
          contributionId: 'c$i',
          projectId: 'p1',
          requestedBy: 'u2',
          reviewerId: 'u1',
        ),
      );

  @override
  Future<Map<String, dynamic>> getProjectDetails(String projectId) async => <String, dynamic>{
        'project': <String, dynamic>{
          'project_members': <Map<String, dynamic>>[
            <String, dynamic>{'profiles': <String, dynamic>{'display_name': 'Sam K'}},
            <String, dynamic>{'profiles': <String, dynamic>{'display_name': 'Veekshith K'}},
          ],
        },
      };

  @override
  Future<List<Contribution>> listContributions(
    String projectId, {
    String? status,
    String? contributor,
    String? category,
  }) async =>
      <Contribution>[];
}
