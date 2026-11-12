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

  bool isWebTalk(String accountId) => sessionKey == 'web:private:account-$accountId';
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

/// A history page plus whether even older messages exist.
///
/// `has_older` comes from a server-side existence probe, not from `length == limit`,
/// so a page ending exactly at the first message never leaves a dead "load earlier"
/// button on screen.
class MessagesPage {
  const MessagesPage({required this.messages, required this.hasOlder});

  final List<Message> messages;
  final bool hasOlder;
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
  String? _csrf;
  String? _token;
  static const _mutating = {'POST', 'PUT', 'PATCH', 'DELETE'};

  void restoreCookie(String? value) => _cookie = value;
  String? get cookie => _cookie;

  /// 登录返回的 Bearer token：服务端对 Bearer 请求豁免 CSRF（原生客户端没有
  /// 跨站页面可 attach header，无暴露面），所以 app 优先走 Bearer 而不是靠
  /// Cookie 过 double-submit——后者要求每次登录都重放 CSRF 值，升级安装
  /// （旧会话仍有效但 csrf 未存）会永远 403。
  void restoreToken(String? value) => _token = value;
  String? get token => _token;

  /// CSRF cookie 值：服务端 double-submit 要求变更请求回显它。HttpOnly 的会话
  /// Cookie 走 [cookie]，这个是刻意可读的那一枚。Bearer 存在时不需要它。
  void restoreCsrf(String? value) => _csrf = value;
  String? get csrf => _csrf;

  Map<String, String> _headersFor(String method) => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (_token != null) 'Authorization': 'Bearer ${_token!}',
        if (_token == null && _cookie != null) 'Cookie': _cookie!,
        if (_token == null &&
            _csrf != null &&
            _mutating.contains(method.toUpperCase()))
          'X-CSRF-Token': _csrf!,
      };

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final request = http.Request(method, uri)..headers.addAll(_headersFor(method));
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
    // 登录/轮换会同时下发会话与 CSRF 两枚 Cookie（httpx 会把多个 Set-Cookie
    // 合并进一个头）。会话 Cookie 原样回传；CSRF 值另存，变更请求时回显到
    // X-CSRF-Token——服务端是标准 double-submit 校验。
    final raw = response.headers['set-cookie'];
    if (raw == null || raw.isEmpty) return;
    final session = RegExp(r'soapbot_session=([^;,\s]+)').firstMatch(raw)?.group(1);
    final csrf = RegExp(r'soapbot_csrf=([^;,\s]+)').firstMatch(raw)?.group(1);
    if (session != null) _cookie = 'soapbot_session=$session';
    if (csrf != null) _csrf = csrf;
  }

  Future<Account> login(String username, String password) async {
    final body = await _send('POST', '/api/accounts/login',
        body: {'username': username, 'password': password});
    final token = body['access_token'];
    if (token is String && token.isNotEmpty) _token = token;
    return Account.fromJson(body['account'] as Map<String, dynamic>);
  }

  Future<Account> register(String invite, String username, String password) async {
    final body = await _send('POST', '/api/accounts/register',
        body: {'invite': invite, 'username': username, 'password': password});
    return Account.fromJson(body['account'] as Map<String, dynamic>);
  }

  Future<Account> me() async => Account.fromJson(await _send('GET', '/api/accounts/me'));

  /// Which client surfaces the deployment has on. `talk` gates the send box.
  Future<bool> talkEnabled() async {
    final body = await _send('GET', '/api/chat/surfaces');
    return body['talk'] == true;
  }

  Future<List<SessionRow>> sessions() async {
    final body = await _send('GET', '/api/chat/sessions');
    final rows = body['sessions'] as List<dynamic>? ?? const [];
    return rows.map((row) => SessionRow.fromJson(row as Map<String, dynamic>)).toList();
  }

  /// One paging mode per call — the server rejects combinations with 400.
  ///
  /// Default (`afterId: 0`) is the forward-sync contract used by the poll loop;
  /// [latest] fetches the newest page of an old session; [beforeId] is the
  /// "load earlier" cursor. The result is always ascending, plus [hasOlder].
  Future<MessagesPage> messages(
    String sessionKey, {
    int afterId = 0,
    int? beforeId,
    bool latest = false,
    int limit = 100,
  }) async {
    final params = {
      'session_key': sessionKey,
      'limit': '$limit',
      if (latest) 'latest': 'true',
      if (beforeId != null) 'before_id': '$beforeId',
      if (!latest && beforeId == null && afterId > 0) 'after_id': '$afterId',
    };
    final query = Uri(queryParameters: params).query;
    final body = await _send('GET', '/api/chat/messages?$query');
    final rows = body['messages'] as List<dynamic>? ?? const [];
    return MessagesPage(
      messages: rows.map((row) => Message.fromJson(row as Map<String, dynamic>)).toList(),
      hasOlder: body['has_older'] == true,
    );
  }

  /// Converse with the bot. The server derives the session from the authenticated
  /// account, so no key is sent — a client-named key would be a forgery primitive.
  Future<String> talk(String content) async {
    final body = await _send('POST', '/api/chat/messages', body: {'content': content});
    return body['reply'] as String? ?? '';
  }

  /// Saves a note. `delivered` is always false; the field exists so the UI can say so.
  Future<Message> note(String sessionKey, String content) async {
    final body = await _send('POST', '/api/chat/notes',
        body: {'session_key': sessionKey, 'content': content});
    return Message.fromJson(body['note'] as Map<String, dynamic>);
  }

  /// Approval events newer than [after]. The server holds a bounded ring, so the
  /// client keeps its own cursor and never assumes the whole history is present.
  Future<ApprovalFeed> approvals({int after = 0}) async {
    final body = await _send('GET', '/api/approvals/feed?after=$after');
    return ApprovalFeed.fromJson(body);
  }

  /// Decide a pending request. The session key only locates the row; authority
  /// comes from the signed-in account, never from this body.
  Future<void> decideApproval(int requestId, String kind, String sessionKey) async {
    await _send('POST', '/api/budget/$requestId/$kind',
        body: {'session_key': sessionKey, 'note': ''});
  }
}

/// One approval event. Field names mirror the server's explicit whitelist.
class ApprovalEvent {
  const ApprovalEvent({
    required this.id,
    required this.kind,
    required this.requestId,
    required this.sessionKey,
    required this.amountMinor,
    required this.currency,
    required this.purpose,
    required this.degraded,
  });

  final int id;
  final String kind;
  final int requestId;
  final String sessionKey;
  final int amountMinor;
  final String currency;
  final String purpose;
  final bool degraded;

  bool get isPending => kind == 'requested';

  String get statusLabel {
    switch (kind) {
      case 'approved':
        return '已批准';
      case 'denied':
        return '已驳回';
      case 'cancelled':
        return '已撤回';
      case 'expired':
        return '已过期';
      default:
        return '待审批';
    }
  }

  String get amountLabel => '${(amountMinor / 100).toStringAsFixed(2)} $currency';

  factory ApprovalEvent.fromJson(Map<String, dynamic> json) => ApprovalEvent(
        id: (json['id'] as num?)?.toInt() ?? 0,
        kind: json['kind'] as String? ?? '',
        requestId: (json['request_id'] as num?)?.toInt() ?? 0,
        sessionKey: json['session_key'] as String? ?? '',
        amountMinor: (json['amount_minor'] as num?)?.toInt() ?? 0,
        currency: json['currency'] as String? ?? 'CNY',
        purpose: json['purpose'] as String? ?? '',
        degraded: json['degraded'] == true,
      );
}

class ApprovalFeed {
  const ApprovalFeed({required this.events, required this.cursor, required this.enabled});

  final List<ApprovalEvent> events;
  final int cursor;
  final bool enabled;

  factory ApprovalFeed.fromJson(Map<String, dynamic> json) => ApprovalFeed(
        events: (json['events'] as List<dynamic>? ?? const [])
            .map((row) => ApprovalEvent.fromJson(row as Map<String, dynamic>))
            .toList(),
        cursor: (json['cursor'] as num?)?.toInt() ?? 0,
        enabled: json['enabled'] != false,
      );
}
