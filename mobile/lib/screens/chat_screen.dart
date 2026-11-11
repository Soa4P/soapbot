import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme.dart';
import 'note_sheet.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.api,
    required this.session,
    required this.accountId,
  });

  final ChatApi api;
  final SessionRow session;

  /// The signed-in account's id. The conversation session
  /// `web:private:account-<id>` belongs to exactly one account, so talk mode is
  /// derived from this, never from the session list alone.
  final int accountId;

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
  bool _loadingEarlier = false;
  bool _saving = false;
  bool _sending = false;
  bool _talkEnabled = false;
  bool _hasOlder = false;
  String _error = '';
  final TextEditingController _talkController = TextEditingController();

  bool get _isTalk =>
      _talkEnabled && widget.session.isWebTalk(widget.accountId.toString());

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(_interval, (_) => _poll());
    // One call, fire-and-forget: the flag only decides which composer is shown.
    widget.api.talkEnabled().then((enabled) {
      if (mounted) setState(() => _talkEnabled = enabled);
    }).catchError((_) {
      // degraded: an old backend without /surfaces still serves the archive;
      // the note composer stays, which is the safe default.
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scroll.dispose();
    _talkController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      // `latest`, not `after_id: 0`: the first screen of an old session must show the
      // newest page. The forward cursor answers "what arrived since N", the wrong
      // question for a session with months of history.
      final page = await widget.api.messages(widget.session.sessionKey, latest: true);
      if (!mounted) return;
      setState(() {
        _messages
          ..clear()
          ..addAll(page.messages);
        _cursor = page.messages.isEmpty ? 0 : page.messages.last.id;
        _hasOlder = page.hasOlder;
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
    if (_loading || _sending) return;
    try {
      final page = await widget.api.messages(widget.session.sessionKey, afterId: _cursor);
      if (!mounted || page.messages.isEmpty) return;
      setState(() {
        for (final row in page.messages) {
          if (row.id > _cursor) {
            _messages.add(row);
            _cursor = row.id;
          }
        }
      });
      _scrollToEnd();
    } on ApiException {
      // A failed poll is not worth a banner: the next tick replays the same cursor.
    }
  }

  Future<void> _loadEarlier() async {
    if (_loadingEarlier || _messages.isEmpty) return;
    setState(() => _loadingEarlier = true);
    final heightBefore = _scroll.hasClients ? _scroll.position.maxScrollExtent : 0.0;
    try {
      final page = await widget.api.messages(
        widget.session.sessionKey,
        beforeId: _messages.first.id,
      );
      if (!mounted) return;
      setState(() {
        _messages.insertAll(0, page.messages);
        _hasOlder = page.hasOlder;
      });
      if (!_scroll.hasClients) return;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_scroll.hasClients) return;
        // Keep the viewport anchored on the message the user was reading, not on
        // the list head: the prepend grew the extent by exactly the new content.
        _scroll.jumpTo(_scroll.position.maxScrollExtent - heightBefore);
      });
    } on ApiException catch (err) {
      if (mounted) setState(() => _error = err.message);
    } finally {
      if (mounted) setState(() => _loadingEarlier = false);
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

  Future<void> _sendTalk() async {
    final text = _talkController.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() {
      _sending = true;
      _error = '';
    });
    _talkController.clear();
    try {
      final reply = await widget.api.talk(text);
      // The pipeline archived both rows (the user message and the reply), so one
      // forward sync replaces the poll tick with the real rows in real order.
      final page = await widget.api.messages(widget.session.sessionKey, afterId: _cursor);
      if (!mounted) return;
      setState(() {
        for (final row in page.messages) {
          if (row.id > _cursor) {
            _messages.add(row);
            _cursor = row.id;
          }
        }
      });
      if (reply.isEmpty && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('机器人没有回复'), duration: Duration(seconds: 2)),
        );
      }
      _scrollToEnd();
    } on ApiException catch (err) {
      if (mounted) setState(() => _error = err.message);
    } finally {
      if (mounted) setState(() => _sending = false);
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
          if (!_isTalk)
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
                        itemCount: _messages.length + (_hasOlder ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (_hasOlder && index == 0) {
                            return Center(
                              child: TextButton(
                                onPressed: _loadingEarlier ? null : _loadEarlier,
                                child: Text(_loadingEarlier ? '正在读取更早的消息…' : '加载更早的消息'),
                              ),
                            );
                          }
                          final messageIndex = _hasOlder ? index - 1 : index;
                          return _Bubble(message: _messages[messageIndex]);
                        },
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
              child: _isTalk ? _talkComposer() : _noteButton(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _noteButton() {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: _saving ? null : _addNote,
            icon: const Icon(Icons.edit_note, size: 18),
            label: Text(_saving ? '保存中…' : '写一条备注'),
          ),
        ),
      ],
    );
  }

  Widget _talkComposer() {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _talkController,
            enabled: !_sending,
            maxLength: 4000,
            minLines: 1,
            maxLines: 4,
            textInputAction: TextInputAction.send,
            onSubmitted: (_) => _sendTalk(),
            style: const TextStyle(fontSize: 14, color: ink),
            decoration: const InputDecoration(
              hintText: '给机器人发一条消息，它会在这里回复你',
              counterText: '',
              isDense: true,
              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(10))),
            ),
          ),
        ),
        const SizedBox(width: 8),
        IconButton.filled(
          onPressed: _sending ? null : _sendTalk,
          icon: _sending
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.send, size: 18),
        ),
      ],
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
