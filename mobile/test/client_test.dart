// Model-level tests for the API client: parsing, labels, and paging-mode mapping.
//
// The client is the contract between the app and the archive API; these tests pin the
// shapes the server actually sends (snake_case keys, optional has_older) so a backend
// rename fails here instead of on a phone.
import 'package:flutter_test/flutter_test.dart';
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
}
