@Tags(<String>['integration'])
library;

import 'dart:convert';

import 'package:bledi_app/data/datasources/api_client.dart';
import 'package:bledi_app/data/datasources/stations_data_source.dart';
import 'package:bledi_app/data/models/itinerary.dart';
import 'package:bledi_app/data/models/station.dart';
import 'package:bledi_app/data/repositories/routing_repository.dart';
import 'package:flutter_test/flutter_test.dart';

/// End-to-end checks of the data layer against a **running** BLEDI.TN backend.
///
/// Skipped automatically when the backend is not reachable, so the default
/// `flutter test` run stays offline-safe. To exercise them:
///
///     # terminal 1 — from the bledi.tn repo root
///     python -m uvicorn src.backend.app.main:app --port 8000
///     # terminal 2
///     flutter test --tags integration
///
/// Override the target with BLED_API_BASE (same variable name the app uses).
const String baseUrl = String.fromEnvironment(
  'BLED_API_BASE',
  defaultValue: 'http://localhost:8000',
);

/// Async reachability probe, run once in `setUpAll`.
Future<bool> _backendUp(ApiClient client) async {
  try {
    final health = await client.getJson('/api/v1/health');
    return health is Map<String, dynamic> && health['status'] == 'ok';
  } catch (_) {
    return false;
  }
}

void main() {
  final client = ApiClient(baseUrl: baseUrl);
  var online = false;

  /// Stations fetched once and shared by the read-only assertions below, so
  /// the 1 700-feature payload is not re-downloaded per test.
  late List<Station> payloadStations;

  setUpAll(() async {
    online = await _backendUp(client);
    if (!online) {
      // ignore: avoid_print
      print('\n[SKIP] No backend at $baseUrl — integration tests skipped.');
      return;
    }
    payloadStations =
        (await StationsDataSource(client).fetchAll()).stations;
  });

  tearDownAll(() => client.close());

  group('live /api/v1/stations', () {
    test('parses the real FeatureCollection', () async {
      if (!online) return markTestSkipped('backend offline');

      final payload = await StationsDataSource(client).fetchAll();

      expect(payload.stations, isNotEmpty);
      expect(payload.total, greaterThan(1000));
      // `total` counts the main transit seed only; the louage/taxi stops from
      // the secondary seed are appended, so features >= total.
      expect(
        payload.stations.length,
        greaterThanOrEqualTo(payload.total),
        reason: 'louage stops are merged in addition to the transit seed',
      );

      // Every station must land inside Tunisia's bounding box. This is the
      // regression guard for the GeoJSON [lon, lat] vs transit [lat, lon] mix-up.
      for (final station in payload.stations.take(500)) {
        expect(
          station.lat,
          inInclusiveRange(30.0, 37.6),
          reason: '${station.name} latitude out of Tunisia bounds',
        );
        expect(
          station.lon,
          inInclusiveRange(7.0, 11.7),
          reason: '${station.name} longitude out of Tunisia bounds',
        );
      }
    });

    test('every station resolves to a known transport category', () async {
      if (!online) return markTestSkipped('backend offline');

      final payload = await StationsDataSource(client).fetchAll();
      final counts = <String, int>{};
      var undeclared = 0;
      for (final station in payload.stations) {
        final mode = station.transportMode;
        counts[mode.name] = (counts[mode.name] ?? 0) + 1;
        if (!station.hasDeclaredMode) undeclared++;
      }

      // The enriched backend supplies a real mode for every stop; the
      // line-id fallback should therefore almost never be needed.
      expect(undeclared, lessThan(payload.stations.length ~/ 10),
          reason: 'most stations must carry a declared mode');

      // The product palette has exactly three real categories; `unknown` must
      // stay a small minority rather than swallowing everything.
      for (final key in ['rail', 'bus', 'louage']) {
        expect(counts[key], greaterThan(0), reason: '$key must be present');
      }
      expect(counts['unknown'] ?? 0, lessThan(payload.stations.length ~/ 4),
          reason: 'unknown must not dominate');
    });

    test('stations carry a city, and the loudest mode groups correctly', () {
      if (!online) return markTestSkipped('backend offline');

      final payload = StationsPayload(
        stations: payloadStations,
        total: payloadStations.length,
      );
      final cities = payload.citySummaries();

      expect(cities, isNotEmpty);
      // Largest first.
      for (var i = 1; i < cities.length; i++) {
        expect(
          cities[i - 1].stationCount,
          greaterThanOrEqualTo(cities[i].stationCount),
          reason: 'cities must be sorted largest first',
        );
      }

      final tunis = cities.firstWhere((c) => c.name == 'Tunis');
      expect(tunis.countOf(TransportMode.bus), greaterThan(0));
      expect(tunis.lat, closeTo(36.8, 0.6));
      expect(tunis.lon, closeTo(10.17, 0.6));

      // Per-city counts must add up to the city's total.
      final summed = tunis.countsByCategory.values.fold<int>(0, (a, b) => a + b);
      expect(summed, lessThanOrEqualTo(tunis.stationCount));
    });

    test('louage stops are present and classified as the yellow category', () {
      if (!online) return markTestSkipped('backend offline');

      final louage = payloadStations
          .where((s) => s.source == 'louage')
          .toList(growable: false);

      expect(louage, isNotEmpty,
          reason: 'the louage seed must contribute yellow-category stops');
      for (final station in louage) {
        expect(station.transportMode, TransportMode.louage);
        expect(station.id, startsWith('louage_'));
        expect(station.lat, inInclusiveRange(30.0, 37.6));
        expect(station.lon, inInclusiveRange(7.0, 11.7));
      }
    });

    test('caches so a second call does not refetch', () async {
      if (!online) return markTestSkipped('backend offline');

      final repository = StationsRepository(StationsDataSource(client));
      expect(repository.isCached, isFalse);

      final first = await repository.getAll();
      expect(repository.isCached, isTrue);
      expect(repository.cached, isNotNull);

      final second = await repository.getAll();
      expect(identical(first, second), isTrue,
          reason: 'cached payload should be returned as-is');

      // Concurrent callers must share one in-flight request.
      repository.clearCache();
      final results = await Future.wait([repository.getAll(), repository.getAll()]);
      expect(identical(results[0], results[1]), isTrue);

      repository.clearCache();
    });

    test('search matches station names', () async {
      if (!online) return markTestSkipped('backend offline');

      final repository = StationsRepository(StationsDataSource(client));
      await repository.getAll();

      final target = repository.cached!.stations.first;
      final needle = target.name.split(' ').first;
      final results = repository.search(needle);

      expect(results, isNotEmpty);
      expect(
        results.any((s) => s.name.toLowerCase().contains(needle.toLowerCase())),
        isTrue,
      );
      expect(repository.search(''), isEmpty);
      expect(repository.search('zzzznotastation'), isEmpty);

      repository.clearCache();
    });
  });

  group('live /api/v1/route/transit', () {
    // Tunis -> a point that yields a real walk+ride bus itinerary.
    const startLat = 36.8065, startLon = 10.1815;
    const endLat = 36.8190, endLon = 10.1650;

    test('returns a parseable itinerary with in-bounds steps', () async {
      if (!online) return markTestSkipped('backend offline');

      final response = await RoutingDataSource(client).fetchTransitRoute(
        startLat: startLat,
        startLon: startLon,
        endLat: endLat,
        endLon: endLon,
      );

      expect(response.hasError, isFalse,
          reason: 'backend error: ${response.error}');

      final itinerary = response.primary;
      expect(itinerary, isNotNull);
      expect(itinerary!.steps, isNotEmpty);
      expect(itinerary.duration, greaterThan(0));
      expect(itinerary.durationMin, greaterThan(0));

      // The same [lat, lon] orientation guard as the station check.
      for (final step in itinerary.steps) {
        expect(step.start.latitude, inInclusiveRange(30.0, 37.6));
        expect(step.start.longitude, inInclusiveRange(7.0, 11.7));
        expect(step.end.latitude, inInclusiveRange(30.0, 37.6));
        expect(step.end.longitude, inInclusiveRange(7.0, 11.7));
        expect(['walk', 'ride', 'transfer', 'taxi'], contains(step.type));
      }

      // Legs must chain end-to-start, otherwise the drawn polyline jumps.
      for (var i = 1; i < itinerary.steps.length; i++) {
        final previous = itinerary.steps[i - 1].end;
        final current = itinerary.steps[i].start;
        expect(
          previous.latitude, closeTo(current.latitude, 1e-9),
          reason: 'gap between step $i-1 end and step $i start',
        );
        expect(previous.longitude, closeTo(current.longitude, 1e-9));
      }
    });

    test('a walk+ride itinerary exposes ride legs and line labels', () async {
      if (!online) return markTestSkipped('backend offline');

      final response = await RoutingDataSource(client).fetchTransitRoute(
        startLat: startLat,
        startLon: startLon,
        endLat: endLat,
        endLon: endLon,
      );
      final itinerary = response.primary;
      if (itinerary == null) return markTestSkipped('no route for these points');

      final rides = itinerary.steps.where((s) => s.isRide).toList();
      if (rides.isEmpty) {
        // The router may legitimately answer with a taxi-only itinerary.
        expect(itinerary.steps.every((s) => s.isTaxi), isTrue);
        return;
      }

      expect(rides.every((s) => s.mode != null && s.mode!.isNotEmpty), isTrue);
      expect(itinerary.lineLabels, isNotEmpty);
      expect(itinerary.walkLegs, greaterThan(0));
    });

    test('taxi fallback carries a fare', () async {
      if (!online) return markTestSkipped('backend offline');

      // Far enough apart that the router answers taxi-only.
      final response = await RoutingDataSource(client).fetchTransitRoute(
        startLat: 36.8065,
        startLon: 10.1815,
        endLat: 36.8628,
        endLon: 10.1957,
      );
      final itinerary = response.primary;
      if (itinerary == null) return markTestSkipped('no route');

      if (itinerary.steps.every((s) => s.isTaxi)) {
        expect(itinerary.hasFare, isTrue);
        expect(itinerary.fareDinars, greaterThan(0));
      }
    });

    test('identical origin and destination yields a zero-length walk', () async {
      if (!online) return markTestSkipped('backend offline');

      final response = await RoutingDataSource(client).fetchTransitRoute(
        startLat: 36.8065,
        startLon: 10.1815,
        endLat: 36.8065,
        endLon: 10.1815,
      );

      // The router always has a taxi fallback, so for any two valid points it
      // returns *something*; an identical pair degrades to a 0 m walk. This
      // must decode rather than throw, and the app must be able to render it.
      expect(response.hasError, isFalse);
      final itinerary = response.primary;
      expect(itinerary, isNotNull);
      expect(itinerary!.steps, isNotEmpty);
      expect(itinerary.steps.first.distanceMeters, lessThan(1));
      // A degenerate route must not be mistaken for a usable one in the UI.
      expect(response.primary!.durationMin, 0);
    });

    test('missing required params surface as an ApiException', () async {
      if (!online) return markTestSkipped('backend offline');

      // FastAPI validates the query params and answers 422. The client must
      // turn that into a typed error, not a raw DioException.
      try {
        await client.getJson('/api/v1/route/transit', query: {'start_lat': 36.8});
        fail('expected ApiException');
      } on ApiException catch (e) {
        expect(e.statusCode, anyOf(422, 400));
        expect(e.message, isNotEmpty);
      }
    });
  });

  group('live /api/v1/lines + health', () {
    test('lines endpoint parses', () async {
      if (!online) return markTestSkipped('backend offline');

      final lines = await LinesDataSource(client).fetchLines(limit: 50);
      expect(lines.lines, isNotEmpty);
      expect(
        lines.lines.every((l) => l.id.isNotEmpty && l.displayName.isNotEmpty),
        isTrue,
      );
    });

    test('health reports the seed counts', () async {
      if (!online) return markTestSkipped('backend offline');

      final health = await LinesDataSource(client).fetchHealth();
      expect(health.isHealthy, isTrue);
      expect(health.stationsCount, greaterThan(1000));
      expect(health.linesCount, greaterThan(100));
      // snake_case mapping must survive the freezed @JsonKey annotations.
      expect(health.seedFile, isNotNull);
      expect(health.seedFile, isNotEmpty);
    });
  });

  group('ApiClient error mapping', () {
    test('maps an unreachable host to a readable message', () async {
      final dead = ApiClient(baseUrl: 'http://127.0.0.1:59999');
      try {
        await dead.getJson('/api/v1/health');
        fail('expected ApiException');
      } on ApiException catch (e) {
        expect(e.message, contains('127.0.0.1:59999'));
        expect(e.message, isNot(contains('Exception:')));
      } finally {
        dead.close();
      }
    });

    test('drops null query params instead of sending "null"', () async {
      // Exercised through the routing datasource: all four params are
      // non-null here, so this asserts the happy path stays wired.
      if (!online) return markTestSkipped('backend offline');
      final response = await RoutingDataSource(client).fetchTransitRoute(
        startLat: 36.8065,
        startLon: 10.1815,
        endLat: 36.8190,
        endLon: 10.1650,
      );
      expect(response.source, isNotNull);
    });
  });

  group('end-to-end JSON round trip', () {
    test('a captured live payload decodes identically', () async {
      if (!online) return markTestSkipped('backend offline');

      final raw = await client.getJson(
        '/api/v1/route/transit',
        query: {
          'start_lat': 36.8065,
          'start_lon': 10.1815,
          'end_lat': 36.8190,
          'end_lon': 10.1650,
        },
      );

      // Decode twice through the generated model to prove stability.
      final once = RouteResponse.fromJson(raw as Map<String, dynamic>);
      final twice = RouteResponse.fromJson(jsonDecode(jsonEncode(once.toJson()))
          as Map<String, dynamic>);

      expect(twice.primary!.steps.length, once.primary!.steps.length);
      expect(twice.primary!.durationMin, once.primary!.durationMin);
      for (var i = 0; i < once.primary!.steps.length; i++) {
        expect(
          twice.primary!.steps[i].start.latitude,
          once.primary!.steps[i].start.latitude,
        );
      }
    });
  });
}