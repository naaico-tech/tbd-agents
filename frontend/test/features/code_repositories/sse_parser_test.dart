import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/features/code_repositories/sse_parser.dart';

void main() {
  group('decodeSseStream', () {
    test('emits a single progress event with parsed data', () async {
      final controller = StreamController<List<int>>();
      final eventsFuture = decodeSseStream(controller.stream).toList();

      controller.add(utf8.encode('event: progress\n'));
      controller.add(utf8.encode('data: {"id":"abc","state":"queued"}\n\n'));
      await controller.close();

      final events = await eventsFuture;
      expect(events, hasLength(1));
      expect(events.single.event, equals('progress'));
      expect(jsonDecode(events.single.data),
          equals({'id': 'abc', 'state': 'queued'}));
    });

    test('ignores `:` heartbeat comments', () async {
      final controller = StreamController<List<int>>();
      final eventsFuture = decodeSseStream(controller.stream).toList();

      controller.add(utf8.encode(': keepalive\n\n'));
      controller.add(utf8.encode('event: progress\ndata: {"a":1}\n\n'));
      controller.add(utf8.encode(': keepalive\n\n'));
      await controller.close();

      final events = await eventsFuture;
      expect(events.map((e) => e.event), equals(['progress']));
    });

    test('handles a sequence ending with `done`', () async {
      final controller = StreamController<List<int>>();
      final received = <SseEvent>[];
      final sub = decodeSseStream(controller.stream).listen(received.add);

      controller.add(utf8.encode('event: progress\ndata: {"chunks_done":1}\n\n'));
      controller.add(utf8.encode('event: progress\ndata: {"chunks_done":2}\n\n'));
      controller.add(utf8.encode('event: done\ndata: {"state":"done"}\n\n'));
      await controller.close();
      await sub.asFuture<void>();

      expect(received.map((e) => e.event),
          equals(['progress', 'progress', 'done']));
      expect(jsonDecode(received.last.data), equals({'state': 'done'}));
    });

    test('reassembles events split across byte chunks', () async {
      final controller = StreamController<List<int>>();
      final eventsFuture = decodeSseStream(controller.stream).toList();

      controller.add(utf8.encode('event: prog'));
      controller.add(utf8.encode('ress\ndata: {"v":'));
      controller.add(utf8.encode('42}\n\n'));
      await controller.close();

      final events = await eventsFuture;
      expect(events, hasLength(1));
      expect(events.single.event, equals('progress'));
      expect(jsonDecode(events.single.data), equals({'v': 42}));
    });

    test('joins multiple data: lines with newline', () async {
      final controller = StreamController<List<int>>();
      final eventsFuture = decodeSseStream(controller.stream).toList();

      controller.add(utf8.encode('data: line one\n'));
      controller.add(utf8.encode('data: line two\n\n'));
      await controller.close();

      final events = await eventsFuture;
      expect(events.single.data, equals('line one\nline two'));
    });

    test('normalises CRLF line endings', () async {
      final controller = StreamController<List<int>>();
      final eventsFuture = decodeSseStream(controller.stream).toList();

      controller.add(utf8.encode('event: progress\r\ndata: {"x":1}\r\n\r\n'));
      await controller.close();

      final events = await eventsFuture;
      expect(events, hasLength(1));
      expect(events.single.event, equals('progress'));
    });
  });
}
