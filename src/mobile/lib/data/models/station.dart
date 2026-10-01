import 'package:freezed_annotation/freezed_annotation.dart';

part 'station.freezed.dart';
part 'station.g.dart';

/// A transport stop served by the seed dataset.
///
/// Parsed from a GeoJSON Feature in `GET /api/v1/stations`; see
/// `StationsDataSource` for the `[lon, lat]` → lat/lon conversion.
///
/// The `mode` / `city` / `operator` fields come from the backend's enriched
/// station response (added for the mode-coloured map). They are optional so the
/// app still parses an older backend that sends only `{id, name, lines}` —
/// `TransportMode.fromName` then falls back to inferring from the line ids.
@freezed
abstract class Station with _$Station {
  const Station._();

  const factory Station({
    required String id,
    required String name,
    required double lat,
    required double lon,

    /// Seed mode: `bus` | `train` | `metro` | `rail` | `unknown`, or a
    /// `louage*` / `taxi` value for the secondary-seed stops.
    String? mode,

    /// Every mode a multi-modal stop (e.g. a louage hub) belongs to.
    @JsonKey(name: 'modes') @Default(<String>[]) List<String> modes,

    /// Governorate, derived by the backend from the nearest seat.
    String? city,

    String? operator,
    String? source,
    String? nameEn,
    @Default(<StationLineRef>[]) List<StationLineRef> lines,
  }) = _Station;

  factory Station.fromJson(Map<String, dynamic> json) =>
      _$StationFromJson(json);

  /// Resolved transport category, used for colour and filtering.
  ///
  /// Prefers the backend's `mode`; when absent (older backend) it infers from
  /// the line reference names, which the seed encodes as `bus_<n>_<id>`,
  /// `train_<n>_sncft`, `metro_*`, `rail_*`.
  TransportMode get transportMode {
    final declared = TransportMode.fromName(mode);
    if (declared != TransportMode.unknown) return declared;

    for (final line in modes) {
      final parsed = TransportMode.fromName(line);
      if (parsed != TransportMode.unknown) return parsed;
    }
    for (final line in lines) {
      final parsed = TransportMode.fromName(line.shortName ?? line.label);
      if (parsed != TransportMode.unknown) return parsed;
    }
    return TransportMode.unknown;
  }

  /// True when the backend supplied a real mode (as opposed to the fallback).
  bool get hasDeclaredMode {
    final declared = TransportMode.fromName(mode);
    if (declared != TransportMode.unknown) return true;
    return modes.any((m) => TransportMode.fromName(m) != TransportMode.unknown);
  }

  /// Direction / destination labels for the lines serving this stop.
  List<String> get lineLabels => <String>{
    for (final line in lines)
      if ((line.label ?? '').trim().isNotEmpty) line.label!.trim(),
  }.toList(growable: false);
}

/// A line reference attached to a station in the GeoJSON properties.
@freezed
abstract class StationLineRef with _$StationLineRef {
  const StationLineRef._();

  const factory StationLineRef({
    @JsonKey(name: 'route_short_name') String? routeShortName,
    @JsonKey(name: 'route_color') String? routeColor,
    String? direction,
    @JsonKey(name: 'route_id') String? routeId,
  }) = _StationLineRef;

  factory StationLineRef.fromJson(Map<String, dynamic> json) =>
      _$StationLineRefFromJson(json);

  /// `""` and `null` both become `null`, so a missing short name never renders
  /// as the literal text "null" or an empty chip.
  String? get shortName {
    final value = routeShortName;
    if (value == null || value.isEmpty) return null;
    return value;
  }

  /// Direction label (e.g. "Sousse Sud"), a human-readable fallback.
  String? get label {
    final value = direction?.trim();
    if (value == null || value.isEmpty) return null;
    return value;
  }

  /// A stable identity for this line, preferring the route id.
  String get key => (routeId ?? shortName ?? label ?? '').trim();
}

/// The transport categories the map colours and filters by.
///
/// These are the colours the product asked for:
///  * rail/metro → green
///  * bus → red
///  * taxi/louage → yellow
///  * unknown → grey (shown only when the user enables it)
enum TransportMode {
  /// train, metro, rail (RFR)
  rail,

  /// bus
  bus,

  /// taxi, louage, louage_red/blue/green
  louage,

  /// mode absent or unrecognised
  unknown;

  /// Maps a backend mode string onto a category.
  ///
  /// Unknown input deliberately becomes [TransportMode.unknown] rather than
  /// throwing, so a seed with a new mode degrades to grey instead of breaking
  /// the map.
  static TransportMode fromName(String? name) {
    if (name == null) return TransportMode.unknown;
    final value = name.trim().toLowerCase();
    if (value.isEmpty) return TransportMode.unknown;

    // Louage variants first: "louage_red" must not match a bare "rail" test.
    if (value == 'taxi' ||
        value.startsWith('louage') ||
        value == 'grand_taxi') {
      return TransportMode.louage;
    }
    if (value == 'bus' || value == 'autobus' || value == 'bibus') {
      return TransportMode.bus;
    }
    if (value == 'train' ||
        value == 'metro' ||
        value == 'rail' ||
        value == 'rfr' ||
        value == 'tramway' ||
        value == 'light_rail') {
      return TransportMode.rail;
    }

    // Line ids from the seed: bus_705_12, train_1_sncft, metro_56_tgm, rail_19_a.
    if (value.startsWith('bus_')) return TransportMode.bus;
    if (value.startsWith('train_')) return TransportMode.rail;
    if (value.startsWith('metro_')) return TransportMode.rail;
    if (value.startsWith('rail_')) return TransportMode.rail;

    return TransportMode.unknown;
  }

  /// All categories, in the order the filter UI lists them.
  ///
  /// Cannot be named `values`: that is reserved for the implicit enum static.
  static const List<TransportMode> all = [
    TransportMode.rail,
    TransportMode.bus,
    TransportMode.louage,
    TransportMode.unknown,
  ];
}