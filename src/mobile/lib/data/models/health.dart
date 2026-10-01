import 'package:freezed_annotation/freezed_annotation.dart';

part 'health.freezed.dart';
part 'health.g.dart';

/// `GET /api/v1/health` — used by Settings to show backend connectivity.
///
/// The FastAPI backend serialises snake_case, so every field carries an
/// explicit `@JsonKey` — without it json_serializable would look for
/// `seedFile` and silently drop `seed_file`.
@freezed
abstract class Health with _$Health {
  const Health._();

  const factory Health({
    @Default('ok') String status,
    String? version,
    String? service,
    @JsonKey(name: 'seed_file') String? seedFile,
    @JsonKey(name: 'stations_count') @Default(0) int stationsCount,
    @JsonKey(name: 'lines_count') @Default(0) int linesCount,
  }) = _Health;

  factory Health.fromJson(Map<String, dynamic> json) =>
      _$HealthFromJson(json);

  bool get isHealthy => status == 'ok';
}

/// A nearby station from `GET /api/v1/stations/near`.
@freezed
abstract class NearbyStation with _$NearbyStation {
  const factory NearbyStation({
    required String id,
    required String name,
    required double lat,
    required double lon,
    @JsonKey(name: 'dist_m') @Default(0) double distM,
    @Default(<NearbyStationLine>[]) List<NearbyStationLine> lines,
  }) = _NearbyStation;

  factory NearbyStation.fromJson(Map<String, dynamic> json) =>
      _$NearbyStationFromJson(json);
}

/// The `lines` entries in the `/stations/near` payload are loosely typed
/// upstream, so the loose shape is modelled here rather than reusing
/// [StationLineRef].
@freezed
abstract class NearbyStationLine with _$NearbyStationLine {
  const factory NearbyStationLine({
    @JsonKey(name: 'route_short_name') String? routeShortName,
    @JsonKey(name: 'route_color') String? routeColor,
    String? direction,
  }) = _NearbyStationLine;

  factory NearbyStationLine.fromJson(Map<String, dynamic> json) =>
      _$NearbyStationLineFromJson(json);
}