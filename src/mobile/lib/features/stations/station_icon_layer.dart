
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';

import '../../data/models/station.dart';
import 'station_map_model.dart';

/// Paints every stop as a mode-coloured pin carrying a white transport glyph.
///
/// Why a custom canvas rather than [CircleLayer]: circle markers draw a filled
/// disc and nothing else, so bus, taxi, train and metro stops are only
/// distinguishable by hue — which fails for a red/green/yellow trio on a
/// phone screen, in bright sun, or for a colour-blind reader. `flutter_map`
/// 8.3.2 has no glyph-capable layer (`CircleLayer`, `MarkerLayer`,
/// `OverlayImageLayer` only), and 4 200 `MarkerLayer` widgets would rebuild the
/// whole layer on every pan. One painter draws every visible stop per frame.
///
/// Two zoom states, because glyphs are unreadable when a stop is a few pixels
/// wide:
///   * below [iconZoom] — a coloured dot, the only thing that can be read
///   * at/above [iconZoom] — a pin with the transport glyph inside it
///
/// The threshold is a `static const` rather than a provider so the painter can
/// be `const` and the layer can skip work entirely when nothing is drawn.
class StationIconLayer extends StatelessWidget {
  const StationIconLayer({super.key, required this.stations});

  final List<MapStation> stations;

  @override
  Widget build(BuildContext context) {
    if (stations.isEmpty) return const SizedBox.shrink();
    return IgnorePointer(
      child: CustomPaint(
        // Read here, in the widget's own build: a CustomPainter has no
        // BuildContext, so `paint` cannot do the inherited-widget lookup
        // itself. Building inside FlutterMap's scope makes this resolve.
        painter: _StationIconPainter(
          stations: stations,
          camera: MapCamera.maybeOf(context),
        ),
        size: Size.infinite,
      ),
    );
  }

  /// Zoom at which glyphs replace plain dots.
  static const double iconZoom = 12;

  /// Dot radius below the threshold.
  static const double _dotRadius = 3;

  /// Pin radius at [iconZoom]. A city tap lands on exactly 12, so this is the
  /// size that has to be legible: a 9 px pin holds a ~4 px glyph, which reads
  /// as a smudge rather than a bus.
  static const double _pinRadius = 13;

  /// Extra radius per zoom level past [iconZoom].
  static const double _radiusPerZoom = 2;

  /// Hard cap, so zooming to a single stop does not bury the map under icons.
  static const double _maxPinRadius = 22;

}

class _StationIconPainter extends CustomPainter {
  _StationIconPainter({required this.stations, required this.camera});

  final List<MapStation> stations;

  final MapCamera? camera;

  /// Glyphs are drawn as paths rather than `TextPainter` with an icon font: no
  /// font asset, no `flutter_map` glyph layer, and the shapes stay crisp at any
  /// device pixel ratio.
  static final Map<TransportMode, Path> _glyphs = _buildGlyphs();

  /// Bus: wide and low, with a windscreen band. Wide-vs-tall is the whole
  /// distinction from [\_trainPath] at 20 px — a thin window strip is not
  /// something that survives at this size, so the silhouette does the work.
  static Path _busPath(double s) => Path()
    ..addRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(center: Offset.zero, width: s * 0.86, height: s * 0.66),
        Radius.circular(s * 0.1),
      ),
    )
    // Windscreen band, deliberately thick: a hairline would vanish.
    ..addRect(Rect.fromLTWH(-s * 0.32, -s * 0.24, s * 0.64, s * 0.16));

  /// Train: tall and narrow with a domed roof and a windscreen.
  static Path _trainPath(double s) => Path()
    ..addRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(center: Offset.zero, width: s * 0.54, height: s * 0.92),
        Radius.circular(s * 0.24),
      ),
    )
    ..addRect(Rect.fromLTWH(-s * 0.19, -s * 0.28, s * 0.38, s * 0.24));

  /// Louage / taxi: a car seen side-on, with a roof sign above the cabin.
  ///
  /// Deliberately the widest, lowest silhouette of the three, plus the roof
  /// sign that no other mode carries.
  static Path _taxiPath(double s) => Path()
    // cabin + body as one closed outline
    ..moveTo(-s * 0.46, s * 0.12)
    ..lineTo(-s * 0.3, s * 0.12)
    ..lineTo(-s * 0.17, -s * 0.14)
    ..lineTo(s * 0.17, -s * 0.14)
    ..lineTo(s * 0.3, s * 0.12)
    ..lineTo(s * 0.46, s * 0.12)
    ..lineTo(s * 0.46, s * 0.36)
    ..lineTo(-s * 0.46, s * 0.36)
    ..close()
    // roof sign
    ..addRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(center: Offset(0, -s * 0.28), width: s * 0.34, height: s * 0.16),
        Radius.circular(s * 0.05),
      ),
    );

  /// Unclassified: a plain dot — the same idea as the zoomed-out marker, so
  /// "we do not know" never looks like a mode we do know.
  static Path _otherPath(double s) => Path()
    ..addOval(Rect.fromCenter(center: Offset.zero, width: s * 0.4, height: s * 0.4));

  static Map<TransportMode, Path> _buildGlyphs() {
    final s = 10.0;
    // TransportMode has four categories, not five: train and metro both
    // resolve to `rail`, taxi and louage both to `louage`. Metro-vs-train and
    // taxi-vs-louage are not distinguishable here, so a single glyph covers
    // each pair rather than inventing a category the model does not have.
    return {
      TransportMode.bus: _busPath(s),
      TransportMode.louage: _taxiPath(s),
      TransportMode.rail: _trainPath(s),
      TransportMode.unknown: _otherPath(s),
    };
  }

  @override
  void paint(Canvas canvas, Size size) {
    final camera = this.camera;
    if (camera == null) return;

    final zoom = camera.zoom;
    final showIcons = zoom >= StationIconLayer.iconZoom;
    final pinRadius = showIcons
        ? (StationIconLayer._pinRadius +
                (zoom - StationIconLayer.iconZoom) * StationIconLayer._radiusPerZoom)
            .clamp(StationIconLayer._pinRadius, StationIconLayer._maxPinRadius)
        : StationIconLayer._dotRadius;

    final paint = Paint()..style = PaintingStyle.fill;
    final border = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = showIcons ? 1.6 : 0.8
      ..color = Colors.white.withValues(alpha: showIcons ? 0.95 : 0.7);
    final glyphPaint = Paint()
      ..style = PaintingStyle.fill
      ..color = Colors.white;

    for (final station in stations) {
      final offset = camera.latLngToScreenOffset(station.point);
      // Skip anything off-screen: the national view holds 4 200 stops and only
      // a few hundred are ever visible.
      if (offset.dx < -40 || offset.dy < -40 ||
          offset.dx > size.width + 40 || offset.dy > size.height + 40) {
        continue;
      }

      if (!showIcons) {
        canvas.drawCircle(offset, StationIconLayer._dotRadius, paint..color = station.color);
        canvas.drawCircle(offset, StationIconLayer._dotRadius, border);
        continue;
      }

      final path = _glyphs[station.mode] ?? _glyphs[TransportMode.unknown]!;
      canvas.drawCircle(offset, pinRadius, paint..color = station.color);
      canvas.drawCircle(offset, pinRadius, border);
      canvas.save();
      canvas.translate(offset.dx, offset.dy);
      // Fill most of the pin: at 10 units scaled by radius/10 the glyph
      // spanned about half the disc and read as a smudge.
      canvas.scale(pinRadius / 7.0);
      canvas.drawPath(path, glyphPaint);
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(_StationIconPainter oldDelegate) =>
      oldDelegate.stations != stations || oldDelegate.camera != camera;
}
