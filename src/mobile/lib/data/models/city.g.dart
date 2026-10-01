// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'city.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_City _$CityFromJson(Map<String, dynamic> json) => _City(
  name: json['name'] as String,
  lat: (json['lat'] as num).toDouble(),
  lon: (json['lon'] as num).toDouble(),
  stationCount: (json['station_count'] as num).toInt(),
  byMode:
      (json['by_mode'] as Map<String, dynamic>?)?.map(
        (k, e) => MapEntry(k, (e as num).toInt()),
      ) ??
      const <String, int>{},
);

Map<String, dynamic> _$CityToJson(_City instance) => <String, dynamic>{
  'name': instance.name,
  'lat': instance.lat,
  'lon': instance.lon,
  'station_count': instance.stationCount,
  'by_mode': instance.byMode,
};

_CitiesResponse _$CitiesResponseFromJson(Map<String, dynamic> json) =>
    _CitiesResponse(
      cities:
          (json['cities'] as List<dynamic>?)
              ?.map((e) => City.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <City>[],
      count: (json['count'] as num?)?.toInt() ?? 0,
    );

Map<String, dynamic> _$CitiesResponseToJson(_CitiesResponse instance) =>
    <String, dynamic>{'cities': instance.cities, 'count': instance.count};
