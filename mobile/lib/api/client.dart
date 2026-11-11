import 'dart:convert';

import 'package:http/http.dart' as http;

/// Result of a sign-in: the cookie is stored by the caller, the account is returned.
class Account {
  const Account({required this.id, required this.username, required this.role});

  final int id;
  final String username;
  final String role;

  factory Account.fromJson(Map<String, dynamic> json) => Account(
        id: (json['id'] as num).toInt(),
        username: json['username'] as String? ?? '',
        role: json['role'] as String? ?? 'member',
      );
}

class SessionRow {
  const SessionRow({
    required this.sessionKey,
    required this.messageCount,
    required this.lastAt,
  });

  final String sessionKey;
  final int messageCount;
  final double lastAt;

  factory SessionRow.fromJson(Map<String, dynamic> json) => SessionRow(
        sessionKey: json['session_key'] as String,
        messageCount: (json['message_count'] as num?)?.toInt() ?? 0,
        lastAt: (json['last_at'] as num?)?.toDouble() ?? 0,
      );

  /// `qq:group:123` reads as `群 123`; unknown shapes are shown verbatim.
  String get label {
    final parts = sessionKey.split(':');
    if (parts.length < 3) return sessionKey;
    final kind = parts[1];
    final id = parts.sublist(2).join(':');
    if (kind == 'group') return '群 $id';
    if (kind == 'private' || kind == 'c2c') return '私聊 $id';
    return sessionKey;
  }
}

class Message {
  const Message({
    required this.id,
    required this.sessionKey,
    required this.role,
    required this.content,
    required this.createdAt,
    this.userName = '',
    this.imageDesc,
  });

  final int id;
  final String sessionKey;
  final String role;
  final String content;
  final double createdAt;
  final String userName;
  final String? imageDesc;

  bool get isNote => role == 'note';

  factory Message.fromJson(Map<String, dynamic> json) => Message(
        id: (json['id'] as num).toInt(),
        sessionKey: json['session_key'] as String,
        role: json['role'] as String? ?? 'user',
        content: json['content'] as String? ?? '',
        createdAt: (json['created_at'] as num?)?.toDouble() ?? 0,
        userName: json['user_name'] as String? ?? '',
        imageDesc: json['image_desc'] as String?,
      );
}

class ApiException implements Exception {
  ApiException(this.status, this.message);

  final int status;
  final String message;

  bool get unauthorized => status == 401;

  @override
  String toString() => message;
}

/// Thin client for the same endpoints the web page uses.
///
/// The session is a cookie. `http` keeps cookies only if the caller passes a
/// [http.Client] that stores them, so the app supplies one and persists the cookie
/// value in secure storage rather than in shared preferences.
class ChatApi {
  ChatApi({required this.baseUrl, http.Client? client}) : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;
  String? _cookie;

  void restoreCookie(String? value) => _cookie = value;
  String? get cookie => _cookie;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (_cookie != null) 'Cookie': _cookie!,
      };

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final request = http.Request(method, uri)..headers.addAll(_headers);
    if (body != null) request.body = jsonEncode(body);
    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);
    _rememberCookie(response);
    final decoded = response.body.isEmpty ? <String, dynamic>{} : jsonDecode(response.body);
    if (response.statusCode >= 400) {
      final detail = decoded is Map && decoded['detail'] is String
          ? decoded['detail'] as String
          : 'HTTP ${response.statusCode}';
      throw ApiException(response.statusCode, detail);
    }
    return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
  }

  void _rememberCookie(http.Response response) {
    final raw = response.headers['set-cookie'];
    if (raw == null || raw.isEmpty) return;
    _cookie = raw.split(';').first;
  }

  Future<Account> login(String username, String password) async {
    final body = await _send('POST', '/api/accounts/login',
        body: {'username': username, 'password': password});
    return Account.fromJson(body['account'] as Map<String, dynamic>);
  }

  Future<Account> register(String invite, String username, String password) async {
    final body = await _send('POST', '/api/accounts/register',
        body: {'invite': invite, 'username': username, 'password': password});
    return Account.fromJson(body['account'] as Map<String, dynamic>);
  }

  Future<Account> me() async => Account.fromJson(await _send('GET', '/api/accounts/me'));

  Future<List<SessionRow>> sessions() async {
    final body = await _send('GET', '/api/chat/sessions');
    final rows = body['sessions'] as List<dynamic>? ?? const [];
    return rows.map((row) => SessionRow.fromJson(row as Map<String, dynamic>)).toList();
  }

  Future<List<Message>> messages(String sessionKey, {int afterId = 0, int limit = 100}) async {
    final query = Uri(queryParameters: {
      'session_key': sessionKey,
      'after_id': '$afterId',
      'limit': '$limit',
    }).query;
    final body = await _send('GET', '/api/chat/messages?$query');
    final rows = body['messages'] as List<dynamic>? ?? const [];
    return rows.map((row) => Message.fromJson(row as Map<String, dynamic>)).toList();
  }

  /// Saves a note. `delivered` is always false; the field exists so the UI can say so.
  Future<Message> note(String sessionKey, String content) async {
    final body = await _send('POST', '/api/chat/notes',
        body: {'session_key': sessionKey, 'content': content});
    return Message.fromJson(body['note'] as Map<String, dynamic>);
  }
}
