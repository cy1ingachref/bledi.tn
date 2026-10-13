import 'package:flutter/foundation.dart';

/// A map point selected by the user (origin, destination, or a long-press).
@immutable
class MapPoint {
  const MapPoint({
    required this.lat,
    required this.lon,
    this.label,
    this.stationId,
  });

  final double lat;
  final double lon;

  /// Station name when the point snapped to a station, else a coordinate label.
  final String? label;
  final String? stationId;

  bool get isNamed => label != null && label!.trim().isNotEmpty;

  String get displayLabel {
    if (isNamed) return label!.trim();
    return '${lat.toStringAsFixed(5)}, ${lon.toStringAsFixed(5)}';
  }

  MapPoint copyWith({String? label, String? stationId}) => MapPoint(
    lat: lat,
    lon: lon,
    label: label ?? this.label,
    stationId: stationId ?? this.stationId,
  );

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is MapPoint &&
          other.lat == lat &&
          other.lon == lon &&
          other.label == label &&
          other.stationId == stationId;

  @override
  int get hashCode => Object.hash(lat, lon, label, stationId);
}