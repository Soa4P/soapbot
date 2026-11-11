import 'package:flutter/material.dart';

import '../theme.dart';

/// Bottom sheet for a note. It returns the text or null; it never sends anything.
class NoteSheet extends StatefulWidget {
  const NoteSheet({super.key});

  @override
  State<NoteSheet> createState() => _NoteSheetState();
}

class _NoteSheetState extends State<NoteSheet> {
  final _text = TextEditingController();

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('仅记录，不发送。对方在 QQ 里看不到这些内容。',
              style: TextStyle(fontSize: 11, color: warn)),
          const SizedBox(height: 10),
          TextField(
            controller: _text,
            autofocus: true,
            minLines: 3,
            maxLines: 6,
            maxLength: 4000,
            decoration: const InputDecoration(
              labelText: '备注',
              hintText: '写一条备注，仅保存到云端，不会发送到 QQ',
            ),
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: () {
              final value = _text.text.trim();
              if (value.isEmpty) return;
              Navigator.of(context).pop(value);
            },
            child: const Text('保存备注'),
          ),
        ],
      ),
    );
  }
}
