import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_map/flutter_map.dart';
// Hide latlong2's generic `Path<T>`: it shadows dart:ui's Path, which is the
// one every glyph and the Canvas spy below are typed against.
import 'package:latlong2/latlong.dart' hide Path;

import 'package:bledi_app/data/models/station.dart';
import 'package:bledi_app/features/stations/station_icon_layer.dart';
import 'package:bledi_app/features/stations/station_map_model.dart';

/// A Canvas that records what was asked of it, so a test can assert that the
/// glyph paths — not just the pin discs — actually reached the canvas.
///
/// Counting pixels or picture operations is not enough: the bug this catches is
/// a painter that draws its circles and quietly skips the glyphs, which still
/// "looks painted" by any coarse measure.
class _RecordingCanvas implements Canvas {
  _RecordingCanvas(this._inner);

  final Canvas _inner;
  int circles = 0;
  int paths = 0;
  int saves = 0;
  final colors = <String>[];

  /// Bounding box of each path drawn, so two modes can be compared on shape
  /// rather than on the mode colour that surrounds them.
  final pathBounds = <String>[];

  @override
  void drawPath(Path path, Paint paint) {
    paths++;
    pathBounds.add(_fmt(path.getBounds()));
    _inner.drawPath(path, paint);
  }

  static String _fmt(Rect r) =>
      '${r.left.toStringAsFixed(2)},${r.top.toStringAsFixed(2)},'
      '${r.width.toStringAsFixed(2)},${r.height.toStringAsFixed(2)}';

  @override
  void drawCircle(Offset c, double radius, Paint paint) {
    circles++;
    colors.add(_paint(paint));
    _inner.drawCircle(c, radius, paint);
  }

  static String _paint(Paint p) =>
      '${(p.color.r * 255).round()},${(p.color.g * 255).round()}'
      ',${(p.color.b * 255).round()}:${p.style.index}';

  @override
  void save() {
    saves++;
    _inner.save();
  }

  @override
  void translate(double dx, double dy) => _inner.translate(dx, dy);

  @override
  void scale(double sx, [double? sy]) => _inner.scale(sx, sy ?? sx);

  @override
  void rotate(double radians) => _inner.rotate(radians);

  @override
  void restore() => _inner.restore();

  @override
  void noSuchMethod(Invocation invocation) {
    // Forward anything else. Reflecting on the member name keeps the spy
    // transparent: the painter must see a working canvas, not one that throws
    // on the first call it does not override.
    // ignore: avoid_dynamic_calls
    (_inner as dynamic).noSuchMethod(invocation);
  }
}

Future<_RecordingCanvas> _paintLayer(
  WidgetTester tester,
  double zoom, {
  required List<MapStation> stations,
}) async {
  final recorder = ui.PictureRecorder();
  final canvas = _RecordingCanvas(Canvas(recorder));

  final controller = MapController();
  await tester.pumpWidget(
    MaterialApp(
      home: FlutterMap(
        mapController: controller,
        options: MapOptions(
          initialCenter: const LatLng(36.8065, 10.1815),
          initialZoom: zoom,
        ),
        children: [StationIconLayer(stations: stations)],
      ),
    ),
  );
  await tester.pumpAndSettle();
  // MapOptions' initialZoom only applies on first layout; re-assert it so each
  // case really runs at its own zoom.
  controller.move(const LatLng(36.8065, 10.1815), zoom);
  await tester.pumpAndSettle();

  final customPaint = tester.widget<CustomPaint>(find.byType(CustomPaint).last);
  customPaint.painter!.paint(canvas, const Size(800, 600));
  return canvas;
}

List<MapStation> sampleStations() => [
      for (var i = 0; i < 5; i++)
        MapStation(
          id: 's$i',
          name: 'S$i',
          lat: 36.8065 + i * 0.002,
          lon: 10.1815,
          mode: i.isEven ? TransportMode.bus : TransportMode.rail,
        ),
    ];

void main() {
  testWidgets('glyphs are painted once zoomed past the threshold',
      (tester) async {
    final out = await _paintLayer(tester, 9, stations: sampleStations());
    expect(out.circles, greaterThan(0), reason: 'dots must paint when zoomed out');
    expect(out.paths, 0, reason: 'no glyphs below the threshold');

    final inn = await _paintLayer(tester, 15, stations: sampleStations());
    expect(inn.circles, greaterThanOrEqualTo(5), reason: 'a pin per station');
    expect(inn.paths, greaterThanOrEqualTo(5),
        reason: 'one glyph path per station, drawn inside the pin');
  });

  testWidgets('every transport mode contributes a distinct glyph',
      (tester) async {
    final stations = [
      for (final mode in TransportMode.values)
        MapStation(id: mode.name, name: mode.name, lat: 36.8065, lon: 10.1815, mode: mode),
    ];
    final canvas = await _paintLayer(tester, 15, stations: stations);
    expect(canvas.paths, TransportMode.values.length,
        reason: 'bus, rail, louage and unknown each need their own glyph');
  });

  testWidgets('a city tap reaches icon zoom', (tester) async {
    // home_screen.dart moves the camera to exactly 12 on a city tap, so the
    // threshold must be at or below that or icons never appear in real use.
    // ignore: avoid_print
    print('iconZoom = ${StationIconLayer.iconZoom}');
    expect(StationIconLayer.iconZoom, lessThanOrEqualTo(12));
    final canvas = await _paintLayer(tester, 12, stations: sampleStations());
    expect(canvas.paths, greaterThan(0),
        reason: 'zooming to a city must reveal glyphs');
  });

  testWidgets('each mode renders a visually distinct glyph', (tester) async {
    final sigs = <String, String>{};
    for (final mode in TransportMode.values) {
      final canvas = await _paintLayer(
        tester,
        16,
        stations: [
          MapStation(id: mode.name, name: mode.name, lat: 36.8065, lon: 10.1815,
              mode: mode),
        ],
      );
      // Record what was drawn, in order, with the colours.
      sigs[mode.name] = canvas.pathBounds.join('|');
    }
    // ignore: avoid_print
    print('  glyph signatures: $sigs');
    // Four modes, four distinct shapes: no two may share a bounding box.
    expect(sigs.values.toSet().length, TransportMode.values.length,
        reason: 'each mode must render differently, got $sigs');
    // A bus is wider than it is tall; a train is the other way round. That
    // single fact is what makes the two tellable apart at map scale, so assert
    // the aspect ratios rather than mere inequality.
    final aspect = <String, double>{};
    for (final e in sigs.entries) {
      final parts = e.value.split(',').map(double.parse).toList();
      aspect[e.key] = parts[2] / parts[3]; // width / height
    }
    // ignore: avoid_print
    print('  aspect ratios (w/h): $aspect');
    expect(aspect[TransportMode.bus.name]!, greaterThan(1.0),
        reason: 'a bus reads as wide');
    expect(aspect[TransportMode.rail.name]!, lessThan(1.0),
        reason: 'a train reads as tall');
    expect(aspect[TransportMode.louage.name]!, greaterThan(1.0),
        reason: 'a taxi reads as wide');
  });

  testWidgets('stations off-screen are skipped', (tester) async {
    // The national view holds 4 200 stops and few are ever visible; skipping
    // the rest is what keeps panning smooth.
    final far = [
      for (var i = 0; i < 50; i++)
        MapStation(
          id: 'f$i',
          name: 'F$i',
          lat: 30.0 + i * 0.05, // ~700 km south of the camera
          lon: 6.5 + i * 0.05,
          mode: TransportMode.bus,
        ),
    ];
    final canvas = await _paintLayer(tester, 15, stations: far);
    expect(canvas.circles, 0, reason: 'nothing on screen, nothing painted');
  });
}
