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

  factory Health.fromJson(Map<String, dynamic> json) => _$HealthFromJson(json);

  bool get isHealthy => status == 'ok';
}
