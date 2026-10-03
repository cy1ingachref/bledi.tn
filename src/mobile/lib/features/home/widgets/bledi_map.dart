import 'dart:async';

import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/constants.dart';
import '../../../core/theme.dart';
import '../../../core/utils/state.dart';
import '../../../data/models/itinerary.dart';
import '../../../providers/providers.dart';
import '../../stations/station_map_layer.dart';
import '../../stations/station_map_model.dart';

/// Shared OSM tile layer configuration.
///
/// OSM's public tile server requires a valid identifying User-Agent/Referer
/// and fair use; see https://operations.osmfoundation.org/policies/tiles/
TileLayer buildOsmTileLayer() => TileLayer(
  urlTemplate: AppConstants.osmTileUrl,
  userAgentPackageName: 'tn.bledi.app',
  maxNativeZoom: 19,
);

/// Renders the selected route as polylines plus stop markers.
class RouteOverlay extends ConsumerWidget {
  const RouteOverlay({super.key, required this.itinerary});

  final Itinerary itinerary;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final steps = itinerary.steps;
    if (steps.isEmpty) return const SizedBox.shrink();

    return PolylineLayer(
      polylines: [
        // A soft casing drawn under the whole route. One continuous path means
        // the line reads as a single journey from departure to destination
        // instead of a row of disconnected two-point segments with visible
        // seams at every transfer.
        if (itinerary.continuousPath.length >= 2)
          Polyline(
            points: itinerary.continuousPath,
            strokeWidth: 11,
            color: Colors.white.withValues(alpha: 0.55),
            borderColor: Colors.white.withValues(alpha: 0.0),
            borderStrokeWidth: 0,
            strokeCap: StrokeCap.round,
            strokeJoin: StrokeJoin.round,
          ),
        // Then each leg on top, keeping its own mode colour and dash pattern so
        // walking legs still read as walking.
        for (final step in steps)
          if (step.start != step.end)
            Polyline(
              points: step.path,
              strokeWidth: step.isWalk ? 4 : 7,
              color: _colorFor(context, step).withValues(alpha: step.isWalk ? 0.9 : 1.0),
              borderColor: Colors.white.withValues(alpha: 0.9),
              borderStrokeWidth: step.isWalk ? 0.8 : 1.4,
              pattern: step.isWalk
                  ? StrokePattern.dashed(segments: const [10, 8])
                  : const StrokePattern.solid(),
              strokeCap: StrokeCap.round,
              strokeJoin: StrokeJoin.round,
            ),
      ],
    );
  }

  /// Markers for the route: every station it passes, in travel order.
  ///
  /// The previous rule drew a dot only where two consecutive steps failed to
  /// meet, which meant the intermediate stops of a long ride were never
  /// rendered at all -- Tunis -> Sfax reported Rades, Hammam Lif and
  /// Grombalia in the step list and showed none of them. Milestones now come
  /// from every leg, so each of those stops gets a numbered dot.
  static List<Marker> buildMarkers(Itinerary itinerary) {
    final steps = itinerary.steps;
    final lastIndex = steps.length - 1;
    final milestones = itinerary.milestones;
    // Map each milestone back to the step that produced it, so a marker can
    // borrow that step's mode colour.
    final stepForMilestone = <int, RouteStep>{};
    var mi = 0;
    for (var i = 0; i < steps.length; i++) {
      final step = steps[i];
      if (step.start == step.end) continue;
      if (step.endLabel.isEmpty) continue;
      stepForMilestone[mi] = step;
      mi++;
    }

    return [
      for (var i = 0; i < milestones.length; i++)
        if (milestones[i].point == steps[lastIndex].end)
          routeEndpointMarker(
            milestones[i].point,
            stepForMilestone[i] ?? steps[lastIndex],
          )
        else
          routeMilestoneMarker(milestones[i], stepForMilestone[i]),
    ];
  }

  static Color _colorFor(BuildContext context, RouteStep step) {
    final hex = step.hexColor;
    if (hex != null) {
      final parsed = _parseHex(hex);
      if (parsed != null) return parsed;
    }
    return AppTheme.stepColor(step.isRide ? step.mode : step.type);
  }

  static Color? _parseHex(String hex) {
    final value = hex.replaceFirst('#', '');
    if (value.length != 6) return null;
    final parsed = int.tryParse(value, radix: 16);
    if (parsed == null) return null;
    return Color(0xFF000000 | parsed);
  }
}

/// A numbered milestone dot for a station along the route.
///
/// The number is the station's order along the journey, so the sequence reads
/// left-to-right down the line and the rider can match it against the step list.
/// Size encodes importance: transfers are largest, plain intermediate stops
/// smaller, and walk/taxi touches are the smallest so they do not compete with
/// the transit stops they sit between.
Marker routeMilestoneMarker(RouteMilestone milestone, RouteStep? step) {
  final color = step == null
      ? const Color(0xFF6B7280)
      : _colorFor2(step).withValues(alpha: 0.95);
  final diameter = switch (milestone.kind) {
    RouteMilestoneKind.transfer => 22.0,
    RouteMilestoneKind.stop => 17.0,
    RouteMilestoneKind.walk || RouteMilestoneKind.taxi => 13.0,
    _ => 17.0,
  };
  return Marker(
    point: milestone.point,
    width: diameter,
    height: diameter,
    alignment: Alignment.center,
    child: Container(
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 2.5),
        boxShadow: const [
          BoxShadow(color: Color(0x33000000), blurRadius: 4, offset: Offset(0, 1)),
        ],
      ),
      alignment: Alignment.center,
      child: Text(
        '${milestone.order}',
        style: TextStyle(
          color: Colors.white,
          fontSize: diameter <= 13 ? 8 : (diameter <= 17 ? 9.5 : 10.5),
          fontWeight: FontWeight.w700,
          height: 1,
        ),
      ),
    ),
  );
}

/// Colour helper that tolerates a null step (unlike the private [_colorFor],
/// which needs a BuildContext).
Color _colorFor2(RouteStep step) {
  final hex = step.hexColor;
  if (hex != null) {
    final parsed = int.tryParse(hex.replaceFirst('#', ''), radix: 16);
    if (parsed != null) return Color(0xFF000000 | parsed);
  }
  return AppTheme.stepColor(step.isRide ? (step.mode ?? 'bus') : step.type);
}

/// Larger mode-coloured pin for the final destination.
Marker routeEndpointMarker(LatLng point, RouteStep step) => Marker(
  point: point,
  width: 30,
  height: 30,
  child: DecoratedBox(
    decoration: BoxDecoration(
      color: AppTheme.stepColor(step.isRide ? step.mode : step.type),
      shape: BoxShape.circle,
      border: Border.all(color: Colors.white, width: 3),
      boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 6)],
    ),
    child: Icon(
      step.isRide ? Icons.directions_bus : Icons.place,
      size: 14,
      color: Colors.white,
    ),
  ),
);

/// The interactive map: OSM tiles, the route overlay, and the origin /
/// destination pins.
class BlediMap extends ConsumerStatefulWidget {
  const BlediMap({super.key, required this.controller, required this.onLongPress, this.onStationTap, this.onCityTap, this.children = const []});

  final MapController controller;

  /// Fired when the user long-presses to drop a pin.
  final void Function(LatLng point) onLongPress;

  /// Fired when a station dot in the overlay is tapped.
  final void Function(MapStation station)? onStationTap;

  /// Fired when a city label is tapped.
  final void Function(CityGroup city)? onCityTap;

  /// Extra layers inserted below the route overlay.
  final List<Widget> children;

  @override
  ConsumerState<BlediMap> createState() => _BlediMapState();
}

class _BlediMapState extends ConsumerState<BlediMap> {
  bool _didAutoFitRoute = false;

  @override
  Widget build(BuildContext context) {
    final selection = ref.watch(routeSelectionProvider);
    final result = ref.watch(routingProvider);
    final itinerary = result.itinerary;
    final scheme = Theme.of(context).colorScheme;
    final showStations = ref.watch(stationOverlayProvider);

    // Fit the camera to the route once, when it first arrives.
    if (itinerary != null && !_didAutoFitRoute && itinerary.allPoints.length >= 2) {
      _didAutoFitRoute = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        widget.controller.fitCamera(
          CameraFit.coordinates(
            coordinates: itinerary.allPoints,
            padding: const EdgeInsets.fromLTRB(56, 96, 56, 240),
            maxZoom: 16,
          ),
        );
      });
    }

    return FlutterMap(
      mapController: widget.controller,
      options: MapOptions(
        initialCenter: LatLng(
          AppConstants.tunisLat,
          AppConstants.tunisLon,
        ),
        initialZoom: AppConstants.tunisZoom,
        minZoom: 5,
        maxZoom: 18,
        backgroundColor: scheme.surfaceContainerHighest,
        cameraConstraint: CameraConstraint.contain(
          bounds: LatLngBounds(
            LatLng(AppConstants.tunisiaSouthLat, AppConstants.tunisiaWestLon),
            LatLng(AppConstants.tunisiaNorthLat, AppConstants.tunisiaEastLon),
          ),
        ),
        onLongPress: (tapPosition, point) => widget.onLongPress(point),
        // Feed the camera zoom to the provider so the station overlay can
        // switch between clustered and individual dots.
        onPositionChanged: (cameraPosition, hasGesture) {
          ref.read(mapZoomProvider.notifier).update(cameraPosition.zoom);
        },
        interactionOptions: const InteractionOptions(
          flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
        ),
      ),
      children: [
        buildOsmTileLayer(),
        ...widget.children,
        // Station/stop overlay sits under the route so the itinerary always
        // reads on top of the network.
        if (showStations)
          StationMapLayer(
            onStationTap: widget.onStationTap,
            onCityTap: widget.onCityTap,
          ),
if (itinerary != null && itinerary.steps.isNotEmpty) ...[
          RouteOverlay(itinerary: itinerary),
          MarkerLayer(markers: RouteOverlay.buildMarkers(itinerary)),
        ],
        _EndpointLayer(
          origin: selection.origin,
          destination: selection.destination,
        ),
        const _Attribution(),
      ],
    );
  }
}

/// Origin (green) and destination (red) pins.
class _EndpointLayer extends StatelessWidget {
  const _EndpointLayer({this.origin, this.destination});

  final MapPoint? origin;
  final MapPoint? destination;

  @override
  Widget build(BuildContext context) {
    return MarkerLayer(
      markers: [
        if (origin != null)
          Marker(
            point: LatLng(origin!.lat, origin!.lon),
            width: 32,
            height: 32,
            child: const _EndpointPin(color: Color(0xFF2F9E44), icon: Icons.trip_origin),
          ),
        if (destination != null)
          Marker(
            point: LatLng(destination!.lat, destination!.lon),
            width: 32,
            height: 32,
            child: const _EndpointPin(color: Color(0xFFE03131), icon: Icons.place),
          ),
      ],
    );
  }
}

class _EndpointPin extends StatelessWidget {
  const _EndpointPin({required this.color, required this.icon});

  final Color color;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
        boxShadow: const [BoxShadow(color: Colors.black38, blurRadius: 8)],
      ),
      child: Icon(icon, color: Colors.white, size: 16),
    );
  }
}

/// OSM attribution — required by the tile usage policy.
class _Attribution extends StatelessWidget {
  const _Attribution();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.bottomRight,
      child: Padding(
        padding: const EdgeInsets.only(right: 6, bottom: 4),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.75),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            child: Text(
              AppConstants.osmAttribution,
              style: const TextStyle(fontSize: 9, color: Colors.black87),
            ),
          ),
        ),
      ),
    );
  }
}

/// Formats a duration in minutes as `1 h 05` / `45 min`.
String formatDuration(BuildContext context, double minutes) {
  final total = minutes.round();
  final h = total ~/ 60;
  final m = total % 60;
  if (h == 0) return '$m min';
  if (m == 0) return '$h h';
  return '$h h ${m.toString().padLeft(2, '0')}';
}

/// Formats a distance in metres as `450 m` / `3.2 km`.
String formatDistance(double meters) {
  if (meters < 1000) return '${meters.round()} m';
  return '${(meters / 1000).toStringAsFixed(1)} km';
}

/// Localised label for a step type or transport mode.
String stepLabel(BuildContext context, RouteStep step) {
  final key = step.isRide ? (step.mode ?? 'bus') : step.type;
  return switch (key) {
    'walk' => 'walk'.tr(),
    'ride' => 'ride'.tr(),
    'transfer' => 'transfer'.tr(),
    'taxi' => 'taxi'.tr(),
    'bus' => 'bus'.tr(),
    'metro' => 'metro'.tr(),
    'train' => 'train'.tr(),
    'rfr' => 'rfr'.tr(),
    _ => key,
  };
}

/// Icon for a step type or transport mode.
IconData stepIcon(RouteStep step) {
  final key = step.isRide ? (step.mode ?? 'bus') : step.type;
  return switch (key) {
    'walk' => Icons.directions_walk,
    'taxi' => Icons.local_taxi,
    'transfer' => Icons.swap_horiz,
    'metro' => Icons.subway,
    'train' || 'rfr' => Icons.train,
    'bus' => Icons.directions_bus,
    _ => Icons.directions_bus,
  };
}

/// Debounces text input — used by the station search field.
class Debouncer {
  Debouncer(this.duration);

  final Duration duration;
  Timer? _timer;

  void run(void Function() action) {
    _timer?.cancel();
    _timer = Timer(duration, action);
  }

  void dispose() => _timer?.cancel();
}