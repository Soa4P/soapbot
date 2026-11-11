import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme.dart';
import 'note_sheet.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.api, required this.session});

  final ChatApi api;
  final SessionRow session;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  /// The web client uses SSE; on mobile the same `after_id` cursor is polled.
  ///
  /// The server's stream is itself a 1.5 s poll, so this is the same behaviour with
  /// one fewer socket — worth saying out loud rather than implying push delivery.
  static const _interval = Duration(seconds: 2);

  final _scroll = ScrollController();
  final List<Message> _messages = [];
  Timer? _timer;
  int _cursor = 0;
  bool _loading = true;
  bool _saving = false;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(_interval, (_) => _poll());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final rows = await widget.api.messages(widget.session.sessionKey, limit: 100);
      if (!mounted) return;
      setState(() {
        _messages
          ..clear()
          ..addAll(rows);
        _cursor = rows.isEmpty ? 0 : rows.last.id;
        _error = '';
      });
      _scrollToEnd();
    } on ApiException catch (err) {
      if (mounted) setState(() => _error = err.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _poll() async {
    if (_loading) return;
    try {
      final rows = await widget.api.messages(widget.session.sessionKey, afterId: _cursor);
      if (!mounted || rows.isEmpty) return;
      setState(() {
        _messages.addAll(rows);
        _cursor = rows.last.id;
      });
      _scrollToEnd();
    } on ApiException {
      // A failed poll is not worth a banner: the next tick replays the same cursor.
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _addNote() async {
    final text = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const NoteSheet(),
    );
    if (text == null || !mounted) return;
    setState(() => _saving = true);
    try {
      final note = await widget.api.note(widget.session.sessionKey, text);
      if (!mounted) return;
      setState(() {
        _messages.add(note);
        if (note.id > _cursor) _cursor = note.id;
      });
      _scrollToEnd();
    } on ApiException catch (err) {
      if (mounted) setState(() => _error = err.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.session.label),
            Text(widget.session.sessionKey,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 10, color: ink3)),
          ],
        ),
      ),
      body: Column(
        children: [
          Container(
            width: double.infinity,
            color: warnSoft,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            child: const Text('这里只记录，不发送。对方在 QQ 里看不到这些内容。',
                style: TextStyle(fontSize: 11, color: warn)),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _messages.isEmpty
                    ? const Center(
                        child: Text('这个会话还没有消息', style: TextStyle(color: ink3)))
                    : ListView.builder(
                        controller: _scroll,
                        padding: const EdgeInsets.all(14),
                        itemCount: _messages.length,
                        itemBuilder: (context, index) => _Bubble(message: _messages[index]),
                      ),
          ),
          if (_error.isNotEmpty)
            Container(
              width: double.infinity,
              color: dangerSoft,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              child: Text(_error, style: const TextStyle(fontSize: 11, color: danger)),
            ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _saving ? null : _addNote,
                      icon: const Icon(Icons.edit_note, size: 18),
                      label: Text(_saving ? '保存中…' : '写一条备注'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final mine = message.role == 'assistant';
    final note = message.isNote;
    final colour = note ? warnSoft : (mine ? const Color(0xFFEDF2FE) : surface);
    final line = note ? const Color(0xFFEFD8A8) : (mine ? const Color(0xFFCBDBFB) : border);
    final time = message.createdAt == 0
        ? ''
        : TimeOfDay.fromDateTime(
                DateTime.fromMillisecondsSinceEpoch((message.createdAt * 1000).round()))
            .format(context);

    return Align(
      alignment: note || mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82),
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.fromLTRB(12, 9, 12, 10),
        decoration: BoxDecoration(
          color: colour,
          border: Border.all(color: line),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(note ? '备注' : (mine ? '机器人' : (message.userName.isEmpty ? '对方' : message.userName)),
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: ink2)),
                if (note) ...[
                  const SizedBox(width: 6),
                  const Text('仅记录',
                      style: TextStyle(fontSize: 10, color: warn)),
                ],
                const Spacer(),
                Text(time, style: const TextStyle(fontSize: 10, color: ink3)),
              ],
            ),
            const SizedBox(height: 4),
            Text(message.content, style: const TextStyle(fontSize: 14, height: 1.5, color: ink)),
            if (message.imageDesc != null && message.imageDesc!.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(message.imageDesc!,
                  style: const TextStyle(fontSize: 11, color: ink3)),
            ],
          ],
        ),
      ),
    );
  }
}
