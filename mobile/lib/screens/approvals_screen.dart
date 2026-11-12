import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme.dart';

/// Approval inbox. Polls the same cursor feed a headless client would use, at a
/// slower pace than chat: a decision is not a conversation, and hammering the
/// panel for a queue that changes a few times a day would only drain the battery.
///
/// Only the newest event per request is shown. An approval that arrives after a
/// request replaces it rather than adding a second row — the ledger's state
/// machine makes `(request_id, kind)` unique, and the UI should say the same.
class ApprovalsScreen extends StatefulWidget {
  const ApprovalsScreen({super.key, required this.api});

  final ChatApi api;

  @override
  State<ApprovalsScreen> createState() => _ApprovalsScreenState();
}

class _ApprovalsScreenState extends State<ApprovalsScreen> {
  static const _pollEvery = Duration(seconds: 5);

  final Map<int, ApprovalEvent> _latest = {};
  Timer? _timer;
  int _cursor = 0;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_poll());
    _timer = Timer.periodic(_pollEvery, (_) => unawaited(_poll()));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _poll() async {
    try {
      final feed = await widget.api.approvals(after: _cursor);
      if (!mounted) return;
      setState(() {
        for (final event in feed.events) {
          _latest[event.requestId] = event;
        }
        _cursor = feed.cursor;
        _error = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '$error');
    }
  }

  Future<void> _decide(ApprovalEvent event, String kind) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await widget.api.decideApproval(event.requestId, kind, event.sessionKey);
      // The decision publishes its own event; poll once so the row changes state
      // without waiting for the next tick.
      await _poll();
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = _latest.values.toList()
      ..sort((a, b) => b.requestId.compareTo(a.requestId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('审批'),
        actions: [
          IconButton(
            tooltip: '刷新',
            onPressed: _busy ? null : () => unawaited(_poll()),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Column(
        children: [
          if (_error != null)
            Container(
              width: double.infinity,
              color: dangerSoft,
              padding: const EdgeInsets.all(12),
              child: Text(
                _error!,
                style: const TextStyle(color: danger),
              ),
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _poll,
              child: rows.isEmpty
                  ? ListView(
                      children: const [
                        SizedBox(height: 120),
                        Center(child: Text('还没有审批事件')),
                        SizedBox(height: 8),
                        Center(
                          child: Text(
                            '发起一笔消费申请后，这里会显示待批项。',
                            style: TextStyle(color: ink3),
                          ),
                        ),
                      ],
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: rows.length,
                      itemBuilder: (context, index) => _Card(
                        event: rows[index],
                        busy: _busy,
                        onDecide: _decide,
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.event, required this.busy, required this.onDecide});

  final ApprovalEvent event;
  final bool busy;
  final Future<void> Function(ApprovalEvent, String) onDecide;

  @override
  Widget build(BuildContext context) {
    final pending = event.isPending;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('#${event.requestId}', style: const TextStyle(color: ink3)),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: pending ? warnSoft : surface2,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    event.statusLabel,
                    style: TextStyle(color: pending ? warn : ink2, fontSize: 12),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              event.amountLabel,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: ink),
            ),
            const SizedBox(height: 4),
            Text(event.purpose.isEmpty ? '(未填用途)' : event.purpose,
                style: const TextStyle(color: ink2)),
            if (event.degraded)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text(
                  '已降级：允许自批，审批退化为确认框',
                  style: TextStyle(color: danger, fontSize: 12),
                ),
              ),
            if (pending) ...[
              const SizedBox(height: 10),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: busy ? null : () => unawaited(onDecide(event, 'deny')),
                    child: const Text('驳回', style: TextStyle(color: danger)),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: busy ? null : () => unawaited(onDecide(event, 'approve')),
                    child: const Text('批准'),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
