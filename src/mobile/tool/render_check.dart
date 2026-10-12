// A CLI diagnostic, not app code: printing to stdout is the entire point, so
// avoid_print does not apply. Also fixes the prefer_is_empty hint.
//
// Run: dart run tool/render_check.dart --dart-define=BLED_API_BASE=<backend>
//
// Decodes a live /route/transit payload through the same model the map widgets
// use and prints what would be drawn. Exits non-zero if the route would not
// render usefully. Useful because the map itself is a canvas behind shadow DOM,
// which resists assertion from outside the app.
// ignore_for_file: avoid_print, prefer_is_empty

// Render check: feed a REAL captured /route/transit payload (with geometry)
// through the Dart model and print what the map would draw.
//
// The browser UI is a canvas behind shadow DOM, so asserting on it is brittle.
// This exercises the same decoding and derivation the widgets call, against a
// payload captured from the live backend, so the numbers below are the real ones.
//
// Run: dart run tool/render_check.dart
import 'dart:convert';
import 'dart:io';

import 'package:bledi_app/data/models/itinerary.dart';

Future<void> main() async {
  final payload = await _fetch();
  final steps = (payload['best_fastest']?['steps'] as List?) ?? [];

  final it = Itinerary.fromJson({
    'duration': payload['best_fastest']?['duration'] ?? 0.0,
    'duration_min': payload['best_fastest']?['duration_min'] ?? 0.0,
    'steps': steps,
  });

  print('legs                : ${it.steps.length}');
  print('legs with geometry  : ${it.steps.where((s) => s.followsRealPath).length}');
  print('geometry points     : '
      '${it.steps.fold<int>(0, (a, s) => a + s.geometry.length)}');
  print('hasRealGeometry     : ${it.hasRealGeometry}');

  final path = it.continuousPath;
  print('continuousPath pts  : ${path.length}');
  var dupes = 0;
  for (var i = 1; i < path.length; i++) {
    if (path[i] == path[i - 1]) dupes++;
  }
  print('duplicate joints    : $dupes');

  final ms = it.milestones;
  print('milestones          : ${ms.length}');
  print('intermediate        : ${ms.where((m) => m.isIntermediate).length}');

  // Self-diagnosis: milestones are named from to_name, and the backend only
  // started sending it after the labelling fix. If this is 0 the running
  // backend predates that change and every milestone below falls back to the
  // instructional label, so the output is not evidence either way.
  final named = it.steps.where((s) => (s.toName ?? '').trim().isNotEmpty).length;
  print('steps with to_name  : $named/${it.steps.length}'
      '${named == 0 ? '  <-- stale backend, labels below are NOT authoritative' : ''}');
  print('');
  print('numbered milestones the map renders:');
  for (final m in ms) {
    final kind = switch (m.kind) {
      RouteMilestoneKind.stop => 'stop',
      RouteMilestoneKind.transfer => 'transfer',
      RouteMilestoneKind.walk => 'walk',
      RouteMilestoneKind.taxi => 'taxi',
      _ => 'other',
    };
    print('  ${m.order.toString().padLeft(2)}. ${m.name}  [$kind]');
  }

  // Every leg drawn must be non-degenerate.
  final bad = it.steps.where((s) => s.path.length < 2).length;
  print('');
  print('legs that would draw nothing: $bad');

  final ok = it.hasRealGeometry &&
      ms.where((m) => m.isIntermediate).length > 0 &&
      dupes == 0 &&
      bad == 0 &&
      path.length > 2;
  print(ok ? '\nRENDER CHECK PASS' : '\nRENDER CHECK FAILED');
  exit(ok ? 0 : 1);
}

Future<Map<String, dynamic>> _fetch() async {
  const base = String.fromEnvironment(
    'BLED_API_BASE',
    defaultValue: 'http://127.0.0.1:8000',
  );
  final uri = Uri.parse('$base/api/v1/route/transit'
      '?start_lat=36.8078&start_lon=10.1815'
      '&end_lat=34.7406&end_lon=10.7603');
  final request = await HttpClient().getUrl(uri);
  final response = await request.close();
  final body = await response.transform(utf8.decoder).join();
  return json.decode(body) as Map<String, dynamic>;
}
