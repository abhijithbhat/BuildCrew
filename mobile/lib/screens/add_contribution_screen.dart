import 'dart:typed_data';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/project_service.dart';
import '../services/storage_service.dart';

class AddContributionScreen extends StatefulWidget {
  static const String routeName = '/add-contribution';

  final String? projectId;
  final ProjectService? projectService;
  final StorageService? storageService;
  final VoidCallback? onContributionAdded;
  final String? initialAttachedFileName;
  final String? initialAttachedFileType;
  final int? initialAttachedFileSize;
  final Uint8List? initialAttachedFileBytes;

  const AddContributionScreen({
    super.key,
    this.projectId,
    this.projectService,
    this.storageService,
    this.onContributionAdded,
    this.initialAttachedFileName,
    this.initialAttachedFileType,
    this.initialAttachedFileSize,
    this.initialAttachedFileBytes,
  });

  @override
  State<AddContributionScreen> createState() => _AddContributionScreenState();
}

class _AddContributionScreenState extends State<AddContributionScreen> {
  final _formKey = GlobalKey<FormState>();

  late final ProjectService _projectService;
  late final StorageService _storageService;
  late final TextEditingController _titleController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _linkController;

  String? _selectedCategory = 'design';
  DateTime _selectedDate = DateTime.now();
  String? _attachedFileName;
  String? _attachedFileType;
  int? _attachedFileSize;
  Uint8List? _attachedFileBytes;

  bool _isLoading = false;
  String? _errorMessage;
  String? _resolvedProjectId;

  static const List<Map<String, dynamic>> _categories = [
    {
      'id': 'design',
      'label': 'UI/UX Design',
      'icon': Icons.palette_outlined,
      'color': Color(0xFF8B5CF6),
      'examples': 'Figma mockups, wireframes, user journeys, design systems',
    },
    {
      'id': 'research',
      'label': 'User & Market Research',
      'icon': Icons.biotech_outlined,
      'color': Color(0xFF06B6D4),
      'examples': 'User interview summaries, competitor analysis, surveys',
    },
    {
      'id': 'documentation',
      'label': 'Documentation & Specs',
      'icon': Icons.description_outlined,
      'color': Color(0xFF3B82F6),
      'examples': 'Architecture specs, API guides, READMEs, Notion wikis',
    },
    {
      'id': 'presentation',
      'label': 'Pitch & Slide Decks',
      'icon': Icons.slideshow_outlined,
      'color': Color(0xFFEC4899),
      'examples': 'Demo day slides, investor decks, roadmap presentations',
    },
    {
      'id': 'devops',
      'label': 'DevOps & Infrastructure',
      'icon': Icons.cloud_sync_outlined,
      'color': Color(0xFF10B981),
      'examples': 'CI/CD pipelines, Docker setups, cloud deployment, monitoring',
    },
    {
      'id': 'testing',
      'label': 'Testing & QA',
      'icon': Icons.verified_outlined,
      'color': Color(0xFFF59E0B),
      'examples': 'Test plans, manual QA test runs, bug triage reports',
    },
    {
      'id': 'code',
      'label': 'Custom Code & Scripts',
      'icon': Icons.code_rounded,
      'color': Color(0xFF6366F1),
      'examples': 'Utility scripts, data processing, external integrations',
    },
    {
      'id': 'other',
      'label': 'Other Impact',
      'icon': Icons.stars_rounded,
      'color': Color(0xFF64748B),
      'examples': 'Project management, meetings, stakeholder coordination',
    },
  ];

  @override
  void initState() {
    super.initState();
    _projectService = widget.projectService ?? ProjectService();
    _storageService = widget.storageService ?? StorageService();
    _titleController = TextEditingController();
    _descriptionController = TextEditingController();
    _linkController = TextEditingController();
    _resolvedProjectId = widget.projectId;
    if (widget.initialAttachedFileName != null) {
      _attachedFileName = widget.initialAttachedFileName;
      _attachedFileType = widget.initialAttachedFileType ?? 'application/pdf';
      _attachedFileSize = widget.initialAttachedFileSize ?? 860160;
      _attachedFileBytes = widget.initialAttachedFileBytes ?? Uint8List.fromList(widget.initialAttachedFileName!.codeUnits);
    }
    _restoreDraftIfAvailable();
    _retrieveLostData();
  }

  Future<void> _restoreDraftIfAvailable() async {
    try {
      final draft = await _storageService.getContributionDraft();
      if (draft.isNotEmpty && mounted) {
        setState(() {
          if ((_resolvedProjectId == null || _resolvedProjectId!.isEmpty) && draft['projectId'] != null) {
            _resolvedProjectId = draft['projectId'];
          }
          if (_titleController.text.isEmpty && draft['title'] != null && draft['title']!.isNotEmpty) {
            _titleController.text = draft['title']!;
          }
          if (draft['category'] != null && draft['category']!.isNotEmpty) {
            _selectedCategory = draft['category']!;
          }
          if (_descriptionController.text.isEmpty && draft['description'] != null && draft['description']!.isNotEmpty) {
            _descriptionController.text = draft['description']!;
          }
          if (_linkController.text.isEmpty && draft['link'] != null && draft['link']!.isNotEmpty) {
            _linkController.text = draft['link']!;
          }
        });
      }
    } catch (_) {
      // Ignore draft read failure
    }
  }

  Future<void> _retrieveLostData() async {
    try {
      final picker = ImagePicker();
      final LostDataResponse response = await picker.retrieveLostData();
      if (response.isEmpty || response.file == null) return;
      final file = response.file!;
      final bytes = await file.readAsBytes();
      final name = file.name;
      final ext = name.contains('.') ? name.split('.').last.toLowerCase() : 'jpg';
      final mimeType = ext == 'png' ? 'image/png' : 'image/jpeg';
      if (mounted) {
        setState(() {
          _attachedFileName = name;
          _attachedFileType = mimeType;
          _attachedFileSize = bytes.length;
          _attachedFileBytes = bytes;
        });
      }
    } catch (_) {
      // Ignore recovery error
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_resolvedProjectId == null) {
      final args = ModalRoute.of(context)?.settings.arguments;
      if (args is Map<String, dynamic> && args['projectId'] != null) {
        _resolvedProjectId = args['projectId'].toString();
      } else if (args is String) {
        _resolvedProjectId = args;
      }
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    _linkController.dispose();
    super.dispose();
  }

  Future<void> _pickDeviceImage(BuildContext modalCtx, {ImageSource source = ImageSource.gallery}) async {
    Navigator.pop(modalCtx);
    try {
      if (_resolvedProjectId != null && _resolvedProjectId!.isNotEmpty) {
        await _storageService.saveContributionDraft(
          projectId: _resolvedProjectId!,
          title: _titleController.text,
          category: _selectedCategory,
          description: _descriptionController.text,
          link: _linkController.text,
        );
      }
      final picker = ImagePicker();
      final picked = await picker.pickImage(
        source: source,
        maxWidth: 1920,
        maxHeight: 1920,
        imageQuality: 85,
      );
      if (picked != null) {
        final bytes = await picked.readAsBytes();
        final name = picked.name;
        final extension = name.contains('.') ? name.split('.').last.toLowerCase() : 'png';
        final mimeType = extension == 'jpg' || extension == 'jpeg' ? 'image/jpeg' : 'image/png';
        setState(() {
          _attachedFileName = name;
          _attachedFileType = mimeType;
          _attachedFileSize = bytes.length;
          _attachedFileBytes = bytes;
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Could not select image: $e'),
            backgroundColor: Colors.red.shade700,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  Future<void> _pickDeviceDocument(
    BuildContext modalCtx, {
    List<String>? extensions,
    String label = 'Documents',
  }) async {
    Navigator.pop(modalCtx);
    try {
      final XTypeGroup typeGroup = XTypeGroup(
        label: label,
        extensions: extensions,
      );
      final XFile? file = await openFile(
        acceptedTypeGroups: extensions != null ? [typeGroup] : const [],
      );
      if (file != null) {
        final bytes = await file.readAsBytes();
        final name = file.name;
        final ext = name.contains('.') ? name.split('.').last.toLowerCase() : '';
        String mimeType = 'application/octet-stream';
        if (ext == 'pdf') {
          mimeType = 'application/pdf';
        } else if (ext == 'pptx' || ext == 'ppt') {
          mimeType = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
        } else if (ext == 'png') {
          mimeType = 'image/png';
        } else if (ext == 'jpg' || ext == 'jpeg') {
          mimeType = 'image/jpeg';
        } else if (ext == 'doc' || ext == 'docx') {
          mimeType = 'application/msword';
        } else if (ext == 'txt' || ext == 'md') {
          mimeType = 'text/plain';
        }

        setState(() {
          _attachedFileName = name;
          _attachedFileType = mimeType;
          _attachedFileSize = bytes.length;
          _attachedFileBytes = bytes;
        });
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Could not select document: $e'),
            backgroundColor: Colors.red.shade700,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  void _clearAttachment() {
    setState(() {
      _attachedFileName = null;
      _attachedFileType = null;
      _attachedFileSize = null;
      _attachedFileBytes = null;
    });
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate,
      firstDate: now.subtract(const Duration(days: 365)),
      lastDate: now.add(const Duration(days: 30)),
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: Color(0xFF2563EB),
              surface: Color(0xFF151C2C),
              onSurface: Colors.white,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() {
        _selectedDate = picked;
      });
    }
  }

  void _showAttachmentOptions() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF151C2C),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Attach Evidence File',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded, color: Colors.white70),
                    onPressed: () => Navigator.pop(ctx),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              const Text(
                'Upload real files from your device storage or gallery:',
                style: TextStyle(fontSize: 13, color: Color(0xFF94A3B8)),
              ),
              const SizedBox(height: 16),

              // 1. Real Device PDF / Specification Document Picker
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF3B82F6).withAlpha(35),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.picture_as_pdf_outlined, color: Color(0xFF3B82F6)),
                ),
                title: const Text(
                  'Upload PDF / Specification Document',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                ),
                subtitle: const Text(
                  'Select PDF, DOC, DOCX, TXT from device files',
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12),
                ),
                trailing: const Icon(Icons.chevron_right_rounded, color: Colors.white54),
                onTap: () => _pickDeviceDocument(
                  ctx,
                  extensions: ['pdf', 'doc', 'docx', 'txt', 'md'],
                  label: 'PDF & Spec Documents',
                ),
              ),

              // 2. Real Device Presentation Slides (PPT / PPTX / PDF) Picker
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEC4899).withAlpha(35),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.slideshow_outlined, color: Color(0xFFEC4899)),
                ),
                title: const Text(
                  'Upload Presentation Slides (PPT / PPTX / PDF)',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                ),
                subtitle: const Text(
                  'Select PPTX, PPT, or PDF slide deck from device',
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12),
                ),
                trailing: const Icon(Icons.chevron_right_rounded, color: Colors.white54),
                onTap: () => _pickDeviceDocument(
                  ctx,
                  extensions: ['pptx', 'ppt', 'pdf', 'key'],
                  label: 'Presentation Slide Decks',
                ),
              ),

              // 3. Real Device Screenshot / Image Picker
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF8B5CF6).withAlpha(35),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.photo_library_outlined, color: Color(0xFF8B5CF6)),
                ),
                title: const Text(
                  'Upload Screenshot / Image (Photo Gallery)',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                ),
                subtitle: const Text(
                  'Choose real screenshot, mockup, or PNG/JPG image',
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12),
                ),
                trailing: const Icon(Icons.chevron_right_rounded, color: Colors.white54),
                onTap: () => _pickDeviceImage(ctx, source: ImageSource.gallery),
              ),

              // 4. Real Device Browse All Files
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF10B981).withAlpha(35),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.folder_open_outlined, color: Color(0xFF10B981)),
                ),
                title: const Text(
                  'Browse All Device Files',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                ),
                subtitle: const Text(
                  'Pick any file or document from device storage (up to 25MB)',
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12),
                ),
                trailing: const Icon(Icons.chevron_right_rounded, color: Colors.white54),
                onTap: () => _pickDeviceDocument(
                  ctx,
                  extensions: null,
                  label: 'All Files',
                ),
              ),

              // 5. Camera Capture
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF59E0B).withAlpha(35),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.camera_alt_outlined, color: Color(0xFFF59E0B)),
                ),
                title: const Text(
                  'Take Photo with Camera',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                ),
                subtitle: const Text(
                  'Capture whiteboard notes, specs, or sketches',
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12),
                ),
                trailing: const Icon(Icons.chevron_right_rounded, color: Colors.white54),
                onTap: () => _pickDeviceImage(ctx, source: ImageSource.camera),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _handleSubmit() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    if (!_formKey.currentState!.validate()) {
      setState(() {
        _isLoading = false;
      });
      return;
    }

    if (_resolvedProjectId == null || _resolvedProjectId!.trim().isEmpty) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Project ID is missing. Please select a project first.';
      });
      return;
    }

    try {
      String? finalEvidenceLink = _linkController.text.trim().isNotEmpty
          ? _linkController.text.trim()
          : null;

      // 1. Upload attached evidence file if provided
      if (_attachedFileBytes != null && _attachedFileName != null) {
        final uploadResult = await _projectService.uploadEvidenceFile(
          fileBytes: _attachedFileBytes!,
          fileName: _attachedFileName!,
          projectId: _resolvedProjectId,
        );
        final uploadedUrl = uploadResult['url']?.toString();
        if (uploadedUrl != null && uploadedUrl.isNotEmpty) {
          finalEvidenceLink = uploadedUrl;
        }
      }

      // 2. Format contribution date
      final dateStr =
          '${_selectedDate.year}-${_selectedDate.month.toString().padLeft(2, '0')}-${_selectedDate.day.toString().padLeft(2, '0')}';

      // 3. Create contribution record via backend API
      final createdContrib = await _projectService.addContribution(
        projectId: _resolvedProjectId!,
        title: _titleController.text.trim(),
        category: _selectedCategory ?? 'other',
        description: _descriptionController.text.trim().isNotEmpty
            ? _descriptionController.text.trim()
            : null,
        evidenceLink: finalEvidenceLink,
        dateRange: dateStr,
        sourceType: 'manual',
      );

      await _storageService.clearContributionDraft();
      widget.onContributionAdded?.call();

      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });

      if (Navigator.of(context).canPop()) {
        Navigator.of(context).pop(createdContrib);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) {
          _storageService.clearContributionDraft();
        }
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF0B0F19),
        appBar: AppBar(
        backgroundColor: const Color(0xFF151C2C),
        elevation: 0,
        centerTitle: false,
        title: const Row(
          children: [
            Icon(Icons.add_task_rounded, color: Color(0xFF2563EB), size: 22),
            SizedBox(width: 10),
            Text(
              'Add Contribution',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 18,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.close_rounded, color: Colors.white70),
            onPressed: () => Navigator.of(context).maybePop(),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
          child: Form(
            key: _formKey,
            autovalidateMode: AutovalidateMode.disabled,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Error Alert Banner
                if (_errorMessage != null) ...[
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    decoration: BoxDecoration(
                      color: Colors.red.shade900.withAlpha(50),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: Colors.red.shade600, width: 1),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.error_outline_rounded, color: Colors.redAccent, size: 20),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _errorMessage!,
                            style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                ],

                // Intro Guidance Card
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF151C2C),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: const Color(0xFF1E293B)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF2563EB).withAlpha(40),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.verified_user_outlined,
                          color: Color(0xFF3B82F6),
                          size: 20,
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Manual Impact Logging',
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                fontSize: 14,
                              ),
                            ),
                            SizedBox(height: 4),
                            Text(
                              'Log non-code contributions (UI/UX, specs, user research, pitch decks). Manual entries start as Self-Declared and appear in the stream for peer verification.',
                              style: TextStyle(
                                color: Color(0xFF94A3B8),
                                fontSize: 12,
                                height: 1.4,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 22),

                // 1. Category Selection
                const Text(
                  'Contribution Category *',
                  style: TextStyle(
                    color: Color(0xFFE2E8F0),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF151C2C),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFF1E293B)),
                  ),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      key: const Key('add_contribution_category_dropdown'),
                      value: _selectedCategory,
                      isExpanded: true,
                      dropdownColor: const Color(0xFF151C2C),
                      icon: const Icon(Icons.keyboard_arrow_down_rounded, color: Colors.white70),
                      items: _categories.map((cat) {
                        return DropdownMenuItem<String>(
                          value: cat['id'] as String,
                          child: Row(
                            children: [
                              Icon(
                                cat['icon'] as IconData,
                                color: cat['color'] as Color,
                                size: 18,
                              ),
                              const SizedBox(width: 10),
                              Text(
                                cat['label'] as String,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                      onChanged: (val) {
                        setState(() {
                          _selectedCategory = val;
                        });
                      },
                    ),
                  ),
                ),
                const SizedBox(height: 20),

                // 2. Title Field
                const Text(
                  'Contribution Title *',
                  style: TextStyle(
                    color: Color(0xFFE2E8F0),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                TextFormField(
                  key: const Key('add_contribution_title_input'),
                  controller: _titleController,
                  style: const TextStyle(color: Colors.white, fontSize: 14),
                  decoration: InputDecoration(
                    hintText: 'e.g. Created high-fidelity Figma mockups for mobile onboarding',
                    hintStyle: const TextStyle(color: Color(0xFFB0BEC5), fontSize: 13),
                    filled: true,
                    fillColor: const Color(0xFF151C2C),
                    prefixIcon: const Icon(Icons.title_rounded, color: Color(0xFF64748B), size: 20),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: Color(0xFF1E293B)),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: Color(0xFF2563EB), width: 1.5),
                    ),
                    errorBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide(color: Colors.red.shade600),
                    ),
                    focusedErrorBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide(color: Colors.red.shade600, width: 1.5),
                    ),
                  ),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return 'Contribution title is required.';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 20),

                // 3. Description Field
                const Text(
                  'Description & Deliverables',
                  style: TextStyle(
                    color: Color(0xFFE2E8F0),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                TextFormField(
                  key: const Key('add_contribution_description_input'),
                  controller: _descriptionController,
                  style: const TextStyle(color: Colors.white, fontSize: 14),
                  minLines: 3,
                  maxLines: 6,
                  decoration: InputDecoration(
                    hintText: 'Detail what you accomplished, key tools used, and how it impacts the team...',
                    hintStyle: const TextStyle(color: Color(0xFFB0BEC5), fontSize: 13),
                    filled: true,
                    fillColor: const Color(0xFF151C2C),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: Color(0xFF1E293B)),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: Color(0xFF2563EB), width: 1.5),
                    ),
                  ),
                ),
                const SizedBox(height: 20),

                // 4. Evidence Attachment Section
                const Text(
                  'Evidence Link or Attachment',
                  style: TextStyle(
                    color: Color(0xFFE2E8F0),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),

                // URL Link Field
                TextFormField(
                  key: const Key('add_contribution_link_input'),
                  controller: _linkController,
                  style: const TextStyle(color: Colors.white, fontSize: 14),
                  keyboardType: TextInputType.url,
                  decoration: InputDecoration(
                    hintText: 'https://figma.com/file/... or https://docs.google.com/...',
                    hintStyle: const TextStyle(color: Color(0xFFB0BEC5), fontSize: 13),
                    filled: true,
                    fillColor: const Color(0xFF151C2C),
                    prefixIcon: const Icon(Icons.link_rounded, color: Color(0xFF64748B), size: 20),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: Color(0xFF1E293B)),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(color: Color(0xFF2563EB), width: 1.5),
                    ),
                  ),
                ),
                const SizedBox(height: 12),

                // File Attachment Picker Box
                InkWell(
                  key: const Key('add_contribution_file_picker'),
                  onTap: _showAttachmentOptions,
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    decoration: BoxDecoration(
                      color: const Color(0xFF151C2C),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: _attachedFileName != null
                            ? const Color(0xFF2563EB)
                            : const Color(0xFF1E293B),
                        width: _attachedFileName != null ? 1.5 : 1.0,
                      ),
                    ),
                    child: _attachedFileName != null
                        ? Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF2563EB).withAlpha(40),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: const Icon(
                                  Icons.attachment_rounded,
                                  color: Color(0xFF3B82F6),
                                  size: 20,
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      _attachedFileName!,
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontWeight: FontWeight.w600,
                                        fontSize: 13,
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      '${((_attachedFileSize ?? 0) / 1024).toStringAsFixed(1)} KB • ${_attachedFileType ?? "file"} • Attached file ready for upload',
                                      style: const TextStyle(
                                        color: Color(0xFF94A3B8),
                                        fontSize: 11,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              IconButton(
                                icon: const Icon(
                                  Icons.delete_outline_rounded,
                                  color: Colors.redAccent,
                                  size: 20,
                                ),
                                onPressed: _clearAttachment,
                              ),
                            ],
                          )
                        : const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                Icons.cloud_upload_outlined,
                                color: Color(0xFF64748B),
                                size: 22,
                              ),
                              SizedBox(width: 10),
                              Text(
                                'Tap to attach Screenshot, PDF, or Document',
                                style: TextStyle(
                                  color: Color(0xFF94A3B8),
                                  fontSize: 13,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
                const SizedBox(height: 20),

                // 5. Date Selection Tile
                Row(
                  children: [
                    const Text(
                      'Contribution Date: ',
                      style: TextStyle(
                        color: Color(0xFF94A3B8),
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(width: 8),
                    InkWell(
                      onTap: _pickDate,
                      borderRadius: BorderRadius.circular(8),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: const Color(0xFF151C2C),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFF1E293B)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.calendar_today_outlined,
                              color: Color(0xFF3B82F6),
                              size: 14,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              '${_selectedDate.year}-${_selectedDate.month.toString().padLeft(2, '0')}-${_selectedDate.day.toString().padLeft(2, '0')}',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 32),

                // 6. Action Buttons
                SizedBox(
                  width: double.infinity,
                  height: 50,
                  child: ElevatedButton(
                    key: const Key('add_contribution_submit_btn'),
                    onPressed: _isLoading ? null : _handleSubmit,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF2563EB),
                      foregroundColor: Colors.white,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.5,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.check_circle_outline_rounded, size: 20),
                              SizedBox(width: 8),
                              Text(
                                'Log Contribution',
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),);
  }
}
