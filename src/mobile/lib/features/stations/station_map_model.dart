import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

import '../../core/theme.dart';
import '../../data/models/station.dart';

/// A station reduced to what the map layer needs: position, identity, and the
/// resolved transport category that drives its colour.
@immutable
class MapStation {
  const MapStation({
    required this.id,
    required this.name,
    required this.lat,
    required this.lon,
    required this.mode,
    this.city,
    this.lineLabels = const <String>[],
  });

  factory MapStation.fromStation(Station station) => MapStation(
    id: station.id,
    name: station.name,
    lat: station.lat,
    lon: station.lon,
    mode: station.transportMode,
    city: station.city,
    lineLabels: station.lineLabels,
  );

  final String id;
  final String name;
  final double lat;
  final double lon;

  /// Resolved from the backend's `mode`, falling back to the line ids.
  final TransportMode mode;

  final String? city;
  final List<String> lineLabels;

  bool get isNamed => name.trim().isNotEmpty;

  LatLng get point => LatLng(lat, lon);

  Color get color => AppTheme.modeColor(mode);
}

/// A city grouping of stations, shown as a pickable region label on the map.
///
/// Replaces the previous density clustering. Density clustering chained the
/// whole country into one 1 561-station blob, which told the user nothing;
/// cities are meaningful places they can choose and zoom into.
@immutable
class CityGroup {
  const CityGroup({
    required this.name,
    required this.center,
    required this.stations,
  });

  const CityGroup._({
    required this.name,
    required this.center,
    required this.stations,
  });

  final String name;

  /// Mean position of the city's stops — where the map zooms when picked.
  final LatLng center;

  final List<MapStation> stations;

  int get count => stations.length;

  /// Stations per transport category, for the city's summary row.
  Map<TransportMode, int> get countsByMode {
    final out = <TransportMode, int>{};
    for (final station in stations) {
      out[station.mode] = (out[station.mode] ?? 0) + 1;
    }
    return out;
  }

  int countOf(TransportMode mode) => countsByMode[mode] ?? 0;

  /// True for the synthetic group of stations with no city.
  bool get isOther => name == CityGroups.otherLabel;
}

/// City grouping helpers.
///
/// A Dart `factory` cannot return a `List`, so grouping lives here rather than
/// on [CityGroup].
abstract final class CityGroups {
  /// Label used for stations too remote to belong to any governorate.
  static const String otherLabel = 'Other';

  /// Groups stations by city, largest first.
  ///
  /// Stations with no city are grouped under [otherLabel] rather than dropped,
  /// so nothing disappears silently.
  static List<CityGroup> fromStations(List<MapStation> stations) {
    final buckets = <String, List<MapStation>>{};
    for (final station in stations) {
      final city = station.city;
      final key = (city == null || city.isEmpty) ? otherLabel : city;
      buckets.putIfAbsent(key, () => <MapStation>[]).add(station);
    }

    final groups = [
      for (final entry in buckets.entries)
        CityGroup._(
          name: entry.key,
          center: _centroid(entry.value),
          stations: entry.value,
        ),
    ];
    groups.sort((a, b) => b.stations.length.compareTo(a.stations.length));
    return groups;
  }

  static LatLng _centroid(List<MapStation> members) {
    var sumLat = 0.0;
    var sumLon = 0.0;
    for (final m in members) {
      sumLat += m.lat;
      sumLon += m.lon;
    }
    return LatLng(sumLat / members.length, sumLon / members.length);
  }
}
