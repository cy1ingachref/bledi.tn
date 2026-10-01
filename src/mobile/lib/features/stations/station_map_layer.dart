import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../core/utils/transport_mode_l10n.dart';
import '../../data/models/station.dart';
import '../../providers/providers.dart';
import 'station_map_model.dart';

/// Draws every station as an individual coloured dot, grouped by city.
///
/// Design note: this replaces the earlier density clustering, which chained
/// the whole country into a single 1 561-station bubble. Cities are the unit
/// the user actually navigates by, so stations are drawn individually and the
/// city labels are the interactive layer.
///
/// Performance: points are painted with [CircleLayer], which draws onto the map
/// canvas in one repaint. [MarkerLayer] is used only for the handful of city
/// labels, which must be tappable widgets.
class StationMapLayer extends ConsumerWidget {
  const StationMapLayer({super.key, this.onStationTap, this.onCityTap});

  /// Called when an individual station dot is tapped.
  final void Function(MapStation station)? onStationTap;

  /// Called when a city label is tapped.
  final void Function(CityGroup city)? onCityTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final payload = ref.watch(stationsProvider).asData?.value;
    final filter = ref.watch(modeFilterProvider);
    final selectedCity = ref.watch(selectedCityProvider);
    if (payload == null) return const SizedBox.shrink();

    final all = [
      for (final station in payload.stations) MapStation.fromStation(station),
    ];

    // Filter by mode, and by city once the user picks one.
    var visible = [
      for (final station in all)
        if (filter.contains(station.mode)) station,
    ];
    if (selectedCity != null) {
      visible = [
        for (final station in visible)
          if (station.city == selectedCity) station,
      ];
    }

    if (visible.isEmpty) return const SizedBox.shrink();

    final cities = CityGroups.fromStations(visible);

    return Stack(
      fit: StackFit.expand,
      children: [
        // Individual station dots — one circle per stop, no aggregation.
        CircleLayer(
          circles: [
            for (final station in visible)
              CircleMarker(
                point: station.point,
                radius: _dotRadius(ref.watch(mapZoomProvider)),
                color: station.color.withValues(alpha: 0.85),
                borderColor: Colors.white.withValues(alpha: 0.75),
                borderStrokeWidth: 0.8,
              ),
          ],
        ),
        // City labels, tappable.
        MarkerLayer(
          markers: [
            for (final city in cities)
              if (city.count > 0)
                Marker(
                  point: city.center,
                  width: 132,
                  height: 30,
                  alignment: Alignment.center,
                  child: _CityLabel(
                    city: city,
                    isSelected: city.name == selectedCity,
                    onTap: onCityTap == null ? null : () => onCityTap!(city),
                  ),
                ),
          ],
        ),
        // Tap catcher for the dots themselves, only when asked for.
        if (onStationTap != null)
          _StationTapCatcher(stations: visible, onStationTap: onStationTap!),
      ],
    );
  }

  /// Dots shrink when zoomed out so dense areas stay readable.
  static double _dotRadius(double zoom) {
    if (zoom >= 13) return 5;
    if (zoom >= 11) return 4;
    if (zoom >= 9) return 3;
    return 2.5;
  }
}

/// Resolves a tap to the nearest station within a touch radius.
///
/// `CircleLayer` has no tap dispatch, and wiring its hit notifier would require
/// exposing a layer key upward. A single translucent detector with
/// nearest-neighbour resolution is simpler and stays cheap because it only
/// iterates the already-filtered visible set.
class _StationTapCatcher extends StatelessWidget {
  const _StationTapCatcher({required this.stations, required this.onStationTap});

  final List<MapStation> stations;
  final void Function(MapStation station) onStationTap;

  static const double _radius = 22;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => GestureDetector(
        behavior: HitTestBehavior.translucent,
        onTapUp: (details) =>
            _resolve(context, details.localPosition),
        child: const SizedBox.expand(),
      ),
    );
  }

  void _resolve(BuildContext context, Offset local) {
    final camera = MapCamera.maybeOf(context);
    if (camera == null) return;

    MapStation? nearest;
    var nearestSq = double.infinity;
    for (final station in stations) {
      final screen = camera.latLngToScreenOffset(station.point);
      final dx = screen.dx - local.dx;
      final dy = screen.dy - local.dy;
      final sq = dx * dx + dy * dy;
      if (sq < nearestSq && sq <= _radius * _radius) {
        nearestSq = sq;
        nearest = station;
      }
    }

    final station = nearest;
    if (station != null) onStationTap(station);
  }
}

/// A tappable city label showing the name and its stop count.
class _CityLabel extends StatelessWidget {
  const _CityLabel({
    required this.city,
    required this.isSelected,
    required this.onTap,
  });

  final CityGroup city;
  final bool isSelected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // The dominant mode tints the label so the city reads as bus- or
    // rail-heavy at a glance.
    final dominant = city.countsByMode.entries.isEmpty
        ? TransportMode.unknown
        : (city.countsByMode.entries.toList()
              ..sort((a, b) => b.value.compareTo(a.value)))
            .first
            .key;
    final tint = AppTheme.modeColor(dominant);

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: isSelected
              ? tint
              : scheme.surface.withValues(alpha: 0.88),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isSelected ? Colors.white : tint.withValues(alpha: 0.7),
            width: isSelected ? 2 : 1,
          ),
          boxShadow: const [
            BoxShadow(color: Colors.black26, blurRadius: 4),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: Text(
                city.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: isSelected ? Colors.white : scheme.onSurface,
                ),
              ),
            ),
            const SizedBox(width: 5),
            Text(
              '${city.count}',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: isSelected
                    ? Colors.white
                    : scheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Filter chips for the transport categories.
///
/// Rendered as a single pill above the map controls so the user can see what
/// is currently displayed without opening the legend.
class ModeFilterBar extends ConsumerWidget {
  const ModeFilterBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(modeFilterProvider);
    final scheme = Theme.of(context).colorScheme;

    return Material(
      elevation: 2,
      borderRadius: BorderRadius.circular(22),
      color: scheme.surface,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final mode in TransportMode.all)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: FilterChip(
                  label: Text(mode.tr()),
                  selected: filter.contains(mode),
                  showCheckmark: false,
                  visualDensity: VisualDensity.compact,
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  avatar: CircleAvatar(
                    radius: 5,
                    backgroundColor: AppTheme.modeColor(mode),
                  ),
                  labelStyle: TextStyle(
                    fontSize: 11,
                    color: filter.contains(mode)
                        ? scheme.onSurface
                        : scheme.onSurfaceVariant,
                  ),
                  onSelected: (_) =>
                      ref.read(modeFilterProvider.notifier).toggle(mode),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Legend / filter entry point shown above the map controls.
class StationLegend extends ConsumerWidget {
  const StationLegend({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(modeFilterProvider);
    final payload = ref.watch(stationsProvider).asData?.value;

    if (payload == null) return const SizedBox.shrink();

    final counts = <TransportMode, int>{};
    for (final station in payload.stations) {
      final mode = station.transportMode;
      counts[mode] = (counts[mode] ?? 0) + 1;
    }

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'filter'.tr(),
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                TextButton(
                  onPressed: () => ref.read(modeFilterProvider.notifier).showAll(),
                  child: Text('show_all'.tr()),
                ),
              ],
            ),
            const SizedBox(height: 4),
            for (final mode in TransportMode.all)
              _LegendRow(
                mode: mode,
                count: counts[mode] ?? 0,
                enabled: filter.contains(mode),
                onToggle: () =>
                    ref.read(modeFilterProvider.notifier).toggle(mode),
              ),
          ],
        ),
      ),
    );
  }
}

class _LegendRow extends StatelessWidget {
  const _LegendRow({
    required this.mode,
    required this.count,
    required this.enabled,
    required this.onToggle,
  });

  final TransportMode mode;
  final int count;
  final bool enabled;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      onTap: onToggle,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 11,
              height: 11,
              decoration: BoxDecoration(
                color: enabled
                    ? AppTheme.modeColor(mode)
                    : AppTheme.modeColor(mode).withValues(alpha: 0.3),
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 1),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              mode.tr(),
              style: theme.textTheme.labelSmall?.copyWith(
                color: enabled
                    ? theme.colorScheme.onSurface
                    : theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 6),
            Text(
              '$count',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}