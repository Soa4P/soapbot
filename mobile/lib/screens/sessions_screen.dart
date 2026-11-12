import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme.dart';
import 'approvals_screen.dart';
import 'chat_screen.dart';

class SessionsScreen extends StatefulWidget {
  const SessionsScreen({
    super.key,
    required this.api,
    required this.accountId,
    required this.onSignOut,
  });

  final ChatApi api;

  /// Signed-in account id, handed to the chat screen so it can recognise the
  /// conversation session that belongs to this account.
  final int accountId;

  final VoidCallback onSignOut;

  @override
  State<SessionsScreen> createState() => _SessionsScreenState();
}

class _SessionsScreenState extends State<SessionsScreen> {
  late Future<List<SessionRow>> _future;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _future = widget.api.sessions();
    // The list is derived from the archive, so a new session exists only once it has
    // messages. Poll at the same pace the chat poll implies; pull-to-refresh stays.
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _reload());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() => _future = widget.api.sessions());
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('会话'),
        actions: [
          IconButton(
            tooltip: '审批',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => ApprovalsScreen(api: widget.api),
              ),
            ),
            icon: const Icon(Icons.fact_check_outlined),
          ),
          IconButton(
            tooltip: '退出登录',
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: FutureBuilder<List<SessionRow>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return _ErrorState(error: '${snapshot.error}', onRetry: _reload);
            }
            final rows = snapshot.data ?? const <SessionRow>[];
            if (rows.isEmpty) {
              return ListView(
                children: const [
                  SizedBox(height: 120),
                  Center(
                    child: Padding(
                      padding: EdgeInsets.symmetric(horizontal: 32),
                      child: Column(
                        children: [
                          Text('还没有被授权的会话',
                              style: TextStyle(fontWeight: FontWeight.w600, color: ink)),
                          SizedBox(height: 6),
                          Text('让所有者用邀请码或成员授权把会话分给你。',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 12, color: ink3)),
                        ],
                      ),
                    ),
                  ),
                ],
              );
            }
            return ListView.separated(
              itemCount: rows.length,
              separatorBuilder: (_, __) => const Divider(height: 1, color: border),
              itemBuilder: (context, index) {
                final row = rows[index];
                return ListTile(
                  title: Text(row.label, style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text(row.sessionKey,
                      style: const TextStyle(fontFamily: 'monospace', fontSize: 11, color: ink3)),
                  trailing: Text('${row.messageCount}',
                      style: const TextStyle(fontSize: 11, color: ink3)),
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => ChatScreen(
                          api: widget.api,
                          session: row,
                          accountId: widget.accountId,
                        ),
                      ),
                    );
                    // Back from a chat: the session may have grown or, for a first
                    // conversation, may not have existed when this list loaded.
                    if (mounted) await _reload();
                  },
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.error, required this.onRetry});

  final String error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 120),
        Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              children: [
                const Text('读取失败', style: TextStyle(fontWeight: FontWeight.w600, color: ink)),
                const SizedBox(height: 6),
                Text(error, textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: ink3)),
                const SizedBox(height: 12),
                OutlinedButton(onPressed: onRetry, child: const Text('重试')),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
