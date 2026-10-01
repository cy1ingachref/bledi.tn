import 'package:freezed_annotation/freezed_annotation.dart';

import 'station.dart';

part 'city.freezed.dart';
part 'city.g.dart';

/// A city/governorate with its station inventory.
///
/// From `GET /api/v1/cities`. Computed by the backend from the same seed as
/// `/api/v1/stations`, so the counts always agree with the station list.
@freezed
abstract class City with _$City {
  const City._();

  const factory City({
    required String name,
    required double lat,
    required double lon,
    @JsonKey(name: 'station_count') required int stationCount,
    @JsonKey(name: 'by_mode') @Default(<String, int>{}) Map<String, int> byMode,
  }) = _City;

  factory City.fromJson(Map<String, dynamic> json) => _$CityFromJson(json);

  /// Count of stops in each [TransportMode].
  ///
  /// The backend keys by raw seed mode (`bus`, `train`, `metro`, `rail`,
  /// `louage`), which this folds into the four display categories.
  Map<TransportMode, int> get countsByCategory {
    final out = <TransportMode, int>{};
    byMode.forEach((raw, count) {
      final category = TransportMode.fromName(raw);
      out[category] = (out[category] ?? 0) + count;
    });
    return out;
  }

  int countOf(TransportMode mode) => countsByCategory[mode] ?? 0;
}

/// Wrapper for the `/api/v1/cities` envelope.
@freezed
abstract class CitiesResponse with _$CitiesResponse {
  const factory CitiesResponse({
    @Default(<City>[]) List<City> cities,
    @Default(0) int count,
  }) = _CitiesResponse;

  factory CitiesResponse.fromJson(Map<String, dynamic> json) =>
      _$CitiesResponseFromJson(json);
}