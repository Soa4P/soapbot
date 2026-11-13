// Client wire-format and screen behaviour tests, driven by a MockClient.
//
// No network and no secure storage: the app classes under test take a `http.Client`
// and the screens take the api object, so a canned-JSON mock exercises the real
// request building and the real widget tree.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:soapbot_archive/api/client.dart';
import 'package:soapbot_archive/screens/chat_screen.dart';
import 'package:soapbot_archive/screens/sessions_screen.dart';

ChatApi _api(Future<Map<String, dynamic>> Function(http.Request request) handler) {
  return ChatApi(
    baseUrl: 'http://test',
    client: MockClient((request) async {
      final headers = <String, String>{'content-type': 'application/json'};
      final body = await handler(request);
      return http.Response(jsonEncode(body), 200, headers: headers);
    }),
  );
}

void main() {
  group('ChatApi.messages paging modes', () {
    test('latest sends latest=true and reads has_older', () async {
      String? path;
      final api = _api((request) async {
        path = request.url.toString();
        return {
          'messages': [
            {'id': 10, 'session_key': 's', 'role': 'user', 'content': 'new'},
          ],
          'has_older': true,
        };
      });
      final page = await api.messages('s', latest: true);
      expect(path, contains('latest=true'));
      expect(path, isNot(contains('after_id=')));
      expect(page.hasOlder, isTrue);
      expect(page.messages.single.id, 10);
    });

    test('beforeId sends before_id, not after_id', () async {
      String? path;
      final api = _api((request) async {
        path = request.url.toString();
        return {'messages': <dynamic>[], 'has_older': false};
      });
      await api.messages('s', beforeId: 5);
      expect(path, contains('before_id=5'));
      expect(path, isNot(contains('after_id=')));
      expect(path, isNot(contains('latest=')));
    });

    test('forward sync keeps the after_id contract', () async {
      String? path;
      final api = _api((request) async {
        path = request.url.toString();
        return {'messages': <dynamic>[]};
      });
      await api.messages('s', afterId: 3);
      expect(path, contains('after_id=3'));
      expect(path, isNot(contains('latest=')));
      // has_older is absent on the forward shape; the page must default to false.
      final page = await api.messages('s', afterId: 3);
      expect(page.hasOlder, isFalse);
    });

    test('talk posts content only — the server derives the session', () async {
      http.Request? captured;
      final api = _api((request) async {
        if (request.method == 'POST') captured = request;
        return {'reply': 'pong', 'session_key': 'web:private:account-3'};
      });
      final reply = await api.talk('ping');
      expect(reply, 'pong');
      expect(captured!.url.path, '/api/chat/messages');
      expect(captured!.body, contains('ping'));
      expect(captured!.body, isNot(contains('session_key')));
    });
  });

  group('SessionsScreen', () {
    testWidgets('renders granted sessions and opens one', (tester) async {
      final api = _api((request) async {
        if (request.url.path == '/api/chat/sessions') {
          return {
            'sessions': [
              {'session_key': 'onebot11:group:1', 'message_count': 2, 'last_at': 0},
            ],
            'scope': 'member',
          };
        }
        return {'talk': false};
      });
      await tester.pumpWidget(MaterialApp(
        home: SessionsScreen(api: api, accountId: 1, onSignOut: () {}),
      ));
      await tester.pumpAndSettle();
      expect(find.text('群 1'), findsOneWidget);
    });

    testWidgets('shows the empty state when nothing is granted', (tester) async {
      final api = _api((request) async => {
            'sessions': <dynamic>[],
            'scope': 'member',
          });
      await tester.pumpWidget(MaterialApp(
        home: SessionsScreen(api: api, accountId: 1, onSignOut: () {}),
      ));
      await tester.pumpAndSettle();
      expect(find.text('还没有被授权的会话'), findsOneWidget);
    });
  });

  group('ChatScreen composers', () {
    testWidgets('own conversation session shows the talk input', (tester) async {
      final api = _api((request) async {
        if (request.url.path == '/api/chat/surfaces') return {'talk': true};
        if (request.url.path == '/api/chat/messages' && request.method == 'GET') {
          return {'messages': <dynamic>[], 'has_older': false};
        }
        return {'reply': 'pong'};
      });
      final session = SessionRow.fromJson({
        'session_key': 'web:private:account-3',
        'message_count': 0,
        'last_at': 0,
      });
      await tester.pumpWidget(MaterialApp(
        home: ChatScreen(api: api, session: session, accountId: 3),
      ));
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsOneWidget);
      expect(find.byIcon(Icons.send), findsOneWidget);
    });

    testWidgets('other sessions keep the note-only button', (tester) async {
      final api = _api((request) async {
        if (request.url.path == '/api/chat/surfaces') return {'talk': true};
        return {'messages': <dynamic>[], 'has_older': false};
      });
      final session = SessionRow.fromJson({
        'session_key': 'onebot11:group:1',
        'message_count': 0,
        'last_at': 0,
      });
      await tester.pumpWidget(MaterialApp(
        home: ChatScreen(api: api, session: session, accountId: 3),
      ));
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsNothing);
      expect(find.text('写一条备注'), findsOneWidget);
      // The archive banner stays for note sessions, never for talk.
      expect(find.text('这里只记录，不发送。对方在 QQ 里看不到这些内容。'), findsOneWidget);
    });
  });

  group('delivery state wire format', () {
    test('session label names the conversation session', () {
      final row = SessionRow.fromJson({
        'session_key': 'web:private:account-3',
        'message_count': 0,
        'last_at': 0,
      });
      expect(row.label, '与机器人的对话');
      expect(row.isWebTalk('3'), isTrue);
    });

    test('state and reason parse from the server rows, legacy rows read ok/absent', () {
      final rejected = Message.fromJson({
        'id': 1,
        'session_key': 's',
        'role': 'user',
        'content': 'x',
        'created_at': 0,
        'state': 'rejected',
        'reason': 'abuse_rate_limited',
      });
      expect(rejected.state, DeliveryState.rejected);
      expect(rejected.reason, 'abuse_rate_limited');

      final failed = Message.fromJson({
        'id': 2,
        'session_key': 's',
        'role': 'assistant',
        'content': 'x',
        'created_at': 0,
        'state': 'send_failed',
      });
      expect(failed.state, DeliveryState.sendFailed);

      final legacy = Message.fromJson({
        'id': 3,
        'session_key': 's',
        'role': 'user',
        'content': 'x',
        'created_at': 0,
        'state': null,
      });
      expect(legacy.state, isNull);
      expect(legacy.reason, '');
    });
  });

  group('ChatScreen delivery states', () {
    testWidgets('a refused message is replaced by the server rejected row', (tester) async {
      final api = ChatApi(
        baseUrl: 'http://test',
        client: MockClient((request) async {
          final headers = <String, String>{'content-type': 'application/json'};
          if (request.url.path == '/api/chat/surfaces') {
            return http.Response(jsonEncode({'talk': true}), 200, headers: headers);
          }
          if (request.url.path == '/api/chat/messages' && request.method == 'GET') {
            // The forward sync after the 429 returns the server's rejected row.
            return http.Response(
              jsonEncode({
                'messages': [
                  {
                    'id': 10,
                    'session_key': 'web:private:account-3',
                    'role': 'user',
                    'content': '被拒的话',
                    'created_at': 0,
                    'state': 'rejected',
                    'reason': 'abuse_rate_limited',
                  }
                ],
              }),
              200,
              headers: headers,
            );
          }
          // POST talk: the pipeline refused with a short token.
          return http.Response(
            jsonEncode({'detail': 'abuse_rate_limited'}),
            429,
            headers: headers,
          );
        }),
      );
      final session = SessionRow.fromJson({
        'session_key': 'web:private:account-3',
        'message_count': 0,
        'last_at': 0,
      });
      await tester.pumpWidget(MaterialApp(
        home: ChatScreen(api: api, session: session, accountId: 3),
      ));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '被拒的话');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      // The optimistic bubble is gone; the server row shows the rejection badge
      // with the short reason token (the timeline matches what other ends see).
      expect(find.text('发送中'), findsNothing);
      expect(find.text('被拒的话'), findsOneWidget);
      expect(find.text('被拒绝 (abuse_rate_limited)'), findsOneWidget);
    });

    testWidgets('a network failure keeps the bubble marked send-failed', (tester) async {
      final api = ChatApi(
        baseUrl: 'http://test',
        client: MockClient((request) async {
          final headers = <String, String>{'content-type': 'application/json'};
          if (request.url.path == '/api/chat/surfaces') {
            return http.Response(jsonEncode({'talk': true}), 200, headers: headers);
          }
          if (request.url.path == '/api/chat/messages' && request.method == 'GET') {
            return http.Response(
              jsonEncode({'messages': <dynamic>[]}),
              200,
              headers: headers,
            );
          }
          throw Exception('network down');
        }),
      );
      final session = SessionRow.fromJson({
        'session_key': 'web:private:account-3',
        'message_count': 0,
        'last_at': 0,
      });
      await tester.pumpWidget(MaterialApp(
        home: ChatScreen(api: api, session: session, accountId: 3),
      ));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '发不出去');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      // Nothing reached the server, so the bubble stays — visibly failed, not gone.
      expect(find.text('发不出去'), findsOneWidget);
      expect(find.text('发送失败'), findsOneWidget);
    });
  });
}
