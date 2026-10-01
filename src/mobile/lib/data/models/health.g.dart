// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'health.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_Health _$HealthFromJson(Map<String, dynamic> json) => _Health(
  status: json['status'] as String? ?? 'ok',
  version: json['version'] as String?,
  service: json['service'] as String?,
  seedFile: json['seed_file'] as String?,
  stationsCount: (json['stations_count'] as num?)?.toInt() ?? 0,
  linesCount: (json['lines_count'] as num?)?.toInt() ?? 0,
);

Map<String, dynamic> _$HealthToJson(_Health instance) => <String, dynamic>{
  'status': instance.status,
  'version': instance.version,
  'service': instance.service,
  'seed_file': instance.seedFile,
  'stations_count': instance.stationsCount,
  'lines_count': instance.linesCount,
};

_NearbyStation _$NearbyStationFromJson(Map<String, dynamic> json) =>
    _NearbyStation(
      id: json['id'] as String,
      name: json['name'] as String,
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      distM: (json['dist_m'] as num?)?.toDouble() ?? 0,
      lines:
          (json['lines'] as List<dynamic>?)
              ?.map(
                (e) => NearbyStationLine.fromJson(e as Map<String, dynamic>),
              )
              .toList() ??
          const <NearbyStationLine>[],
    );

Map<String, dynamic> _$NearbyStationToJson(_NearbyStation instance) =>
    <String, dynamic>{
      'id': instance.id,
      'name': instance.name,
      'lat': instance.lat,
      'lon': instance.lon,
      'dist_m': instance.distM,
      'lines': instance.lines,
    };

_NearbyStationLine _$NearbyStationLineFromJson(Map<String, dynamic> json) =>
    _NearbyStationLine(
      routeShortName: json['route_short_name'] as String?,
      routeColor: json['route_color'] as String?,
      direction: json['direction'] as String?,
    );

Map<String, dynamic> _$NearbyStationLineToJson(_NearbyStationLine instance) =>
    <String, dynamic>{
      'route_short_name': instance.routeShortName,
      'route_color': instance.routeColor,
      'direction': instance.direction,
    };
