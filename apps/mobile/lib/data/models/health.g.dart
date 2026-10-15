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
