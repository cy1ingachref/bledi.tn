import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

import 'package:bledi_app/data/models/itinerary.dart';

/// Build a step from JSON, the way the backend sends it.
RouteStep stepFrom(Map<String, dynamic> json) => RouteStep.fromJson(json);

Map<String, dynamic> ride({
  required double lat1,
  required double lon1,
  required double lat2,
  required double lon2,
  String to = 'B',
  String? line = 'bus_1',
  String mode = 'bus',
  List<List<double>>? geometry,
}) => {
  'type': 'ride',
  'start': [lat1, lon1],
  'end': [lat2, lon2],
  'stop_name': to,
  'mode': mode,
  'line': line,
  'geometry': ?geometry,
  if (geometry != null) 'has_geometry': geometry.length >= 2,
};

void main() {
  group('RouteStep.path', () {
    test('uses real geometry when present', () {
      final s = stepFrom(
        ride(
          lat1: 36.8,
          lon1: 10.1,
          lat2: 36.9,
          lon2: 10.2,
          geometry: [
            [36.8, 10.1],
            [36.85, 10.15],
            [36.9, 10.2],
          ],
        ),
      );
      expect(s.hasGeometry, isTrue);
      expect(s.followsRealPath, isTrue);
      expect(s.path.length, 3);
      expect(s.path.first, const LatLng(36.8, 10.1));
      expect(s.path.last, const LatLng(36.9, 10.2));
    });

    test('falls back to a straight line when geometry is absent', () {
      final s = stepFrom(ride(lat1: 36.8, lon1: 10.1, lat2: 36.9, lon2: 10.2));
      expect(s.hasGeometry, isFalse);
      expect(s.followsRealPath, isFalse);
      expect(s.path, [const LatLng(36.8, 10.1), const LatLng(36.9, 10.2)]);
    });

    test('drops geometry that does not start and end at the step endpoints', () {
      // A geometry that fails to reach the destination would visibly detach the
      // line from the stop marker, so it must be rejected in favour of the
      // straight line rather than trusted.
      final s = stepFrom(
        ride(
          lat1: 36.8,
          lon1: 10.1,
          lat2: 36.9,
          lon2: 10.2,
          geometry: [
            [36.7, 10.0],
            [36.85, 10.15],
            [36.95, 10.3],
          ],
        ),
      );
      expect(s.geometry.length, 3, reason: 'raw geometry is still decoded');
      expect(s.path.length, 2, reason: 'but is not drawn');
      expect(s.path.first, const LatLng(36.8, 10.1));
      expect(s.path.last, const LatLng(36.9, 10.2));
    });

    test('rejects geometry with a single point', () {
      final s = stepFrom(
        ride(
          lat1: 36.8,
          lon1: 10.1,
          lat2: 36.9,
          lon2: 10.2,
          geometry: [
            [36.8, 10.1],
          ],
        ),
      );
      expect(s.path.length, 2);
    });
  });

  group('Itinerary.milestones', () {
    Itinerary withSteps(List<Map<String, dynamic>> raw) => Itinerary.fromJson({
      'duration': 3600.0,
      'duration_min': 60.0,
      'steps': raw,
    });

    test('lists every station passed, in travel order', () {
      final it = withSteps([
        ride(lat1: 36.80, lon1: 10.18, lat2: 36.81, lon2: 10.19, to: 'A'),
        ride(lat1: 36.81, lon1: 10.19, lat2: 36.82, lon2: 10.20, to: 'B'),
        ride(lat1: 36.82, lon1: 10.20, lat2: 36.83, lon2: 10.21, to: 'C'),
      ]);
      final m = it.milestones;
      expect(m.map((x) => x.name).toList(), ['A', 'B', 'C']);
      expect(m.map((x) => x.order).toList(), [1, 2, 3]);
      expect(m.every((x) => x.kind == RouteMilestoneKind.stop), isTrue);
    });

    test('surfaces intermediate stops the old marker rule dropped', () {
      // The regression: markers were drawn only where consecutive steps failed
      // to meet, so every intermediate stop of a continuous ride had no marker.
      // Rades/Hammam Lif/Grombalia on Tunis->Sfax were reported but invisible.
      final it = withSteps([
        ride(lat1: 36.80, lon1: 10.18, lat2: 36.81, lon2: 10.19, to: 'Rades'),
        ride(
          lat1: 36.81,
          lon1: 10.19,
          lat2: 36.82,
          lon2: 10.20,
          to: 'Hammam Lif',
        ),
        ride(lat1: 36.82, lon1: 10.20, lat2: 36.83, lon2: 10.21, to: 'Sfax'),
      ]);
      expect(it.milestones.length, 3);
      expect(
        it.milestones.where((m) => m.isIntermediate).length,
        3,
        reason: 'all three are intermediate stops, not just the endpoints',
      );
    });

    test('skips zero-length steps', () {
      final it = withSteps([
        ride(lat1: 36.8, lon1: 10.1, lat2: 36.8, lon2: 10.1, to: 'Same'),
        ride(lat1: 36.8, lon1: 10.1, lat2: 36.9, lon2: 10.2, to: 'Next'),
      ]);
      expect(it.milestones.map((m) => m.name).toList(), ['Next']);
    });

    test('skips unnamed steps', () {
      final it = withSteps([
        ride(lat1: 36.8, lon1: 10.1, lat2: 36.9, lon2: 10.2, to: ''),
      ]);
      expect(it.milestones, isEmpty);
    });

    test('classifies walk and taxi legs distinctly from stops', () {
      final it = withSteps([
        {
          'type': 'walk',
          'start': [36.80, 10.18],
          'end': [36.81, 10.19],
          'stop_name': 'Corner',
        },
        ride(lat1: 36.81, lon1: 10.19, lat2: 36.82, lon2: 10.20, to: 'Stop'),
        {
          'type': 'taxi',
          'start': [36.82, 10.20],
          'end': [36.90, 10.30],
          'stop_name': 'Destination',
        },
      ]);
      final kinds = it.milestones.map((m) => m.kind).toList();
      expect(kinds[0], RouteMilestoneKind.walk);
      expect(kinds[1], RouteMilestoneKind.stop);
      expect(kinds[2], RouteMilestoneKind.taxi);
    });
  });

  group('Itinerary.continuousPath', () {
    test('joins legs without gaps or repeated joints', () {
      final it = Itinerary.fromJson({
        'duration': 3600.0,
        'duration_min': 60.0,
        'steps': [
          ride(
            lat1: 36.80,
            lon1: 10.18,
            lat2: 36.81,
            lon2: 10.19,
            geometry: [
              [36.80, 10.18],
              [36.805, 10.185],
              [36.81, 10.19],
            ],
          ),
          ride(
            lat1: 36.81,
            lon1: 10.19,
            lat2: 36.82,
            lon2: 10.20,
            line: 'train_1',
            geometry: [
              [36.81, 10.19],
              [36.815, 10.195],
              [36.82, 10.20],
            ],
          ),
        ],
      });
      final path = it.continuousPath;
      expect(path.length, 5, reason: '3 + 3 minus the shared joint');
      // No consecutive duplicates anywhere.
      for (var i = 1; i < path.length; i++) {
        expect(path[i], isNot(path[i - 1]));
      }
      expect(path.first, const LatLng(36.80, 10.18));
      expect(path.last, const LatLng(36.82, 10.20));
    });

    test('is continuous across a walk leg', () {
      final it = Itinerary.fromJson({
        'duration': 3600.0,
        'duration_min': 60.0,
        'steps': [
          ride(lat1: 36.80, lon1: 10.18, lat2: 36.81, lon2: 10.19, to: 'A'),
          {
            'type': 'walk',
            'start': [36.81, 10.19],
            'end': [36.815, 10.195],
            'stop_name': 'Interchange',
          },
          ride(
            lat1: 36.815,
            lon1: 10.195,
            lat2: 36.82,
            lon2: 10.20,
            to: 'B',
            line: 'train_1',
          ),
        ],
      });
      final path = it.continuousPath;
      expect(path.first, const LatLng(36.80, 10.18));
      expect(path.last, const LatLng(36.82, 10.20));
      expect(path.length, 4);
    });

    test('handles a single leg', () {
      final it = Itinerary.fromJson({
        'duration': 600.0,
        'duration_min': 10.0,
        'steps': [ride(lat1: 36.8, lon1: 10.1, lat2: 36.9, lon2: 10.2)],
      });
      expect(it.continuousPath.length, 2);
    });

    test('hasRealGeometry is false when every leg is a straight line', () {
      final it = Itinerary.fromJson({
        'duration': 600.0,
        'duration_min': 10.0,
        'steps': [ride(lat1: 36.8, lon1: 10.1, lat2: 36.9, lon2: 10.2)],
      });
      expect(it.hasRealGeometry, isFalse);
    });

    test('hasRealGeometry is true when any leg has geometry', () {
      final it = Itinerary.fromJson({
        'duration': 600.0,
        'duration_min': 10.0,
        'steps': [
          ride(lat1: 36.8, lon1: 10.1, lat2: 36.9, lon2: 10.2),
          ride(
            lat1: 36.9,
            lon1: 10.2,
            lat2: 37.0,
            lon2: 10.3,
            line: 'train_1',
            geometry: [
              [36.9, 10.2],
              [36.95, 10.25],
              [37.0, 10.3],
            ],
          ),
        ],
      });
      expect(it.hasRealGeometry, isTrue);
    });
  });

  group('allPoints', () {
    test('includes geometry so the camera fits the real route', () {
      final it = Itinerary.fromJson({
        'duration': 600.0,
        'duration_min': 10.0,
        'steps': [
          ride(
            lat1: 36.8,
            lon1: 10.1,
            lat2: 36.9,
            lon2: 10.2,
            geometry: [
              [36.8, 10.1],
              [36.82, 10.15],
              [36.85, 10.18],
              [36.9, 10.2],
            ],
          ),
        ],
      });
      expect(it.allPoints.length, 4, reason: 'not just the two endpoints');
    });
  });

  group('decoding', () {
    test('parses a geometry-bearing step from backend JSON', () {
      const payload = '''{
        "type": "ride",
        "start": [36.8, 10.1],
        "end": [36.9, 10.2],
        "mode": "train",
        "line": "train_24_sncft",
        "geometry": [[36.8,10.1],[36.85,10.15],[36.9,10.2]],
        "has_geometry": true
      }''';
      final s = RouteStep.fromJson(json.decode(payload));
      expect(s.mode, 'train');
      expect(s.line, 'train_24_sncft');
      expect(s.geometry.length, 3);
      expect(s.hasGeometry, isTrue);
      expect(s.geometry[1], const LatLng(36.85, 10.15));
    });

    test('a step without geometry decodes to an empty list', () {
      const payload = '{"type":"walk","start":[36.8,10.1],"end":[36.9,10.2]}';
      final s = RouteStep.fromJson(json.decode(payload));
      expect(s.geometry, isEmpty);
      expect(s.hasGeometry, isFalse);
      expect(s.path.length, 2);
    });
  });
}
