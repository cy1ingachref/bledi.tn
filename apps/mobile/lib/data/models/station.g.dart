// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'station.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_Station _$StationFromJson(Map<String, dynamic> json) => _Station(
  id: json['id'] as String,
  name: json['name'] as String,
  lat: (json['lat'] as num).toDouble(),
  lon: (json['lon'] as num).toDouble(),
  mode: json['mode'] as String?,
  modes:
      (json['modes'] as List<dynamic>?)?.map((e) => e as String).toList() ??
      const <String>[],
  city: json['city'] as String?,
  operator: json['operator'] as String?,
  source: json['source'] as String?,
  nameEn: json['nameEn'] as String?,
  lines:
      (json['lines'] as List<dynamic>?)
          ?.map((e) => StationLineRef.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <StationLineRef>[],
);

Map<String, dynamic> _$StationToJson(_Station instance) => <String, dynamic>{
  'id': instance.id,
  'name': instance.name,
  'lat': instance.lat,
  'lon': instance.lon,
  'mode': instance.mode,
  'modes': instance.modes,
  'city': instance.city,
  'operator': instance.operator,
  'source': instance.source,
  'nameEn': instance.nameEn,
  'lines': instance.lines,
};

_StationLineRef _$StationLineRefFromJson(Map<String, dynamic> json) =>
    _StationLineRef(
      routeShortName: json['route_short_name'] as String?,
      routeColor: json['route_color'] as String?,
      direction: json['direction'] as String?,
      routeId: json['route_id'] as String?,
    );

Map<String, dynamic> _$StationLineRefToJson(_StationLineRef instance) =>
    <String, dynamic>{
      'route_short_name': instance.routeShortName,
      'route_color': instance.routeColor,
      'direction': instance.direction,
      'route_id': instance.routeId,
    };
