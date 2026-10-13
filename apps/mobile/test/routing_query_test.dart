import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:bledi_app/data/datasources/api_client.dart';
import 'package:bledi_app/data/repositories/routing_repository.dart';

/// Captures the request the repository builds and answers it with `body`.
///
/// This is the only way to prove the transport selection actually reaches
/// `/api/v1/route/plan`: the parameters were previously only ever checked by
/// the analyzer, never executed, so an omission bug would have shipped silently.
class _Recorder {
  _Recorder(this.body);

  final Object body;
  final List<Uri> requests = [];
  final List<Map<String, dynamic>> queries = [];

  late final ApiClient client = ApiClient(
    dio: Dio()..httpClientAdapter = _Adapter(this),
    baseUrl: 'http://test.local',
  );
}

class _Adapter implements HttpClientAdapter {
  _Adapter(this.rec);

  final _Recorder rec;

  @override
  void close({bool force = false}) {}

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    rec.requests.add(options.uri);
    rec.queries.add(options.uri.queryParameters);
    return ResponseBody.fromString(
      '{"type":"x"}',
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }
}

void main() {
  group('fetchRoutePlan query', () {
    test('omits modes_include / modes_exclude when not supplied', () async {
      final rec = _Recorder(<String, dynamic>{});
      await RoutingDataSource(rec.client).fetchRoutePlan(
        startLat: 36.8,
        startLon: 10.18,
        endLat: 35.8,
        endLon: 10.6,
      );
      final q = rec.queries.single;
      expect(q.containsKey('modes_include'), isFalse,
          reason: 'an empty include must be omitted, not sent as ""');
      expect(q.containsKey('modes_exclude'), isFalse);
      expect(q['objective'], 'fastest');
      expect(rec.requests.single.path, '/api/v1/route/plan');
    });

    test('omits empty lists explicitly passed in', () async {
      final rec = _Recorder(<String, dynamic>{});
      await RoutingDataSource(rec.client).fetchRoutePlan(
        startLat: 36.8,
        startLon: 10.18,
        endLat: 35.8,
        endLon: 10.6,
        include: const [],
        exclude: const [],
      );
      final q = rec.queries.single;
      expect(q.containsKey('modes_include'), isFalse);
      expect(q.containsKey('modes_exclude'), isFalse);
    });

    test('sends the selected modes comma-separated', () async {
      final rec = _Recorder(<String, dynamic>{});
      await RoutingDataSource(rec.client).fetchRoutePlan(
        startLat: 36.8,
        startLon: 10.18,
        endLat: 35.8,
        endLon: 10.6,
        include: const ['bus', 'metro'],
        exclude: const ['train'],
      );
      final q = rec.queries.single;
      expect(q['modes_include'], 'bus,metro');
      expect(q['modes_exclude'], 'train');
    });

    test('passes the objective and caps through', () async {
      final rec = _Recorder(<String, dynamic>{});
      await RoutingDataSource(rec.client).fetchRoutePlan(
        startLat: 36.8,
        startLon: 10.18,
        endLat: 35.8,
        endLon: 10.6,
        objective: 'fewest_transfers',
        maxTransfers: 1,
        maxWalkM: 800,
        maxItineraries: 5,
      );
      final q = rec.queries.single;
      expect(q['objective'], 'fewest_transfers');
      expect(q['max_transfers'], '1');
      expect(q['max_walk_m'], '800.0'); // Dio stringifies doubles
      expect(q['max_itineraries'], '5');
    });

    test('omits unset caps', () async {
      final rec = _Recorder(<String, dynamic>{});
      await RoutingDataSource(rec.client).fetchRoutePlan(
        startLat: 36.8,
        startLon: 10.18,
        endLat: 35.8,
        endLon: 10.6,
      );
      final q = rec.queries.single;
      expect(q.containsKey('max_transfers'), isFalse);
      expect(q.containsKey('max_walk_m'), isFalse);
    });

    test('always sends the four coordinates', () async {
      final rec = _Recorder(<String, dynamic>{});
      await RoutingDataSource(rec.client).fetchRoutePlan(
        startLat: 36.8065,
        startLon: 10.1815,
        endLat: 35.8256,
        endLon: 10.636,
      );
      final q = rec.queries.single;
      expect(q['start_lat'], '36.8065');
      expect(q['start_lon'], '10.1815');
      expect(q['end_lat'], '35.8256');
      expect(q['end_lon'], '10.636');
    });
  });
}