// Approval feed parsing: the shape the Python notifier's whitelist produces.
//
// A field rename on the server must fail here (a Dart test in CI) rather than on a
// phone showing "0.00" for a real spend request.
import 'package:flutter_test/flutter_test.dart';
import 'package:soapbot_archive/api/client.dart';

void main() {
  group('ApprovalEvent.fromJson', () {
    test('parses the whitelisted fields and formats minor units', () {
      final event = ApprovalEvent.fromJson({
        'id': 3,
        'kind': 'requested',
        'request_id': 7,
        'session_key': 'onebot11:group:100',
        'amount_minor': 2550,
        'currency': 'CNY',
        'purpose': 'materials',
        'degraded': false,
      });
      expect(event.isPending, isTrue);
      expect(event.statusLabel, '待审批');
      expect(event.amountLabel, '25.50 CNY');
      expect(event.requestId, 7);
    });

    test('absent fields degrade to safe defaults, never a crash', () {
      final event = ApprovalEvent.fromJson({});
      expect(event.requestId, 0);
      expect(event.amountMinor, 0);
      expect(event.isPending, isFalse);
      expect(event.statusLabel, '待审批');
    });

    test('a degraded approval is visible and not pending', () {
      final event = ApprovalEvent.fromJson({
        'kind': 'approved',
        'request_id': 2,
        'amount_minor': 100,
        'degraded': true,
      });
      expect(event.degraded, isTrue);
      expect(event.isPending, isFalse);
      expect(event.statusLabel, '已批准');
    });
  });

  group('ApprovalFeed.fromJson', () {
    test('preserves the cursor and parses events in order', () {
      final feed = ApprovalFeed.fromJson({
        'enabled': true,
        'cursor': 12,
        'events': [
          {'id': 11, 'request_id': 1, 'kind': 'requested', 'amount_minor': 100},
          {'id': 12, 'request_id': 2, 'kind': 'denied', 'amount_minor': 200},
        ],
      });
      expect(feed.enabled, isTrue);
      expect(feed.cursor, 12);
      expect(feed.events.map((e) => e.requestId), [1, 2]);
    });

    test('a disabled deployment reports an empty feed', () {
      final feed = ApprovalFeed.fromJson({'enabled': false, 'events': [], 'cursor': 0});
      expect(feed.enabled, isFalse);
      expect(feed.events, isEmpty);
    });
  });
}
