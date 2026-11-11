import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme.dart';
import 'chat_screen.dart';

class SessionsScreen extends StatefulWidget {
  const SessionsScreen({super.key, required this.api, required this.onSignOut});

  final ChatApi api;
  final VoidCallback onSignOut;

  @override
  State<SessionsScreen> createState() => _SessionsScreenState();
}

class _SessionsScreenState extends State<SessionsScreen> {
  late Future<List<SessionRow>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.sessions();
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
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => ChatScreen(api: widget.api, session: row),
                    ),
                  ),
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
