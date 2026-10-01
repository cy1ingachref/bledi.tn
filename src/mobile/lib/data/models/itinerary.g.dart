// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'itinerary.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_RouteStep _$RouteStepFromJson(Map<String, dynamic> json) => _RouteStep(
  type: json['type'] as String,
  start: latLngFromJsonList(json['start'] as List?),
  end: latLngFromJsonList(json['end'] as List?),
  color: json['color'] as String?,
  stopName: json['stop_name'] as String?,
  durationMin: (json['duration_min'] as num?)?.toDouble() ?? 0.0,
  mode: json['mode'] as String?,
  line: json['line'] as String?,
  fromName: json['from_name'] as String?,
  toName: json['to_name'] as String?,
);

Map<String, dynamic> _$RouteStepToJson(_RouteStep instance) =>
    <String, dynamic>{
      'type': instance.type,
      'start': latLngToJsonList(instance.start),
      'end': latLngToJsonList(instance.end),
      'color': instance.color,
      'stop_name': instance.stopName,
      'duration_min': instance.durationMin,
      'mode': instance.mode,
      'line': instance.line,
      'from_name': instance.fromName,
      'to_name': instance.toName,
    };

_Itinerary _$ItineraryFromJson(Map<String, dynamic> json) => _Itinerary(
  duration: (json['duration'] as num).toDouble(),
  durationMin: (json['duration_min'] as num).toDouble(),
  transfers: (json['transfers'] as num?)?.toInt() ?? 0,
  hasWalkTransfer: json['has_walk_transfer'] as bool? ?? false,
  steps:
      (json['steps'] as List<dynamic>?)
          ?.map((e) => RouteStep.fromJson(e as Map<String, dynamic>))
          .toList() ??
      const <RouteStep>[],
  fareDinars: (json['fare_dinars'] as num?)?.toDouble(),
);

Map<String, dynamic> _$ItineraryToJson(_Itinerary instance) =>
    <String, dynamic>{
      'duration': instance.duration,
      'duration_min': instance.durationMin,
      'transfers': instance.transfers,
      'has_walk_transfer': instance.hasWalkTransfer,
      'steps': instance.steps,
      'fare_dinars': instance.fareDinars,
    };

_RouteResponse _$RouteResponseFromJson(Map<String, dynamic> json) =>
    _RouteResponse(
      bestFastest: json['best_fastest'] == null
          ? null
          : Itinerary.fromJson(json['best_fastest'] as Map<String, dynamic>),
      bestLessWalk: json['best_less_walk'] == null
          ? null
          : Itinerary.fromJson(json['best_less_walk'] as Map<String, dynamic>),
      alternatives:
          (json['alternatives'] as List<dynamic>?)
              ?.map((e) => Itinerary.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const <Itinerary>[],
      source: json['source'] as String?,
      error: json['error'] as String?,
    );

Map<String, dynamic> _$RouteResponseToJson(_RouteResponse instance) =>
    <String, dynamic>{
      'best_fastest': instance.bestFastest,
      'best_less_walk': instance.bestLessWalk,
      'alternatives': instance.alternatives,
      'source': instance.source,
      'error': instance.error,
    };
