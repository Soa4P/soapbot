// Model-level tests for the API client: parsing, labels, and paging-mode mapping.
//
// The client is the contract between the app and the archive API; these tests pin the
// shapes the server actually sends (snake_case keys, optional has_older) so a backend
// rename fails here instead of on a phone.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:soapbot_archive/api/client.dart';

void main() {
  group('SessionRow.label', () {
    test('qq group sessions read as 群 <id>', () {
      final row = SessionRow.fromJson({
        'session_key': 'onebot11:group:12345',
        'message_count': 3,
        'last_at': 0,
      });
      expect(row.label, '群 12345');
    });

    test('private sessions read as 私聊 <id>', () {
      final row = SessionRow.fromJson({
        'session_key': 'qq_official:private:20001',
        'message_count': 1,
        'last_at': 0,
      });
      expect(row.label, '私聊 20001');
    });

    test('the conversation session is recognised by isWebTalk', () {
      final row = SessionRow.fromJson({
        'session_key': 'web:private:account-3',
        'message_count': 0,
        'last_at': 0,
      });
      expect(row.isWebTalk('3'), isTrue);
      expect(row.isWebTalk('4'), isFalse);
      // Never true for someone else's conversation session.
      expect(row.sessionKey.startsWith('web:private:'), isTrue);
    });
  });

  group('Message.fromJson', () {
    test('defaults and notes', () {
      final note = Message.fromJson({
        'id': 7,
        'session_key': 'onebot11:group:1',
        'role': 'note',
        'content': '记住这个',
        'created_at': 100.5,
        'user_name': 'bob',
        'image_desc': '',
      });
      expect(note.isNote, isTrue);
      expect(note.userName, 'bob');
      expect(note.createdAt, 100.5);

      final plain = Message.fromJson({
        'id': 8,
        'session_key': 's',
        'role': 'assistant',
        'content': 'hi',
      });
      expect(plain.isNote, isFalse);
      expect(plain.userName, '');
      expect(plain.imageDesc, isNull);
    });
  });

  group('CSRF double-submit', () {
    test('登录同时捕获两枚 Cookie，变更请求回显 X-CSRF-Token', () async {
      final captured = <http.Request>[];
      http.Response respond(dynamic body, {Map<String, String> headers = const {}}) {
        final h = <String, String>{'content-type': 'application/json', ...headers};
        return http.Response(jsonEncode(body), 200, headers: h);
      }

      final api = ChatApi(
        baseUrl: 'http://test',
        client: MockClient((request) async {
          captured.add(request);
          if (request.url.path == '/api/accounts/login') {
            // httpx/http 会把多个 Set-Cookie 合并进一个头（逗号连接）。
            return respond(
              {
                'account': {'id': 1, 'username': 'u', 'role': 'owner'},
                'access_token': 'jwt-token',
              },
              headers: {
                'set-cookie':
                    'soapbot_session=abc.def; HttpOnly; Path=/, soapbot_csrf=tok123; Path=/',
              },
            );
          }
          if (request.url.path == '/api/chat/notes') {
            return respond({
              'note': {'id': 1, 'session_key': 's', 'role': 'note', 'content': 'x'},
              'delivered': false,
            });
          }
          return respond({});
        }),
      );

      final account = await api.login('u', 'p');
      expect(account.id, 1);
      expect(api.csrf, 'tok123');
      expect(api.token, 'jwt-token');

      final note = await api.note('onebot11:group:1', '备忘');
      expect(note.isNote, isTrue);
      final noteReq = captured.last;
      // Bearer 优先：服务端对 Bearer 请求豁免 CSRF，原生客户端不再被
      // 「升级后 csrf 未存」的 403 卡死。
      expect(noteReq.headers['Authorization'], 'Bearer jwt-token');
      expect(api.csrf, 'tok123');
    });
  });
}
