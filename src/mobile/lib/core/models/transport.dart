import 'package:freezed_annotation/freezed_annotation.dart';

part 'station.freezed.dart';
part 'station.g.dart';

@freezed
class Station with _$Station {
  const factory Station({
    required String id,
    @JsonKey(name: 'name_ar') required String nameAr,
    @JsonKey(name: 'name_fr') String? nameFr,
    @JsonKey(name: 'name_en') String? nameEn,
    double? lat,
    double? lon,
    @JsonKey(name: 'governorate') String? governorate,
    @JsonKey(name: 'station_type') String? stationType,
    String? description,
    @JsonKey(name: 'is_active') bool? isActive,
    @JsonKey(name: 'created_at') DateTime? createdAt,
  }) = _Station;

  factory Station.fromJson(Map<String, dynamic> json) => _$StationFromJson(json);
}

@freezed
class Line with _$Line {
  const factory Line({
    required String id,
    @JsonKey(name: 'line_number') String? lineNumber,
    @JsonKey(name: 'line_name') String? lineName,
    String? operator,
    required String mode,
    String? description,
    String? frequency,
    @JsonKey(name: 'schedule_type') String? scheduleType,
    List<LineStation>? stations,
    Map<String, List<String>>? departures,
  }) = _Line;

  factory Line.fromJson(Map<String, dynamic> json) => _$LineFromJson(json);
}

@freezed
class LineStation with _$LineStation {
  const factory LineStation({
    required String stationId,
    required String nameAr,
    String? nameFr,
    String? nameEn,
    required int order,
    @JsonKey(name: 'is_origin') bool? isOrigin,
    @JsonKey(name: 'is_destination') bool? isDestination,
    double? distanceKm,
  }) = _LineStation;

  factory LineStation.fromJson(Map<String, dynamic> json) => _$LineStationFromJson(json);
}

@freezed
class Fare with _$Fare {
  const factory Fare({
    required String from,
    required String to,
    required int fareDt,
    String? fareDisplay,
    String? mode,
    String? frequency,
  }) = _Fare;

  factory Fare.fromJson(Map<String, dynamic> json) => _$FareFromJson(json);
}

@freezed
class RouteOption with _$RouteOption {
  const factory RouteOption({
    required String id,
    required String mode,
    required String modeAr,
    required String lineName,
    String? lineNumber,
    required String originStation,
    required String destinationStation,
    required String originAr,
    required String destinationAr,
    @JsonKey(name: 'walk_distance_m') int? walkDistanceM,
    @JsonKey(name: 'walk_duration_min') int? walkDurationMin,
    @JsonKey(name: 'ride_duration_min') int? rideDurationMin,
    @JsonKey(name: 'fare_dt') int? fareDt,
    List<StopInfo>? stops,
    List<String>? departures,
    String? frequency,
  }) = _RouteOption;

  factory RouteOption.fromJson(Map<String, dynamic> json) => _$RouteOptionFromJson(json);
}

@freezed
class StopInfo with _$StopInfo {
  const StopInfo._();
  
  const factory StopInfo({
    required String nameAr,
    String? nameFr,
    String? nameEn,
    required int order,
    bool? isGetOff,
  }) = _StopInfo;

  factory StopInfo.fromJson(Map<String, dynamic> json) => _$StopInfoFromJson(json);
}
