// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'itinerary.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$RouteStep {

/// `walk` | `ride` | `transfer` | `taxi`
 String get type;@JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList) LatLng get start;@JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList) LatLng get end; String? get color;@JsonKey(name: 'stop_name') String? get stopName;@JsonKey(name: 'duration_min') double get durationMin; String? get mode; String? get line;@JsonKey(name: 'from_name') String? get fromName;@JsonKey(name: 'to_name') String? get toName;
/// Create a copy of RouteStep
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$RouteStepCopyWith<RouteStep> get copyWith => _$RouteStepCopyWithImpl<RouteStep>(this as RouteStep, _$identity);

  /// Serializes this RouteStep to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as RouteStep;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is RouteStep&&(identical(other.type, _this.type) || other.type == _this.type)&&(identical(other.start, _this.start) || other.start == _this.start)&&(identical(other.end, _this.end) || other.end == _this.end)&&(identical(other.color, _this.color) || other.color == _this.color)&&(identical(other.stopName, _this.stopName) || other.stopName == _this.stopName)&&(identical(other.durationMin, _this.durationMin) || other.durationMin == _this.durationMin)&&(identical(other.mode, _this.mode) || other.mode == _this.mode)&&(identical(other.line, _this.line) || other.line == _this.line)&&(identical(other.fromName, _this.fromName) || other.fromName == _this.fromName)&&(identical(other.toName, _this.toName) || other.toName == _this.toName));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as RouteStep;
  return Object.hash(runtimeType,_this.type,_this.start,_this.end,_this.color,_this.stopName,_this.durationMin,_this.mode,_this.line,_this.fromName,_this.toName);
}

@override
String toString() {
  final _this = this as RouteStep;
  return 'RouteStep(type: ${_this.type}, start: ${_this.start}, end: ${_this.end}, color: ${_this.color}, stopName: ${_this.stopName}, durationMin: ${_this.durationMin}, mode: ${_this.mode}, line: ${_this.line}, fromName: ${_this.fromName}, toName: ${_this.toName})';
}


}

/// @nodoc
abstract mixin class $RouteStepCopyWith<$Res>  {
  factory $RouteStepCopyWith(RouteStep value, $Res Function(RouteStep) _then) = _$RouteStepCopyWithImpl;
@useResult
$Res call({
 String type,@JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList) LatLng start,@JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList) LatLng end, String? color,@JsonKey(name: 'stop_name') String? stopName,@JsonKey(name: 'duration_min') double durationMin, String? mode, String? line,@JsonKey(name: 'from_name') String? fromName,@JsonKey(name: 'to_name') String? toName
});




}
/// @nodoc
class _$RouteStepCopyWithImpl<$Res>
    implements $RouteStepCopyWith<$Res> {
  _$RouteStepCopyWithImpl(this._self, this._then);

  final RouteStep _self;
  final $Res Function(RouteStep) _then;

/// Create a copy of RouteStep
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? type = null,Object? start = null,Object? end = null,Object? color = freezed,Object? stopName = freezed,Object? durationMin = null,Object? mode = freezed,Object? line = freezed,Object? fromName = freezed,Object? toName = freezed,}) {
  return _then(RouteStep(
type: null == type ? _self.type : type // ignore: cast_nullable_to_non_nullable
as String,start: null == start ? _self.start : start // ignore: cast_nullable_to_non_nullable
as LatLng,end: null == end ? _self.end : end // ignore: cast_nullable_to_non_nullable
as LatLng,color: freezed == color ? _self.color : color // ignore: cast_nullable_to_non_nullable
as String?,stopName: freezed == stopName ? _self.stopName : stopName // ignore: cast_nullable_to_non_nullable
as String?,durationMin: null == durationMin ? _self.durationMin : durationMin // ignore: cast_nullable_to_non_nullable
as double,mode: freezed == mode ? _self.mode : mode // ignore: cast_nullable_to_non_nullable
as String?,line: freezed == line ? _self.line : line // ignore: cast_nullable_to_non_nullable
as String?,fromName: freezed == fromName ? _self.fromName : fromName // ignore: cast_nullable_to_non_nullable
as String?,toName: freezed == toName ? _self.toName : toName // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

}


/// Adds pattern-matching-related methods to [RouteStep].
extension RouteStepPatterns on RouteStep {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _RouteStep value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _RouteStep() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _RouteStep value)  $default,){
final _that = this;
switch (_that) {
case _RouteStep():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _RouteStep value)?  $default,){
final _that = this;
switch (_that) {
case _RouteStep() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String type, @JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList)  LatLng start, @JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList)  LatLng end,  String? color, @JsonKey(name: 'stop_name')  String? stopName, @JsonKey(name: 'duration_min')  double durationMin,  String? mode,  String? line, @JsonKey(name: 'from_name')  String? fromName, @JsonKey(name: 'to_name')  String? toName)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _RouteStep() when $default != null:
return $default(_that.type,_that.start,_that.end,_that.color,_that.stopName,_that.durationMin,_that.mode,_that.line,_that.fromName,_that.toName);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String type, @JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList)  LatLng start, @JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList)  LatLng end,  String? color, @JsonKey(name: 'stop_name')  String? stopName, @JsonKey(name: 'duration_min')  double durationMin,  String? mode,  String? line, @JsonKey(name: 'from_name')  String? fromName, @JsonKey(name: 'to_name')  String? toName)  $default,) {final _that = this;
switch (_that) {
case _RouteStep():
return $default(_that.type,_that.start,_that.end,_that.color,_that.stopName,_that.durationMin,_that.mode,_that.line,_that.fromName,_that.toName);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String type, @JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList)  LatLng start, @JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList)  LatLng end,  String? color, @JsonKey(name: 'stop_name')  String? stopName, @JsonKey(name: 'duration_min')  double durationMin,  String? mode,  String? line, @JsonKey(name: 'from_name')  String? fromName, @JsonKey(name: 'to_name')  String? toName)?  $default,) {final _that = this;
switch (_that) {
case _RouteStep() when $default != null:
return $default(_that.type,_that.start,_that.end,_that.color,_that.stopName,_that.durationMin,_that.mode,_that.line,_that.fromName,_that.toName);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _RouteStep extends RouteStep {
  const _RouteStep({required this.type, @JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList) required this.start, @JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList) required this.end, this.color, @JsonKey(name: 'stop_name') this.stopName, @JsonKey(name: 'duration_min') this.durationMin = 0.0, this.mode, this.line, @JsonKey(name: 'from_name') this.fromName, @JsonKey(name: 'to_name') this.toName}): super._();
  factory _RouteStep.fromJson(Map<String, dynamic> json) => _$RouteStepFromJson(json);

/// `walk` | `ride` | `transfer` | `taxi`
@override final  String type;
@override@JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList) final  LatLng start;
@override@JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList) final  LatLng end;
@override final  String? color;
@override@JsonKey(name: 'stop_name') final  String? stopName;
@override@JsonKey(name: 'duration_min') final  double durationMin;
@override final  String? mode;
@override final  String? line;
@override@JsonKey(name: 'from_name') final  String? fromName;
@override@JsonKey(name: 'to_name') final  String? toName;

/// Create a copy of RouteStep
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$RouteStepCopyWith<_RouteStep> get copyWith => __$RouteStepCopyWithImpl<_RouteStep>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$RouteStepToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _RouteStep&&(identical(other.type, type) || other.type == type)&&(identical(other.start, start) || other.start == start)&&(identical(other.end, end) || other.end == end)&&(identical(other.color, color) || other.color == color)&&(identical(other.stopName, stopName) || other.stopName == stopName)&&(identical(other.durationMin, durationMin) || other.durationMin == durationMin)&&(identical(other.mode, mode) || other.mode == mode)&&(identical(other.line, line) || other.line == line)&&(identical(other.fromName, fromName) || other.fromName == fromName)&&(identical(other.toName, toName) || other.toName == toName));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,type,start,end,color,stopName,durationMin,mode,line,fromName,toName);
}

@override
String toString() {
    return 'RouteStep(type: $type, start: $start, end: $end, color: $color, stopName: $stopName, durationMin: $durationMin, mode: $mode, line: $line, fromName: $fromName, toName: $toName)';
}


}

/// @nodoc
abstract mixin class _$RouteStepCopyWith<$Res> implements $RouteStepCopyWith<$Res> {
  factory _$RouteStepCopyWith(_RouteStep value, $Res Function(_RouteStep) _then) = __$RouteStepCopyWithImpl;
@override @useResult
$Res call({
 String type,@JsonKey(name: 'start', fromJson: latLngFromJsonList, toJson: latLngToJsonList) LatLng start,@JsonKey(name: 'end', fromJson: latLngFromJsonList, toJson: latLngToJsonList) LatLng end, String? color,@JsonKey(name: 'stop_name') String? stopName,@JsonKey(name: 'duration_min') double durationMin, String? mode, String? line,@JsonKey(name: 'from_name') String? fromName,@JsonKey(name: 'to_name') String? toName
});




}
/// @nodoc
class __$RouteStepCopyWithImpl<$Res>
    implements _$RouteStepCopyWith<$Res> {
  __$RouteStepCopyWithImpl(this._self, this._then);

  final _RouteStep _self;
  final $Res Function(_RouteStep) _then;

/// Create a copy of RouteStep
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? type = null,Object? start = null,Object? end = null,Object? color = freezed,Object? stopName = freezed,Object? durationMin = null,Object? mode = freezed,Object? line = freezed,Object? fromName = freezed,Object? toName = freezed,}) {
  return _then(_RouteStep(
type: null == type ? _self.type : type // ignore: cast_nullable_to_non_nullable
as String,start: null == start ? _self.start : start // ignore: cast_nullable_to_non_nullable
as LatLng,end: null == end ? _self.end : end // ignore: cast_nullable_to_non_nullable
as LatLng,color: freezed == color ? _self.color : color // ignore: cast_nullable_to_non_nullable
as String?,stopName: freezed == stopName ? _self.stopName : stopName // ignore: cast_nullable_to_non_nullable
as String?,durationMin: null == durationMin ? _self.durationMin : durationMin // ignore: cast_nullable_to_non_nullable
as double,mode: freezed == mode ? _self.mode : mode // ignore: cast_nullable_to_non_nullable
as String?,line: freezed == line ? _self.line : line // ignore: cast_nullable_to_non_nullable
as String?,fromName: freezed == fromName ? _self.fromName : fromName // ignore: cast_nullable_to_non_nullable
as String?,toName: freezed == toName ? _self.toName : toName // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}


}


/// @nodoc
mixin _$Itinerary {

/// Total duration in **seconds** (backend field `duration`).
 double get duration;@JsonKey(name: 'duration_min') double get durationMin; int get transfers;@JsonKey(name: 'has_walk_transfer') bool get hasWalkTransfer; List<RouteStep> get steps;@JsonKey(name: 'fare_dinars') double? get fareDinars;
/// Create a copy of Itinerary
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$ItineraryCopyWith<Itinerary> get copyWith => _$ItineraryCopyWithImpl<Itinerary>(this as Itinerary, _$identity);

  /// Serializes this Itinerary to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as Itinerary;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is Itinerary&&(identical(other.duration, _this.duration) || other.duration == _this.duration)&&(identical(other.durationMin, _this.durationMin) || other.durationMin == _this.durationMin)&&(identical(other.transfers, _this.transfers) || other.transfers == _this.transfers)&&(identical(other.hasWalkTransfer, _this.hasWalkTransfer) || other.hasWalkTransfer == _this.hasWalkTransfer)&&const DeepCollectionEquality().equals(other.steps, _this.steps)&&(identical(other.fareDinars, _this.fareDinars) || other.fareDinars == _this.fareDinars));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as Itinerary;
  return Object.hash(runtimeType,_this.duration,_this.durationMin,_this.transfers,_this.hasWalkTransfer,const DeepCollectionEquality().hash(_this.steps),_this.fareDinars);
}

@override
String toString() {
  final _this = this as Itinerary;
  return 'Itinerary(duration: ${_this.duration}, durationMin: ${_this.durationMin}, transfers: ${_this.transfers}, hasWalkTransfer: ${_this.hasWalkTransfer}, steps: ${_this.steps}, fareDinars: ${_this.fareDinars})';
}


}

/// @nodoc
abstract mixin class $ItineraryCopyWith<$Res>  {
  factory $ItineraryCopyWith(Itinerary value, $Res Function(Itinerary) _then) = _$ItineraryCopyWithImpl;
@useResult
$Res call({
 double duration,@JsonKey(name: 'duration_min') double durationMin, int transfers,@JsonKey(name: 'has_walk_transfer') bool hasWalkTransfer, List<RouteStep> steps,@JsonKey(name: 'fare_dinars') double? fareDinars
});




}
/// @nodoc
class _$ItineraryCopyWithImpl<$Res>
    implements $ItineraryCopyWith<$Res> {
  _$ItineraryCopyWithImpl(this._self, this._then);

  final Itinerary _self;
  final $Res Function(Itinerary) _then;

/// Create a copy of Itinerary
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? duration = null,Object? durationMin = null,Object? transfers = null,Object? hasWalkTransfer = null,Object? steps = null,Object? fareDinars = freezed,}) {
  return _then(Itinerary(
duration: null == duration ? _self.duration : duration // ignore: cast_nullable_to_non_nullable
as double,durationMin: null == durationMin ? _self.durationMin : durationMin // ignore: cast_nullable_to_non_nullable
as double,transfers: null == transfers ? _self.transfers : transfers // ignore: cast_nullable_to_non_nullable
as int,hasWalkTransfer: null == hasWalkTransfer ? _self.hasWalkTransfer : hasWalkTransfer // ignore: cast_nullable_to_non_nullable
as bool,steps: null == steps ? _self.steps : steps // ignore: cast_nullable_to_non_nullable
as List<RouteStep>,fareDinars: freezed == fareDinars ? _self.fareDinars : fareDinars // ignore: cast_nullable_to_non_nullable
as double?,
  ));
}

}


/// Adds pattern-matching-related methods to [Itinerary].
extension ItineraryPatterns on Itinerary {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _Itinerary value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _Itinerary() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _Itinerary value)  $default,){
final _that = this;
switch (_that) {
case _Itinerary():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _Itinerary value)?  $default,){
final _that = this;
switch (_that) {
case _Itinerary() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( double duration, @JsonKey(name: 'duration_min')  double durationMin,  int transfers, @JsonKey(name: 'has_walk_transfer')  bool hasWalkTransfer,  List<RouteStep> steps, @JsonKey(name: 'fare_dinars')  double? fareDinars)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _Itinerary() when $default != null:
return $default(_that.duration,_that.durationMin,_that.transfers,_that.hasWalkTransfer,_that.steps,_that.fareDinars);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( double duration, @JsonKey(name: 'duration_min')  double durationMin,  int transfers, @JsonKey(name: 'has_walk_transfer')  bool hasWalkTransfer,  List<RouteStep> steps, @JsonKey(name: 'fare_dinars')  double? fareDinars)  $default,) {final _that = this;
switch (_that) {
case _Itinerary():
return $default(_that.duration,_that.durationMin,_that.transfers,_that.hasWalkTransfer,_that.steps,_that.fareDinars);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( double duration, @JsonKey(name: 'duration_min')  double durationMin,  int transfers, @JsonKey(name: 'has_walk_transfer')  bool hasWalkTransfer,  List<RouteStep> steps, @JsonKey(name: 'fare_dinars')  double? fareDinars)?  $default,) {final _that = this;
switch (_that) {
case _Itinerary() when $default != null:
return $default(_that.duration,_that.durationMin,_that.transfers,_that.hasWalkTransfer,_that.steps,_that.fareDinars);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _Itinerary extends Itinerary {
  const _Itinerary({required this.duration, @JsonKey(name: 'duration_min') required this.durationMin, this.transfers = 0, @JsonKey(name: 'has_walk_transfer') this.hasWalkTransfer = false,  List<RouteStep> steps = const <RouteStep>[], @JsonKey(name: 'fare_dinars') this.fareDinars}): _steps = steps,super._();
  factory _Itinerary.fromJson(Map<String, dynamic> json) => _$ItineraryFromJson(json);

/// Total duration in **seconds** (backend field `duration`).
@override final  double duration;
@override@JsonKey(name: 'duration_min') final  double durationMin;
@override@JsonKey() final  int transfers;
@override@JsonKey(name: 'has_walk_transfer') final  bool hasWalkTransfer;
 final  List<RouteStep> _steps;
@override@JsonKey() List<RouteStep> get steps {
  if (_steps is EqualUnmodifiableListView) return _steps;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_steps);
}

@override@JsonKey(name: 'fare_dinars') final  double? fareDinars;

/// Create a copy of Itinerary
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$ItineraryCopyWith<_Itinerary> get copyWith => __$ItineraryCopyWithImpl<_Itinerary>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$ItineraryToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _Itinerary&&(identical(other.duration, duration) || other.duration == duration)&&(identical(other.durationMin, durationMin) || other.durationMin == durationMin)&&(identical(other.transfers, transfers) || other.transfers == transfers)&&(identical(other.hasWalkTransfer, hasWalkTransfer) || other.hasWalkTransfer == hasWalkTransfer)&&const DeepCollectionEquality().equals(other.steps, _steps)&&(identical(other.fareDinars, fareDinars) || other.fareDinars == fareDinars));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,duration,durationMin,transfers,hasWalkTransfer,const DeepCollectionEquality().hash(_steps),fareDinars);
}

@override
String toString() {
    return 'Itinerary(duration: $duration, durationMin: $durationMin, transfers: $transfers, hasWalkTransfer: $hasWalkTransfer, steps: $steps, fareDinars: $fareDinars)';
}


}

/// @nodoc
abstract mixin class _$ItineraryCopyWith<$Res> implements $ItineraryCopyWith<$Res> {
  factory _$ItineraryCopyWith(_Itinerary value, $Res Function(_Itinerary) _then) = __$ItineraryCopyWithImpl;
@override @useResult
$Res call({
 double duration,@JsonKey(name: 'duration_min') double durationMin, int transfers,@JsonKey(name: 'has_walk_transfer') bool hasWalkTransfer, List<RouteStep> steps,@JsonKey(name: 'fare_dinars') double? fareDinars
});




}
/// @nodoc
class __$ItineraryCopyWithImpl<$Res>
    implements _$ItineraryCopyWith<$Res> {
  __$ItineraryCopyWithImpl(this._self, this._then);

  final _Itinerary _self;
  final $Res Function(_Itinerary) _then;

/// Create a copy of Itinerary
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? duration = null,Object? durationMin = null,Object? transfers = null,Object? hasWalkTransfer = null,Object? steps = null,Object? fareDinars = freezed,}) {
  return _then(_Itinerary(
duration: null == duration ? _self.duration : duration // ignore: cast_nullable_to_non_nullable
as double,durationMin: null == durationMin ? _self.durationMin : durationMin // ignore: cast_nullable_to_non_nullable
as double,transfers: null == transfers ? _self.transfers : transfers // ignore: cast_nullable_to_non_nullable
as int,hasWalkTransfer: null == hasWalkTransfer ? _self.hasWalkTransfer : hasWalkTransfer // ignore: cast_nullable_to_non_nullable
as bool,steps: null == steps ? _self._steps : steps // ignore: cast_nullable_to_non_nullable
as List<RouteStep>,fareDinars: freezed == fareDinars ? _self.fareDinars : fareDinars // ignore: cast_nullable_to_non_nullable
as double?,
  ));
}


}


/// @nodoc
mixin _$RouteResponse {

@JsonKey(name: 'best_fastest') Itinerary? get bestFastest;@JsonKey(name: 'best_less_walk') Itinerary? get bestLessWalk; List<Itinerary> get alternatives; String? get source; String? get error;
/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$RouteResponseCopyWith<RouteResponse> get copyWith => _$RouteResponseCopyWithImpl<RouteResponse>(this as RouteResponse, _$identity);

  /// Serializes this RouteResponse to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as RouteResponse;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is RouteResponse&&(identical(other.bestFastest, _this.bestFastest) || other.bestFastest == _this.bestFastest)&&(identical(other.bestLessWalk, _this.bestLessWalk) || other.bestLessWalk == _this.bestLessWalk)&&const DeepCollectionEquality().equals(other.alternatives, _this.alternatives)&&(identical(other.source, _this.source) || other.source == _this.source)&&(identical(other.error, _this.error) || other.error == _this.error));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as RouteResponse;
  return Object.hash(runtimeType,_this.bestFastest,_this.bestLessWalk,const DeepCollectionEquality().hash(_this.alternatives),_this.source,_this.error);
}

@override
String toString() {
  final _this = this as RouteResponse;
  return 'RouteResponse(bestFastest: ${_this.bestFastest}, bestLessWalk: ${_this.bestLessWalk}, alternatives: ${_this.alternatives}, source: ${_this.source}, error: ${_this.error})';
}


}

/// @nodoc
abstract mixin class $RouteResponseCopyWith<$Res>  {
  factory $RouteResponseCopyWith(RouteResponse value, $Res Function(RouteResponse) _then) = _$RouteResponseCopyWithImpl;
@useResult
$Res call({
@JsonKey(name: 'best_fastest') Itinerary? bestFastest,@JsonKey(name: 'best_less_walk') Itinerary? bestLessWalk, List<Itinerary> alternatives, String? source, String? error
});


$ItineraryCopyWith<$Res>? get bestFastest;$ItineraryCopyWith<$Res>? get bestLessWalk;

}
/// @nodoc
class _$RouteResponseCopyWithImpl<$Res>
    implements $RouteResponseCopyWith<$Res> {
  _$RouteResponseCopyWithImpl(this._self, this._then);

  final RouteResponse _self;
  final $Res Function(RouteResponse) _then;

/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? bestFastest = freezed,Object? bestLessWalk = freezed,Object? alternatives = null,Object? source = freezed,Object? error = freezed,}) {
  return _then(RouteResponse(
bestFastest: freezed == bestFastest ? _self.bestFastest : bestFastest // ignore: cast_nullable_to_non_nullable
as Itinerary?,bestLessWalk: freezed == bestLessWalk ? _self.bestLessWalk : bestLessWalk // ignore: cast_nullable_to_non_nullable
as Itinerary?,alternatives: null == alternatives ? _self.alternatives : alternatives // ignore: cast_nullable_to_non_nullable
as List<Itinerary>,source: freezed == source ? _self.source : source // ignore: cast_nullable_to_non_nullable
as String?,error: freezed == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}
/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$ItineraryCopyWith<$Res>? get bestFastest {
    if (_self.bestFastest == null) {
    return null;
  }

  return $ItineraryCopyWith<$Res>(_self.bestFastest!, (value) {
    return _then(_self.copyWith(bestFastest: value));
  });
}/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$ItineraryCopyWith<$Res>? get bestLessWalk {
    if (_self.bestLessWalk == null) {
    return null;
  }

  return $ItineraryCopyWith<$Res>(_self.bestLessWalk!, (value) {
    return _then(_self.copyWith(bestLessWalk: value));
  });
}
}


/// Adds pattern-matching-related methods to [RouteResponse].
extension RouteResponsePatterns on RouteResponse {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _RouteResponse value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _RouteResponse() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _RouteResponse value)  $default,){
final _that = this;
switch (_that) {
case _RouteResponse():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _RouteResponse value)?  $default,){
final _that = this;
switch (_that) {
case _RouteResponse() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function(@JsonKey(name: 'best_fastest')  Itinerary? bestFastest, @JsonKey(name: 'best_less_walk')  Itinerary? bestLessWalk,  List<Itinerary> alternatives,  String? source,  String? error)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _RouteResponse() when $default != null:
return $default(_that.bestFastest,_that.bestLessWalk,_that.alternatives,_that.source,_that.error);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function(@JsonKey(name: 'best_fastest')  Itinerary? bestFastest, @JsonKey(name: 'best_less_walk')  Itinerary? bestLessWalk,  List<Itinerary> alternatives,  String? source,  String? error)  $default,) {final _that = this;
switch (_that) {
case _RouteResponse():
return $default(_that.bestFastest,_that.bestLessWalk,_that.alternatives,_that.source,_that.error);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function(@JsonKey(name: 'best_fastest')  Itinerary? bestFastest, @JsonKey(name: 'best_less_walk')  Itinerary? bestLessWalk,  List<Itinerary> alternatives,  String? source,  String? error)?  $default,) {final _that = this;
switch (_that) {
case _RouteResponse() when $default != null:
return $default(_that.bestFastest,_that.bestLessWalk,_that.alternatives,_that.source,_that.error);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _RouteResponse extends RouteResponse {
  const _RouteResponse({@JsonKey(name: 'best_fastest') this.bestFastest, @JsonKey(name: 'best_less_walk') this.bestLessWalk,  List<Itinerary> alternatives = const <Itinerary>[], this.source, this.error}): _alternatives = alternatives,super._();
  factory _RouteResponse.fromJson(Map<String, dynamic> json) => _$RouteResponseFromJson(json);

@override@JsonKey(name: 'best_fastest') final  Itinerary? bestFastest;
@override@JsonKey(name: 'best_less_walk') final  Itinerary? bestLessWalk;
 final  List<Itinerary> _alternatives;
@override@JsonKey() List<Itinerary> get alternatives {
  if (_alternatives is EqualUnmodifiableListView) return _alternatives;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_alternatives);
}

@override final  String? source;
@override final  String? error;

/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$RouteResponseCopyWith<_RouteResponse> get copyWith => __$RouteResponseCopyWithImpl<_RouteResponse>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$RouteResponseToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _RouteResponse&&(identical(other.bestFastest, bestFastest) || other.bestFastest == bestFastest)&&(identical(other.bestLessWalk, bestLessWalk) || other.bestLessWalk == bestLessWalk)&&const DeepCollectionEquality().equals(other.alternatives, _alternatives)&&(identical(other.source, source) || other.source == source)&&(identical(other.error, error) || other.error == error));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,bestFastest,bestLessWalk,const DeepCollectionEquality().hash(_alternatives),source,error);
}

@override
String toString() {
    return 'RouteResponse(bestFastest: $bestFastest, bestLessWalk: $bestLessWalk, alternatives: $alternatives, source: $source, error: $error)';
}


}

/// @nodoc
abstract mixin class _$RouteResponseCopyWith<$Res> implements $RouteResponseCopyWith<$Res> {
  factory _$RouteResponseCopyWith(_RouteResponse value, $Res Function(_RouteResponse) _then) = __$RouteResponseCopyWithImpl;
@override @useResult
$Res call({
@JsonKey(name: 'best_fastest') Itinerary? bestFastest,@JsonKey(name: 'best_less_walk') Itinerary? bestLessWalk, List<Itinerary> alternatives, String? source, String? error
});


@override $ItineraryCopyWith<$Res>? get bestFastest;@override $ItineraryCopyWith<$Res>? get bestLessWalk;

}
/// @nodoc
class __$RouteResponseCopyWithImpl<$Res>
    implements _$RouteResponseCopyWith<$Res> {
  __$RouteResponseCopyWithImpl(this._self, this._then);

  final _RouteResponse _self;
  final $Res Function(_RouteResponse) _then;

/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? bestFastest = freezed,Object? bestLessWalk = freezed,Object? alternatives = null,Object? source = freezed,Object? error = freezed,}) {
  return _then(_RouteResponse(
bestFastest: freezed == bestFastest ? _self.bestFastest : bestFastest // ignore: cast_nullable_to_non_nullable
as Itinerary?,bestLessWalk: freezed == bestLessWalk ? _self.bestLessWalk : bestLessWalk // ignore: cast_nullable_to_non_nullable
as Itinerary?,alternatives: null == alternatives ? _self._alternatives : alternatives // ignore: cast_nullable_to_non_nullable
as List<Itinerary>,source: freezed == source ? _self.source : source // ignore: cast_nullable_to_non_nullable
as String?,error: freezed == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$ItineraryCopyWith<$Res>? get bestFastest {
    if (_self.bestFastest == null) {
    return null;
  }

  return $ItineraryCopyWith<$Res>(_self.bestFastest!, (value) {
    return _then(_self.copyWith(bestFastest: value));
  });
}/// Create a copy of RouteResponse
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$ItineraryCopyWith<$Res>? get bestLessWalk {
    if (_self.bestLessWalk == null) {
    return null;
  }

  return $ItineraryCopyWith<$Res>(_self.bestLessWalk!, (value) {
    return _then(_self.copyWith(bestLessWalk: value));
  });
}
}

// dart format on
