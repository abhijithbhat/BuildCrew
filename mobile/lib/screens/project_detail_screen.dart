import 'package:flutter/material.dart';

class ProjectDetailScreen extends StatelessWidget {
  static const String routeName = '/project-detail';

  const ProjectDetailScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Project Detail'),
      ),
      body: const Center(
        child: Text('Project Detail Screen Placeholder'),
      ),
    );
  }
}
