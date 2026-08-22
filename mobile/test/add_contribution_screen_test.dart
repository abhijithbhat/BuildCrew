import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/contribution.dart';
import 'package:mobile/screens/add_contribution_screen.dart';
import 'package:mobile/services/project_service.dart';
import 'package:mobile/services/storage_service.dart';

class MockProjectService extends ProjectService {
  Map<String, dynamic>? lastUploadedFile;
  Map<String, dynamic>? lastContributionPayload;
  bool shouldThrowOnUpload = false;
  bool shouldThrowOnAdd = false;

  @override
  Future<Map<String, dynamic>> uploadEvidenceFile({
    required List<int> fileBytes,
    required String fileName,
    String? projectId,
  }) async {
    if (shouldThrowOnUpload) {
      throw 'Storage upload failed. Please try again.';
    }
    lastUploadedFile = {
      'fileName': fileName,
      'fileBytes': fileBytes,
      'projectId': projectId,
    };
    return {
      'url': 'https://storage.supabase.co/evidence/user-1/$fileName',
      'filename': fileName,
      'file_type': 'image/png',
      'size_bytes': fileBytes.length,
      'storage_path': 'evidence/user-1/$fileName',
    };
  }

  @override
  Future<Contribution> addContribution({
    required String projectId,
    required String title,
    String? category,
    String? description,
    String? evidenceLink,
    String? dateRange,
    String? sourceType,
    String? visibility,
  }) async {
    if (shouldThrowOnAdd) {
      throw 'Failed to create contribution record.';
    }
    lastContributionPayload = {
      'projectId': projectId,
      'title': title,
      'category': category,
      'description': description,
      'evidenceLink': evidenceLink,
      'dateRange': dateRange,
      'sourceType': sourceType,
      'visibility': visibility,
    };
    return Contribution(
      id: 'mock-contrib-1',
      contributor: 'user-1',
      project: projectId,
      title: title,
      category: category,
      description: description,
      evidenceLink: evidenceLink,
      dateRange: dateRange,
      sourceType: sourceType ?? 'manual',
      verificationStatus: 'self-declared',
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
  }
}

class FakeStorageService extends StorageService {
  final Map<String, String?> _store = {};

  @override
  Future<void> saveContributionDraft({
    required String projectId,
    String? title,
    String? category,
    String? description,
    String? link,
  }) async {
    _store['projectId'] = projectId;
    _store['title'] = title;
    _store['category'] = category;
    _store['description'] = description;
    _store['link'] = link;
  }

  @override
  Future<Map<String, String?>> getContributionDraft() async {
    if (_store['projectId'] == null) return {};
    return Map.from(_store);
  }

  @override
  Future<void> clearContributionDraft() async {
    _store.clear();
  }
}

void main() {
  late MockProjectService mockProjectService;
  late FakeStorageService fakeStorageService;

  setUp(() {
    mockProjectService = MockProjectService();
    fakeStorageService = FakeStorageService();
  });

  Widget buildTestWidget({String? projectId, ProjectService? service, StorageService? storage}) {
    return MaterialApp(
      home: AddContributionScreen(
        projectId: projectId ?? 'test-proj-123',
        projectService: service ?? mockProjectService,
        storageService: storage ?? fakeStorageService,
      ),
    );
  }

  group('AddContributionScreen Widget Layout Tests', () {
    testWidgets('renders all required form fields, category dropdown, inputs, and submit button', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Header title
      expect(find.text('Add Contribution'), findsOneWidget);
      expect(find.text('Manual Impact Logging'), findsOneWidget);

      // 1. Category Dropdown
      expect(find.byKey(const Key('add_contribution_category_dropdown')), findsOneWidget);
      expect(find.text('UI/UX Design'), findsOneWidget);

      // 2. Title field
      expect(find.byKey(const Key('add_contribution_title_input')), findsOneWidget);
      expect(find.text('Contribution Title *'), findsOneWidget);

      // 3. Description field
      expect(find.byKey(const Key('add_contribution_description_input')), findsOneWidget);
      expect(find.text('Description & Deliverables'), findsOneWidget);

      // 4. Evidence Link & File Picker
      expect(find.byKey(const Key('add_contribution_link_input')), findsOneWidget);
      expect(find.byKey(const Key('add_contribution_file_picker')), findsOneWidget);
      expect(find.text('Tap to attach Screenshot, PDF, or Document'), findsOneWidget);

      // 5. Submit Button
      expect(find.byKey(const Key('add_contribution_submit_btn')), findsOneWidget);
      expect(find.text('Log Contribution'), findsOneWidget);
    });

    testWidgets('validates required title field ONLY upon submit button tap', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Before tapping submit, no error message is displayed
      expect(find.text('Contribution title is required.'), findsNothing);

      // Ensure submit button is visible and tap it
      await tester.ensureVisible(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();

      // Now validation error appears
      expect(find.text('Contribution title is required.'), findsOneWidget);
    });

    testWidgets('allows selecting different category from dropdown', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Tap dropdown to open menu
      await tester.tap(find.byKey(const Key('add_contribution_category_dropdown')));
      await tester.pumpAndSettle();

      // Select 'DevOps & Infrastructure'
      expect(find.text('DevOps & Infrastructure').last, findsOneWidget);
      await tester.tap(find.text('DevOps & Infrastructure').last);
      await tester.pumpAndSettle();

      // Verify category updated
      expect(find.text('DevOps & Infrastructure'), findsOneWidget);
    });

    testWidgets('opens evidence attachment sheet and displays real device file upload options', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Scroll to file picker zone and tap
      await tester.ensureVisible(find.byKey(const Key('add_contribution_file_picker')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_contribution_file_picker')));
      await tester.pumpAndSettle();

      // Verify bottom sheet opened with all real device options
      expect(find.text('Attach Evidence File'), findsOneWidget);
      expect(find.text('Upload PDF / Specification Document'), findsOneWidget);
      expect(find.text('Upload Presentation Slides (PPT / PPTX / PDF)'), findsOneWidget);
      expect(find.text('Upload Screenshot / Image (Photo Gallery)'), findsOneWidget);
      expect(find.text('Browse All Device Files'), findsOneWidget);
      expect(find.text('Take Photo with Camera'), findsOneWidget);
    });

    testWidgets('previews attached file and allows removing it', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AddContributionScreen(
            projectId: 'test-proj-123',
            projectService: mockProjectService,
            storageService: fakeStorageService,
            initialAttachedFileName: 'specification_document.pdf',
            initialAttachedFileType: 'application/pdf',
            initialAttachedFileSize: 860160,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Scroll to file picker box
      await tester.ensureVisible(find.byKey(const Key('add_contribution_file_picker')));
      await tester.pumpAndSettle();

      // Verify file preview card rendered
      expect(find.text('specification_document.pdf'), findsOneWidget);
      expect(find.textContaining('Attached file ready for upload'), findsOneWidget);

      // Clear attachment
      expect(find.byIcon(Icons.delete_outline_rounded), findsOneWidget);
      await tester.tap(find.byIcon(Icons.delete_outline_rounded));
      await tester.pumpAndSettle();

      // Scroll to file picker box and verify back to empty picker box
      await tester.ensureVisible(find.byKey(const Key('add_contribution_file_picker')));
      await tester.pumpAndSettle();
      expect(find.text('Tap to attach Screenshot, PDF, or Document'), findsOneWidget);
    });

    testWidgets('shows error alert banner if project ID is missing upon submit', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AddContributionScreen(
            projectId: null,
            projectService: mockProjectService,
            storageService: fakeStorageService,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Enter valid title
      await tester.enterText(
        find.byKey(const Key('add_contribution_title_input')),
        'Test Valid Title',
      );
      await tester.pumpAndSettle();

      // Tap submit
      await tester.ensureVisible(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();

      // Verify error alert banner shown
      expect(find.text('Project ID is missing. Please select a project first.'), findsOneWidget);
    });
  });

  group('AddContributionScreen Wiring & Integration Tests (Step 4)', () {
    testWidgets('submits valid manual contribution with direct evidence link and triggers addContribution', (tester) async {
      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // 1. Enter title
      await tester.enterText(
        find.byKey(const Key('add_contribution_title_input')),
        'Created User Research Report',
      );

      // 2. Enter description
      await tester.enterText(
        find.byKey(const Key('add_contribution_description_input')),
        'Synthesized 15 user interviews on mobile friction points.',
      );

      // 3. Enter direct evidence link
      await tester.enterText(
        find.byKey(const Key('add_contribution_link_input')),
        'https://docs.google.com/document/d/report123',
      );

      // 4. Tap submit
      await tester.ensureVisible(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();

      // Verify addContribution called with exact payload
      expect(mockProjectService.lastContributionPayload, isNotNull);
      expect(mockProjectService.lastContributionPayload!['projectId'], 'test-proj-123');
      expect(mockProjectService.lastContributionPayload!['title'], 'Created User Research Report');
      expect(mockProjectService.lastContributionPayload!['category'], 'design');
      expect(mockProjectService.lastContributionPayload!['description'], 'Synthesized 15 user interviews on mobile friction points.');
      expect(mockProjectService.lastContributionPayload!['evidenceLink'], 'https://docs.google.com/document/d/report123');
      expect(mockProjectService.lastContributionPayload!['sourceType'], 'manual');
    });

    testWidgets('uploads attached evidence file first, then creates contribution record with resulting URL', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AddContributionScreen(
            projectId: 'test-proj-123',
            projectService: mockProjectService,
            storageService: fakeStorageService,
            initialAttachedFileName: 'mockup_preview.png',
            initialAttachedFileType: 'image/png',
            initialAttachedFileSize: 1468006,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. Enter title
      await tester.enterText(
        find.byKey(const Key('add_contribution_title_input')),
        'Figma Design System Architecture',
      );

      // 2. Tap submit
      await tester.ensureVisible(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();

      // Verify upload was executed first
      expect(mockProjectService.lastUploadedFile, isNotNull);
      expect(mockProjectService.lastUploadedFile!['fileName'], 'mockup_preview.png');
      expect(mockProjectService.lastUploadedFile!['projectId'], 'test-proj-123');

      // Verify addContribution was executed with uploaded URL
      expect(mockProjectService.lastContributionPayload, isNotNull);
      expect(
        mockProjectService.lastContributionPayload!['evidenceLink'],
        'https://storage.supabase.co/evidence/user-1/mockup_preview.png',
      );
    });

    testWidgets('displays error alert banner when uploadEvidenceFile throws', (tester) async {
      mockProjectService.shouldThrowOnUpload = true;

      await tester.pumpWidget(
        MaterialApp(
          home: AddContributionScreen(
            projectId: 'test-proj-123',
            projectService: mockProjectService,
            storageService: fakeStorageService,
            initialAttachedFileName: 'mockup_preview.png',
            initialAttachedFileType: 'image/png',
            initialAttachedFileSize: 1468006,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Enter title
      await tester.enterText(
        find.byKey(const Key('add_contribution_title_input')),
        'Failing Upload Contribution',
      );

      // Tap submit
      await tester.ensureVisible(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();

      // Verify error banner
      expect(find.textContaining('Storage upload failed'), findsOneWidget);
    });

    testWidgets('displays error alert banner when addContribution throws', (tester) async {
      mockProjectService.shouldThrowOnAdd = true;

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      // Enter title
      await tester.enterText(
        find.byKey(const Key('add_contribution_title_input')),
        'Failing Add Contribution',
      );

      // Tap submit
      await tester.ensureVisible(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_contribution_submit_btn')));
      await tester.pumpAndSettle();

      // Verify error banner
      expect(find.textContaining('Failed to create contribution record'), findsOneWidget);
    });
  });
}
