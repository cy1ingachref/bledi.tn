import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../core/constants.dart';
import '../../core/utils/state.dart';
import '../../providers/providers.dart';
import '../routing/routing_panel.dart';
import '../stations/city_picker_sheet.dart';
import '../stations/station_info_sheet.dart';
import '../stations/station_map_layer.dart';
import '../stations/station_map_model.dart';
import '../stations/station_search_sheet.dart';
import 'widgets/bledi_map.dart';

/// Home screen: map + endpoint selection + routing.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final MapController _mapController = MapController();

  /// Which endpoint a new pin replaces.
  SelectionTarget get _target => ref.read(routeSelectionProvider).target;

  Future<void> _openPicker(SelectionTarget target) async {
    ref.read(routeSelectionProvider.notifier).setTarget(target);
    final picked = await StationSearchSheet.show(context);
    if (picked == null || !mounted) return;

    final notifier = ref.read(routeSelectionProvider.notifier);
    final point = MapPoint(
      lat: picked.lat,
      lon: picked.lon,
      label: picked.name,
      stationId: picked.id,
    );
    if (target == SelectionTarget.origin) {
      notifier.setOrigin(point);
    } else {
      notifier.setDestination(point);
    }
    _mapController.move(LatLng(picked.lat, picked.lon), 15);
  }

  void _onLongPress(LatLng point) {
    final notifier = ref.read(routeSelectionProvider.notifier);
    final mapPoint = MapPoint(lat: point.latitude, lon: point.longitude);
    if (_target == SelectionTarget.origin) {
      notifier.setOrigin(mapPoint);
    } else {
      notifier.setDestination(mapPoint);
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          _target == SelectionTarget.origin
              ? '${'choose_origin'.tr()}: ${mapPoint.displayLabel}'
              : '${'choose_destination'.tr()}: ${mapPoint.displayLabel}',
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Future<void> _searchRoute() async {
    final selection = ref.read(routeSelectionProvider);
    if (!selection.hasBoth) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('origin_destination_required'.tr())),
      );
      return;
    }
    await ref.read(routingProvider.notifier).routeCurrentSelection();
    if (mounted) _showResultSheet();
  }

  void _showResultSheet() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const RoutingPanel(),
    );
  }

  void _onStationTap(MapStation station) {
    StationInfoSheet.show(context, station);
  }

  /// Filters the map to a city and zooms to it.
  void _onCityTap(CityGroup city) {
    final alreadySelected =
        ref.read(selectedCityProvider) == city.name;
    ref.read(selectedCityProvider.notifier).select(
      alreadySelected ? null : city.name,
    );
    _mapController.move(
      city.center,
      alreadySelected ? AppConstants.tunisZoom : 12,
    );
  }

  Future<void> _openCityPicker() async {
    final chosen = await CityPickerSheet.show(context);
    if (!mounted || chosen == null) return;
    final city = ref
        .read(citiesProvider)
        .where((c) => c.name == chosen)
        .firstOrNull;
    if (city != null) {
      _mapController.move(LatLng(city.lat, city.lon), 12);
    }
  }

  Future<void> _centerOnUser() async {
    final notifier = ref.read(userLocationProvider.notifier);
    await notifier.refresh();
    final location = ref.read(userLocationProvider);
    if (!mounted) return;

    if (!location.hasFix) {
      final message = switch (location.error) {
        'permission_denied' => 'location_permission_denied'.tr(),
        'location_disabled' || 'unavailable' => 'location_unavailable'.tr(),
        _ => 'location_unavailable'.tr(),
      };
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
      return;
    }
    _mapController.move(LatLng(location.lat!, location.lon!), 15);
  }

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selection = ref.watch(routeSelectionProvider);
    final result = ref.watch(routingProvider);
    final showStations = ref.watch(stationOverlayProvider);
    final selectedCity = ref.watch(selectedCityProvider);

    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: BlediMap(
              controller: _mapController,
              onLongPress: _onLongPress,
              onStationTap: _onStationTap,
              onCityTap: _onCityTap,
            ),
          ),
          Positioned(
            top: MediaQuery.of(context).padding.top + 8,
            left: 12,
            right: 12,
            child: _EndpointBar(
              origin: selection.origin,
              destination: selection.destination,
              isLoading: result.isLoading,
              onPickOrigin: () => _openPicker(SelectionTarget.origin),
              onPickDestination: () =>
                  _openPicker(SelectionTarget.destination),
              onSwap: () => ref.read(routeSelectionProvider.notifier).swap(),
              onClear: () {
                ref.read(routeSelectionProvider.notifier).clear();
                ref.read(routingProvider.notifier).clear();
              },
              onSearch: _searchRoute,
            ),
          ),
          Positioned(
            right: 12,
            bottom: result.hasItinerary || result.isLoading ? 300 : 24,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                // Filter chips for the transport categories.
                if (showStations) const ModeFilterBar(),
                const SizedBox(height: 10),
                FloatingActionButton.small(
                  heroTag: 'city_picker',
                  tooltip: 'cities'.tr(),
                  onPressed: _openCityPicker,
                  child: const Icon(Icons.location_city),
                ),
                const SizedBox(height: 10),
                FloatingActionButton.small(
                  heroTag: 'station_overlay',
                  tooltip: 'stations'.tr(),
                  onPressed: () => ref
                      .read(stationOverlayProvider.notifier)
                      .toggle(),
                  child: Icon(
                    showStations ? Icons.layers : Icons.layers_outlined,
                  ),
                ),
                const SizedBox(height: 10),
                FloatingActionButton.small(
                  heroTag: 'my_location',
                  tooltip: 'my_location'.tr(),
                  onPressed: _centerOnUser,
                  child: const Icon(Icons.my_location),
                ),
              ],
            ),
          ),
          if (selectedCity != null)
            Positioned(
              left: 12,
              bottom: result.hasItinerary || result.isLoading ? 300 : 24,
              child: _SelectedCityChip(
                name: selectedCity,
                onClear: () {
                  ref.read(selectedCityProvider.notifier).select(null);
                  _mapController.move(
                    LatLng(
                      AppConstants.tunisLat,
                      AppConstants.tunisLon,
                    ),
                    AppConstants.tunisZoom,
                  );
                },
              ),
            ),
          if (result.isLoading)
            const Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: LinearProgressIndicator(minHeight: 2),
            ),
          if (result.hasItinerary)
            Positioned(
              left: 12,
              right: 12,
              bottom: 16,
              child: _RouteSummaryBar(
                onTap: _showResultSheet,
              ),
            ),
        ],
      ),
    );
  }
}

/// Top card with the origin/destination fields and the search button.
class _EndpointBar extends StatelessWidget {
  const _EndpointBar({
    required this.origin,
    required this.destination,
    required this.isLoading,
    required this.onPickOrigin,
    required this.onPickDestination,
    required this.onSwap,
    required this.onClear,
    required this.onSearch,
  });

  final MapPoint? origin;
  final MapPoint? destination;
  final bool isLoading;
  final VoidCallback onPickOrigin;
  final VoidCallback onPickDestination;
  final VoidCallback onSwap;
  final VoidCallback onClear;
  final VoidCallback onSearch;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasBoth = origin != null && destination != null;

    return Material(
      elevation: 3,
      borderRadius: BorderRadius.circular(18),
      color: theme.colorScheme.surface,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    children: [
                      _EndpointField(
                        icon: Icons.trip_origin,
                        iconColor: const Color(0xFF2F9E44),
                        label: 'origin'.tr(),
                        value: origin?.displayLabel,
                        placeholder: 'choose_origin'.tr(),
                        onTap: onPickOrigin,
                      ),
                      const SizedBox(height: 8),
                      _EndpointField(
                        icon: Icons.place,
                        iconColor: const Color(0xFFE03131),
                        label: 'destination'.tr(),
                        value: destination?.displayLabel,
                        placeholder: 'choose_destination'.tr(),
                        onTap: onPickDestination,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Column(
                  children: [
                    IconButton(
                      tooltip: 'swap'.tr(),
                      onPressed: hasBoth ? onSwap : null,
                      icon: const Icon(Icons.swap_vert),
                    ),
                    IconButton(
                      tooltip: 'clear'.tr(),
                      onPressed: hasBoth ? onClear : null,
                      icon: const Icon(Icons.close),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: isLoading ? null : onSearch,
              icon: isLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.route),
              label: Text(isLoading ? 'routing'.tr() : 'search_route'.tr()),
            ),
          ],
        ),
      ),
    );
  }
}

class _EndpointField extends StatelessWidget {
  const _EndpointField({
    required this.icon,
    required this.iconColor,
    required this.label,
    required this.value,
    required this.placeholder,
    required this.onTap,
  });

  final IconData icon;
  final Color iconColor;
  final String label;
  final String? value;
  final String placeholder;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            Icon(icon, size: 18, color: iconColor),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    label,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  Text(
                    value ?? placeholder,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: value == null ? FontWeight.normal : null,
                      color: value == null
                          ? theme.colorScheme.onSurfaceVariant
                          : null,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Collapsed summary bar shown after a successful route search.
class _RouteSummaryBar extends ConsumerWidget {
  const _RouteSummaryBar({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final itinerary = ref.watch(routingProvider).itinerary;
    if (itinerary == null) return const SizedBox.shrink();

    final theme = Theme.of(context);
    return Material(
      elevation: 3,
      borderRadius: BorderRadius.circular(18),
      color: theme.colorScheme.surface,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              const Icon(Icons.directions_bus, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '${'total_duration'.tr()}: ${formatDuration(context, itinerary.durationMin)}'
                      '${itinerary.transfers > 0 ? ' · ${'transfers'.tr()}: ${itinerary.transfers}' : ''}'
                      '${itinerary.hasFare ? ' · ${'fare'.tr()}: ${itinerary.fareDinars!.toStringAsFixed(2)} DT' : ''}',
                      style: theme.textTheme.bodyMedium,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (itinerary.lineLabels.isNotEmpty)
                      Text(
                        itinerary.lineLabels.join(' · '),
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                  ],
                ),
              ),
              const Icon(Icons.expand_less),
            ],
          ),
        ),
      ),
    );
  }
}

/// Chip showing the city the map is currently filtered to, with a clear action.
class _SelectedCityChip extends StatelessWidget {
  const _SelectedCityChip({required this.name, required this.onClear});

  final String name;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 2,
      borderRadius: BorderRadius.circular(20),
      color: Theme.of(context).colorScheme.secondaryContainer,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 6, 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.location_city, size: 16),
            const SizedBox(width: 6),
            Text(
              name,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
            IconButton(
              iconSize: 16,
              visualDensity: VisualDensity.compact,
              onPressed: onClear,
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      ),
    );
  }
}
