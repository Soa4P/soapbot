import 'package:flutter/material.dart';

import '../api/client.dart';
import '../theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.api, required this.onSignedIn});

  final ChatApi api;
  final ValueChanged<Account> onSignedIn;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _invite = TextEditingController();
  bool _register = false;
  bool _busy = false;
  bool _obscure = true;
  String _error = '';

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    _invite.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final username = _username.text.trim();
    if (username.length < 3 || _password.text.length < 8) {
      setState(() => _error = '用户名至少 3 位，密码至少 8 位');
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final account = _register
          ? await widget.api.register(_invite.text.trim(), username, _password.text)
          : await widget.api.login(username, _password.text);
      if (!mounted) return;
      widget.onSignedIn(account);
    } on ApiException catch (err) {
      setState(() => _error = err.message);
    } catch (err) {
      setState(() => _error = '$err');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('SOAPBOT · ARCHIVE',
                      style: TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 11,
                          letterSpacing: 1.6,
                          color: brand)),
                  const SizedBox(height: 8),
                  Text('登录云端存档',
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w600, color: ink)),
                  const SizedBox(height: 6),
                  const Text('用账号查看被授权的会话。QQ 端不受影响，输入只保存备注。',
                      style: TextStyle(fontSize: 13, height: 1.5, color: ink3)),
                  const SizedBox(height: 20),
                  SegmentedButton<bool>(
                    segments: const [
                      ButtonSegment(value: false, label: Text('登录')),
                      ButtonSegment(value: true, label: Text('邀请注册')),
                    ],
                    selected: {_register},
                    onSelectionChanged: (value) => setState(() {
                      _register = value.first;
                      _error = '';
                    }),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _username,
                    autofillHints: const [AutofillHints.username],
                    decoration: const InputDecoration(labelText: '用户名'),
                  ),
                  const SizedBox(height: 12),
                  if (_register) ...[
                    TextField(
                      controller: _invite,
                      decoration: const InputDecoration(labelText: '邀请码'),
                    ),
                    const SizedBox(height: 12),
                  ],
                  TextField(
                    controller: _password,
                    obscureText: _obscure,
                    autofillHints: const [AutofillHints.password],
                    decoration: InputDecoration(
                      labelText: '密码',
                      suffixIcon: IconButton(
                        tooltip: _obscure ? '显示密码' : '隐藏密码',
                        icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    onSubmitted: (_) => _submit(),
                  ),
                  if (_error.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: dangerSoft,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFEDBFB8)),
                      ),
                      child: Text(_error, style: const TextStyle(fontSize: 12, color: danger)),
                    ),
                  ],
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(_register ? '注册并登录' : '登录'),
                  ),
                  const SizedBox(height: 12),
                  const Text('账号由所有者邀请创建，不开放自助注册。',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 11, color: ink3)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
