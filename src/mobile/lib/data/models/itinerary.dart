import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:latlong2/latlong.dart';

part 'itinerary.freezed.dart';
part 'itinerary.g.dart';

/// Great-circle distance helper. latlong2 exposes this as a `Distance`
/// callable rather than as a method on `LatLng`.
const Distance _distance = Distance();

/// Decodes a backend `[lat, lon]` pair into a [LatLng].
///
/// The backend deliberately emits `[lat, lon]` (not GeoJSON's `[lon, lat]`)
/// in every transit step, which is the opposite of the GeoJSON convention used
/// by `/api/v1/stations`. Getting this backwards silently places routes in the
/// Indian Ocean, so it is centralised here rather than at each call site.
///
/// These are plain top-level functions rather than a [JsonConverter] class
/// because `json_serializable` only honours per-field [JsonKey] converters —
/// an annotation on a constructor parameter is silently ignored, producing
/// `LatLng.fromJson(...)` and a runtime cast error.
LatLng latLngFromJsonList(List<dynamic>? json) {
  if (json == null || json.length < 2) {
    throw const FormatException('Expected a [lat, lon] pair');
  }
  final lat = (json[0] as num?)?.toDouble();
  final lon = (json[1] as num?)?.toDouble();
  if (lat == null || lon == null || lat.isNaN || lon.isNaN) {
    throw FormatException('Invalid [lat, lon] pair: $json');
  }
  return LatLng(lat, lon);
}

/// Inverse of [latLngFromJsonList].
List<double>? latLngToJsonList(LatLng? object) => object == null
    ? null
    : <double>[object.latitude, object.longitude];

/// A single leg of a transit itinerary.
///
/// Matches `TransitStep` in `src/backend/app/main.py`. Note the backend sends
/// `duration_min` in the pydantic model but does not populate it in the
/// `/route/transit` payload, so the app falls back to [Itinerary] totals and
/// [estimatedDurationMin].
@freezed
abstract class RouteStep with _$RouteStep {
  const RouteStep._();

  const factory RouteStep({
    /// `walk` | `ride` | `transfer` | `taxi`
    required String type,
    @JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList)
    required LatLng start,
    @JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList)
    required LatLng end,
    String? color,
    @JsonKey(name: 'stop_name') String? stopName,
    @JsonKey(name: 'duration_min') @Default(0.0) double durationMin,
    String? mode,
    String? line,
    @JsonKey(name: 'from_name') String? fromName,
    @JsonKey(name: 'to_name') String? toName,
  }) = _RouteStep;

  factory RouteStep.fromJson(Map<String, dynamic> json) =>
      _$RouteStepFromJson(json);

  /// True for a `ride` step — the only kind that uses a line number.
  bool get isRide => type == 'ride';

  bool get isWalk => type == 'walk';
  bool get isTaxi => type == 'taxi';
  bool get isTransfer => type == 'transfer';

  /// Best available label for where this step ends.
  String get endLabel {
    if (toName != null && toName!.trim().isNotEmpty) return toName!.trim();
    if (stopName != null && stopName!.trim().isNotEmpty) return stopName!.trim();
    return '';
  }

  /// Label for where this step starts, falling back to [endLabel].
  String get startLabel {
    if (fromName != null && fromName!.trim().isNotEmpty) {
      return fromName!.trim();
    }
    return endLabel;
  }

  /// Colour for this step: the backend value wins, else a per-mode fallback.
  ///
  /// The seed/backend emit `#RRGGBB`; malformed values fall back to the
  /// theme's mode colour rather than throwing.
  String? get hexColor {
    final value = color?.trim();
    if (value == null || value.isEmpty) return null;
    final withHash = value.startsWith('#') ? value : '#$value';
    return RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(withHash) ? withHash : null;
  }

  /// Typical cruising speed per step kind, in km/h, used only when the backend
  /// sends no per-step duration. The backend populates `duration_min` only on
  /// the itinerary, not per step, so these estimates fill the gap.
  ///
  /// Taxi matters here: treating a taxi leg as walking turned a real 19-minute
  /// ride into a nonsense "3 h 06".
  double get _assumedSpeedKmh {
    if (isWalk) return 4.5;
    if (isTaxi) return 45.0;
    if (isRide) {
      return switch (mode) {
        'metro' => 32.0,
        'train' || 'rfr' => 70.0,
        _ => 18.0, // bus, including urban stop-and-go
      };
    }
    return 18.0;
  }

  /// Duration of this step in minutes.
  ///
  /// Prefers the backend value; otherwise estimates from straight-line
  /// distance. The estimate is approximate — real road geometry lives on the
  /// backend — so it is only used to give each step a plausible magnitude.
  double estimatedDurationMin({double walkSpeedKmh = 4.5}) {
    if (durationMin > 0) return durationMin;
    final km = distanceMeters / 1000.0;
    if (km <= 0) return 0;
    final speed = isWalk ? walkSpeedKmh : _assumedSpeedKmh;
    return (km / speed) * 60.0;
  }

  /// Straight-line distance of this step in metres. Used only for the
  /// step-list summary — the real route geometry is on the backend.
  double get distanceMeters => _distance(start, end);
}

/// A complete itinerary option (`TransitOption` on the backend).
@freezed
abstract class Itinerary with _$Itinerary {
  const Itinerary._();

  const factory Itinerary({
    /// Total duration in **seconds** (backend field `duration`).
    required double duration,
    @JsonKey(name: 'duration_min') required double durationMin,
    @Default(0) int transfers,
    @JsonKey(name: 'has_walk_transfer') @Default(false) bool hasWalkTransfer,
    @Default(<RouteStep>[]) List<RouteStep> steps,
    @JsonKey(name: 'fare_dinars') double? fareDinars,
  }) = _Itinerary;

  factory Itinerary.fromJson(Map<String, dynamic> json) =>
      _$ItineraryFromJson(json);

  /// Number of non-ride steps (access walk + egress walk), used as a sanity
  /// check that the step list is complete.
  int get walkLegs => steps.where((s) => s.isWalk).length;

  /// Distinct lines used, in order of first appearance.
  List<String> get lineLabels {
    final seen = <String>{};
    final out = <String>[];
    for (final step in steps) {
      final line = step.line;
      if (step.isRide && line != null && line.isNotEmpty && seen.add(line)) {
        out.add(line);
      }
    }
    return out;
  }

  /// Union of every step's start/end, for fitting the map camera.
  List<LatLng> get allPoints => [
    for (final step in steps) ...[step.start, step.end],
  ];

  bool get hasFare => fareDinars != null && fareDinars! > 0;
}

/// The `/api/v1/route/transit` envelope.
///
/// On failure the backend returns a bare `{"error": "...", "source": "..."}`
/// with HTTP 200, so [error] is the field the UI must branch on — a 200 alone
/// does not mean a route was found.
@freezed
abstract class RouteResponse with _$RouteResponse {
  const RouteResponse._();

  const factory RouteResponse({
    @JsonKey(name: 'best_fastest') Itinerary? bestFastest,
    @JsonKey(name: 'best_less_walk') Itinerary? bestLessWalk,
    @Default(<Itinerary>[]) List<Itinerary> alternatives,
    String? source,
    String? error,
  }) = _RouteResponse;

  factory RouteResponse.fromJson(Map<String, dynamic> json) =>
      _$RouteResponseFromJson(json);

  bool get hasError => error != null && error!.isNotEmpty;

  /// Best available option: fastest, else less-walk, else first alternative.
  /// `null` when the response carried neither an error nor an option.
  Itinerary? get primary {
    if (bestFastest != null) return bestFastest;
    if (bestLessWalk != null) return bestLessWalk;
    return alternatives.isNotEmpty ? alternatives.first : null;
  }

  /// Every usable option, fastest first.
  List<Itinerary> get options => <Itinerary>[
    ?bestFastest,
    ?bestLessWalk,
    ...alternatives,
  ];
}