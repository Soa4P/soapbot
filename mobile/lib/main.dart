import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api/client.dart';
import 'screens/login_screen.dart';
import 'screens/sessions_screen.dart';
import 'theme.dart';

/// Base URL of the panel. Override at build time:
/// `flutter build apk --dart-define=SOAPBOT_BASE_URL=https://example.com`
const baseUrl = String.fromEnvironment('SOAPBOT_BASE_URL', defaultValue: 'http://127.0.0.1:16700');

void main() => runApp(const SoapbotArchiveApp());

class SoapbotArchiveApp extends StatefulWidget {
  const SoapbotArchiveApp({super.key});

  @override
  State<SoapbotArchiveApp> createState() => _SoapbotArchiveAppState();
}

class _SoapbotArchiveAppState extends State<SoapbotArchiveApp> {
  static const _storage = FlutterSecureStorage();
  static const _cookieKey = 'soapbot.session';

  final _api = ChatApi(baseUrl: baseUrl);
  Account? _account;
  bool _restoring = true;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  /// A stored cookie is a hint, not a login: it is verified against `/me` so a
  /// revoked account lands on the form instead of an empty list.
  Future<void> _restore() async {
    try {
      final cookie = await _storage.read(key: _cookieKey);
      if (cookie != null && cookie.isNotEmpty) {
        _api.restoreCookie(cookie);
        final account = await _api.me();
        if (mounted) setState(() => _account = account);
      }
    } catch (_) {
      await _storage.delete(key: _cookieKey);
      _api.restoreCookie(null);
    } finally {
      if (mounted) setState(() => _restoring = false);
    }
  }

  Future<void> _signedIn(Account account) async {
    final cookie = _api.cookie;
    if (cookie != null) await _storage.write(key: _cookieKey, value: cookie);
    if (mounted) setState(() => _account = account);
  }

  Future<void> _signOut() async {
    await _storage.delete(key: _cookieKey);
    _api.restoreCookie(null);
    if (mounted) setState(() => _account = null);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Soapbot 存档',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: _restoring
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _account == null
              ? LoginScreen(api: _api, onSignedIn: _signedIn)
              : SessionsScreen(api: _api, accountId: _account!.id, onSignOut: _signOut),
    );
  }
}
