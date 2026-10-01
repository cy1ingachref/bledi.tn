// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'line.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_Line _$LineFromJson(Map<String, dynamic> json) => _Line(
  id: json['id'] as String,
  number: json['number'] as String?,
  shortName: json['short_name'] as String?,
  longName: json['long_name'] as String?,
  mode: json['mode'] as String? ?? 'bus',
  color: json['color'] as String?,
  routeId: json['route_id'] as String?,
  stopsCount: (json['stops_count'] as num?)?.toInt() ?? 0,
);

Map<String, dynamic> _$LineToJson(_Line instance) => <String, dynamic>{
  'id': instance.id,
  'number': instance.number,
  'short_name': instance.shortName,
  'long_name': instance.longName,
  'mode': instance.mode,
  'color': instance.color,
  'route_id': instance.routeId,
  'stops_count': instance.stopsCount,
};

_LinesResponse _$LinesResponseFromJson(Map<String, dynamic> json) =>
    _LinesResponse(
      lines:
          (json['lines'] as List<dynamic>?)
              ?.map((e) => Line.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <Line>[],
      count: (json['count'] as num?)?.toInt() ?? 0,
    );

Map<String, dynamic> _$LinesResponseToJson(_LinesResponse instance) =>
    <String, dynamic>{'lines': instance.lines, 'count': instance.count};
