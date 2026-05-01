import 'dart:async';
import 'dart:convert';

/// One decoded Server-Sent Event.
class SseEvent {
  const SseEvent({required this.event, required this.data});

  /// Event name (e.g. `progress`, `done`). Defaults to `message` per spec.
  final String event;

  /// Joined payload (multiple `data:` lines concatenated with `\n`).
  final String data;
}

/// A minimal SSE decoder: takes a raw byte stream (typically
/// `http.StreamedResponse.stream`) and yields parsed [SseEvent]s.
///
/// We intentionally hand-roll this rather than pull in a dedicated package —
/// the format is small and our backend's grammar is fully covered by:
/// - `event: <name>` lines set the next event's name
/// - `data: <payload>` lines are accumulated (joined with `\n`)
/// - lines starting with `:` are comments (heartbeats) and ignored
/// - a blank line dispatches the buffered event
///
/// Behaviour:
/// - The returned stream closes when the upstream byte stream closes.
/// - Errors from upstream are forwarded.
/// - Trailing partial chunks at end-of-stream are flushed if any `data:` was
///   buffered.
Stream<SseEvent> decodeSseStream(Stream<List<int>> bytes) {
  final controller = StreamController<SseEvent>();
  String buffer = '';
  String currentEvent = 'message';
  final dataLines = <String>[];

  void dispatch() {
    if (dataLines.isEmpty && currentEvent == 'message') return;
    final ev = SseEvent(event: currentEvent, data: dataLines.join('\n'));
    dataLines.clear();
    currentEvent = 'message';
    if (!controller.isClosed) controller.add(ev);
  }

  void handleLine(String line) {
    if (line.isEmpty) {
      dispatch();
      return;
    }
    if (line.startsWith(':')) return; // comment / heartbeat
    final colon = line.indexOf(':');
    final String field;
    String value;
    if (colon < 0) {
      field = line;
      value = '';
    } else {
      field = line.substring(0, colon);
      value = line.substring(colon + 1);
      if (value.startsWith(' ')) value = value.substring(1);
    }
    switch (field) {
      case 'event':
        currentEvent = value;
        break;
      case 'data':
        dataLines.add(value);
        break;
      default:
        // id / retry / unknown — ignored (we don't need them).
        break;
    }
  }

  late final StreamSubscription<String> sub;
  sub = utf8.decoder.bind(bytes).listen(
    (chunk) {
      buffer += chunk;
      // Normalise CRLF → LF then split on LF, keeping the trailing partial.
      buffer = buffer.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
      while (true) {
        final nl = buffer.indexOf('\n');
        if (nl < 0) break;
        final line = buffer.substring(0, nl);
        buffer = buffer.substring(nl + 1);
        handleLine(line);
      }
    },
    onError: (Object e, StackTrace st) {
      if (!controller.isClosed) controller.addError(e, st);
    },
    onDone: () {
      if (buffer.isNotEmpty) handleLine(buffer);
      dispatch();
      controller.close();
    },
    cancelOnError: false,
  );

  controller.onCancel = () => sub.cancel();
  return controller.stream;
}
