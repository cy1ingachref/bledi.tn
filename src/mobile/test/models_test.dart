import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

import 'package:bledi_app/core/theme.dart';
import 'package:bledi_app/data/models/health.dart';
import 'package:bledi_app/data/models/itinerary.dart';
import 'package:bledi_app/data/models/line.dart';
import 'package:bledi_app/data/models/station.dart';

/// Verifies the models parse the exact payloads the backend emits.
///
/// Every fixture below is copied from a live `curl` against
/// `src/backend/app/main.py` @ 1711 stations / 232 lines, so a backend contract
/// drift fails these tests instead of silently mis-placing the map.
void main() {
  group('RouteResponse', () {
    // Captured from: GET /api/v1/route/transit (bus itinerary, Tunis).
    final busItinerary = '''
    {
      "best_fastest": {
        "duration": 900.0,
        "duration_min": 15.0,
        "transfers": 0,
        "has_walk_transfer": false,
        "steps": [
          {"type":"walk","start":[36.8065,10.1815],"end":[36.8075,10.1825],
           "color":"#8b949e","stop_name":"Marcher 432 m (~6 min) jusqu'au Jardin Thameur",
           "mode":"walk","line":null},
          {"type":"ride","start":[36.8075,10.1825],"end":[36.8190,10.1650],
           "color":"#e03131","stop_name":"Mechtel","mode":"bus","line":"bus_705_12"},
          {"type":"walk","start":[36.8190,10.1650],"end":[36.8200,10.1660],
           "color":"#8b949e","stop_name":"Marcher 170 m (~2 min) jusqu'a destination",
           "mode":"walk","line":null}
        ],
        "fare_dinars": null
      },
      "best_less_walk": null,
      "alternatives": [],
      "source": "local-router"
    }
    ''';

    test('parses the bus itinerary envelope', () {
      final response = RouteResponse.fromJson(
        jsonDecodeCompat(busItinerary),
      );

      expect(response.hasError, isFalse);
      expect(response.source, 'local-router');

      final itinerary = response.primary!;
      expect(itinerary.duration, 900.0);
      expect(itinerary.durationMin, 15.0);
      expect(itinerary.transfers, 0);
      expect(itinerary.steps, hasLength(3));
      expect(itinerary.fareDinars, isNull);
      expect(itinerary.hasFare, isFalse);
    });

    test('decodes [lat, lon] pairs in the Tunisia orientation', () {
      final response = RouteResponse.fromJson(
        jsonDecodeCompat(busItinerary),
      );
      final first = response.primary!.steps.first;

      // Tunis is ~36.8 N / ~10.2 E. A swapped decoder would put this near
      // lat 10.18, lon 36.80 (the Indian Ocean / Gulf of Aden).
      expect(first.start.latitude, closeTo(36.8065, 1e-9));
      expect(first.start.longitude, closeTo(10.1815, 1e-9));
      expect(first.start.latitude, greaterThan(30));
      expect(first.start.longitude, lessThan(12));
    });

    test('exposes step types, modes and line labels', () {
      final steps = RouteResponse.fromJson(
        jsonDecodeCompat(busItinerary),
      ).primary!.steps;

      expect(steps[0].type, 'walk');
      expect(steps[0].isWalk, isTrue);
      expect(steps[1].type, 'ride');
      expect(steps[1].isRide, isTrue);
      expect(steps[1].mode, 'bus');
      expect(steps[2].isWalk, isTrue);

      expect(
        RouteResponse.fromJson(jsonDecodeCompat(busItinerary))
            .primary!
            .lineLabels,
        ['bus_705_12'],
      );
    });

    test('keeps backend hex colours, validating the format', () {
      final steps = RouteResponse.fromJson(
        jsonDecodeCompat(busItinerary),
      ).primary!.steps;

      expect(steps[0].hexColor, '#8b949e');
      expect(steps[1].hexColor, '#e03131');
    });

    test('parses the taxi single-step payload', () {
      // Captured from: GET /api/v1/route/transit (taxi fallback).
      const taxiJson = '''
      {
        "best_fastest": {
          "duration": 510.0,
          "duration_min": 8.5,
          "transfers": 0,
          "has_walk_transfer": false,
          "steps": [
            {"type":"taxi","start":[36.8065,10.1815],"end":[36.8628,10.1957],
             "color":"#8b949e","stop_name":"Taxi — 6.4 km (~9 min, 3.92 DT)",
             "mode":"taxi","line":null}
          ],
          "fare_dinars": 3.92
        },
        "best_less_walk": null,
        "alternatives": [],
        "source": "local-router"
      }
      ''';
      final itinerary = RouteResponse.fromJson(
        jsonDecodeCompat(taxiJson),
      ).primary!;

      expect(itinerary.steps.single.isTaxi, isTrue);
      expect(itinerary.hasFare, isTrue);
      expect(itinerary.fareDinars, 3.92);
      expect(itinerary.lineLabels, isEmpty);
    });

    test('surfaces the HTTP-200 error envelope', () {
      // The router reports "no route" with status 200 + an error field.
      const errorJson = '{"error": "No transit route found", '
          '"source": "local-router"}';
      final response = RouteResponse.fromJson(jsonDecodeCompat(errorJson));

      expect(response.hasError, isTrue);
      expect(response.error, 'No transit route found');
      expect(response.primary, isNull);
    });

    test('falls back to less-walk when fastest is null', () {
      const json = '''
      {
        "best_fastest": null,
        "best_less_walk": {
          "duration": 1200.0, "duration_min": 20.0, "transfers": 1,
          "has_walk_transfer": true, "steps": [], "fare_dinars": 2.0
        },
        "alternatives": [],
        "source": "local-router"
      }
      ''';
      final response = RouteResponse.fromJson(jsonDecodeCompat(json));

      expect(response.primary, isNotNull);
      expect(response.primary!.durationMin, 20.0);
      expect(response.options, hasLength(1));
    });
  });

  group('Station', () {
    test('parses a GeoJSON feature the way the datasource does', () {
      // Captured from: GET /api/v1/stations (first feature).
      const feature = '''
      {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [10.6415928, 35.823063]},
        "properties": {
          "id": "sousse_bab_jdid",
          "name": "Sousse Bab Jdid",
          "lines": [
            {"route_short_name": null, "route_color": "829EC0",
             "direction": "Sousse Bab Jdid"},
            {"route_short_name": "", "route_color": "407E15",
             "direction": "Mahdia"}
          ]
        }
      }
      ''';
      final json = jsonDecodeCompat(feature);
      final coords = json['geometry']['coordinates'] as List;

      // GeoJSON order is [lon, lat] — the opposite of transit steps.
      final station = Station(
        id: json['properties']['id'] as String,
        name: json['properties']['name'] as String,
        lat: (coords[1] as num).toDouble(),
        lon: (coords[0] as num).toDouble(),
      );

      expect(station.name, 'Sousse Bab Jdid');
      expect(station.lat, closeTo(35.823063, 1e-9));
      expect(station.lon, closeTo(10.6415928, 1e-9));
    });

    test('treats an empty short name as absent', () {
      const line = StationLineRef(routeShortName: '', direction: 'Mahdia');
      expect(line.shortName, isNull);
      expect(line.label, 'Mahdia');
    });
  });

  group('Line', () {
    test('parses the lines envelope', () {
      // Captured from: GET /api/v1/lines?limit=1
      const json = '''
      {
        "lines": [
          {"id": "train_1_sncft", "number": "SNCFT", "short_name": null,
           "long_name": null, "mode": "train", "color": null,
           "route_id": "1", "stops_count": 29}
        ],
        "count": 232
      }
      ''';
      final response = LinesResponse.fromJson(jsonDecodeCompat(json));
      final line = response.lines.single;

      expect(response.count, 232);
      expect(line.id, 'train_1_sncft');
      expect(line.mode, 'train');
      expect(line.stopsCount, 29);
      // Falls back through shortName/longName/number to "SNCFT".
      expect(line.displayName, 'SNCFT');
    });

    test('normalises seed colours that omit the leading hash', () {
      expect(
        const Line(id: 'x', color: '829EC0').hexColor,
        '#829EC0',
      );
      expect(const Line(id: 'x', color: '#829ec0').hexColor, '#829ec0');
      // Malformed values are rejected rather than crashing the map paint.
      expect(const Line(id: 'x', color: 'not-a-colour').hexColor, isNull);
      expect(const Line(id: 'x').hexColor, isNull);
    });
  });

  group('Health', () {
    test('parses /api/v1/health', () {
      // Captured live: {"status":"ok","version":"0.2.0",...}
      const json = '{"status":"ok","version":"0.2.0","service":"bledi.tn",'
          '"seed_file":"seed_all_tunisia_routes.tagged.json",'
          '"stations_count":1711,"lines_count":232}';
      final health = Health.fromJson(jsonDecodeCompat(json));

      expect(health.isHealthy, isTrue);
      expect(health.stationsCount, 1711);
      expect(health.linesCount, 232);
      expect(health.version, '0.2.0');
    });
  });

  group('per-step duration estimation', () {
    // The backend fills `duration_min` on the itinerary but NOT per step, so
    // the app estimates from straight-line distance. Getting the assumed speed
    // wrong made a real 19-minute taxi ride display as "3 h 06".
    RouteStep stepOf(String type, {String? mode, double km = 14.0}) {
      // 1 degree of latitude ~ 111.32 km.
      final dLat = km / 111.32;
      return RouteStep(
        type: type,
        start: const LatLng(36.8065, 10.1815),
        end: LatLng(36.8065 + dLat, 10.1815),
        mode: mode,
      );
    }

    test('a taxi leg is not estimated at walking speed', () {
      final taxi = stepOf('taxi', mode: 'taxi');
      final minutes = taxi.estimatedDurationMin();

      // 14 km at ~45 km/h ~ 19 min. At walking speed it would be ~3 hours.
      expect(minutes, lessThan(30));
      expect(minutes, greaterThan(12));
    });

    test('a walk leg uses walking speed', () {
      final walk = stepOf('walk', mode: 'walk');
      // 14 km at 4.5 km/h is ~3 h 07.
      expect(walk.estimatedDurationMin(), greaterThan(150));
    });

    test('rail is faster than road, metro faster than bus', () {
      final train = stepOf('ride', mode: 'train').estimatedDurationMin();
      final bus = stepOf('ride', mode: 'bus').estimatedDurationMin();
      final metro = stepOf('ride', mode: 'metro').estimatedDurationMin();

      expect(train, lessThan(bus));
      expect(metro, lessThan(bus));
      expect(bus, lessThan(stepOf('walk', mode: 'walk').estimatedDurationMin()));
    });

    test('a backend-provided duration always wins over the estimate', () {
      const step = RouteStep(
        type: 'taxi',
        start: LatLng(36.8065, 10.1815),
        end: LatLng(36.93, 10.1815),
        durationMin: 19,
      );
      expect(step.estimatedDurationMin(), 19);
    });

    test('a zero-length step estimates zero', () {
      const step = RouteStep(
        type: 'walk',
        start: LatLng(36.8065, 10.1815),
        end: LatLng(36.8065, 10.1815),
      );
      expect(step.estimatedDurationMin(), 0);
      expect(step.distanceMeters, 0);
    });
  });

  group('TransportMode classification', () {
    test('maps backend mode names to categories', () {
      expect(TransportMode.fromName('bus'), TransportMode.bus);
      expect(TransportMode.fromName('train'), TransportMode.rail);
      expect(TransportMode.fromName('metro'), TransportMode.rail);
      expect(TransportMode.fromName('rail'), TransportMode.rail);
      expect(TransportMode.fromName('taxi'), TransportMode.louage);
      expect(TransportMode.fromName('louage'), TransportMode.louage);
      expect(TransportMode.fromName('louage_red'), TransportMode.louage);
    });

    test('infers mode from seed line ids when mode is absent', () {
      // A stale backend sends only {id, name, lines}; the line names encode
      // the mode: bus_705_12, train_1_sncft, metro_56_tgm, rail_19_a.
      final bus = Station.fromJson({
        'id': 'x',
        'name': 'X',
        'lat': 36.8,
        'lon': 10.18,
        'lines': [
          {'route_short_name': null, 'direction': 'bus_705_12'},
        ],
      });
      expect(bus.transportMode, TransportMode.bus);
      expect(bus.hasDeclaredMode, isFalse);

      final metro = Station.fromJson({
        'id': 'y',
        'name': 'Y',
        'lat': 36.8,
        'lon': 10.18,
        'lines': [
          {'route_short_name': 'metro_56_tgm', 'direction': 'TGM'},
        ],
      });
      expect(metro.transportMode, TransportMode.rail);
    });

    test('prefers the declared mode over the line-id fallback', () {
      final station = Station.fromJson({
        'id': 'z',
        'name': 'Z',
        'lat': 36.8,
        'lon': 10.18,
        'mode': 'metro',
        'lines': [
          {'route_short_name': 'bus_705_12', 'direction': 'bus'},
        ],
      });
      expect(station.transportMode, TransportMode.rail);
      expect(station.hasDeclaredMode, isTrue);
    });

    test('unrecognised and empty modes degrade to unknown, never throw', () {
      expect(TransportMode.fromName(null), TransportMode.unknown);
      expect(TransportMode.fromName(''), TransportMode.unknown);
      expect(TransportMode.fromName('teletransport'), TransportMode.unknown);
      expect(TransportMode.all, hasLength(4));
    });

    test('a station with nothing usable resolves to unknown', () {
      final station = Station.fromJson({
        'id': 'q',
        'name': 'Q',
        'lat': 36.8,
        'lon': 10.18,
      });
      expect(station.transportMode, TransportMode.unknown);
    });
  });

  group('AppTheme', () {
    test('maps backend mode names to stable colours', () {
      expect(AppTheme.stepColor('metro'), AppTheme.metroColor);
      expect(AppTheme.stepColor('bus'), AppTheme.busColor);
      expect(AppTheme.stepColor('train'), AppTheme.trainColor);
      // Unknown modes must not throw.
      expect(AppTheme.stepColor('teletransport'), AppTheme.walkColor);
      expect(AppTheme.stepColor(null), AppTheme.walkColor);
    });

    test('the product palette is green / red / yellow', () {
      expect(AppTheme.modeColor(TransportMode.rail), AppTheme.railColor);
      expect(AppTheme.modeColor(TransportMode.bus), AppTheme.busColor);
      expect(AppTheme.modeColor(TransportMode.louage), AppTheme.louageColor);
      expect(AppTheme.modeColor(TransportMode.unknown), AppTheme.unknownColor);

      // Distinct hues, so the three categories never look alike.
      final colors = {
        AppTheme.railColor,
        AppTheme.busColor,
        AppTheme.louageColor,
      };
      expect(colors, hasLength(3));
    });
  });
}

/// Small shim so the fixtures above can be pasted as raw JSON strings.
Map<String, dynamic> jsonDecodeCompat(String source) =>
    jsonDecode(source) as Map<String, dynamic>;