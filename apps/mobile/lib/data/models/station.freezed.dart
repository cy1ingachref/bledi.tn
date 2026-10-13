// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'station.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$Station {

 String get id; String get name; double get lat; double get lon;/// Seed mode: `bus` | `train` | `metro` | `rail` | `unknown`, or a
/// `louage*` / `taxi` value for the secondary-seed stops.
 String? get mode;/// Every mode a multi-modal stop (e.g. a louage hub) belongs to.
@JsonKey(name: 'modes') List<String> get modes;/// Governorate, derived by the backend from the nearest seat.
 String? get city; String? get operator; String? get source; String? get nameEn; List<StationLineRef> get lines;
/// Create a copy of Station
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$StationCopyWith<Station> get copyWith => _$StationCopyWithImpl<Station>(this as Station, _$identity);

  /// Serializes this Station to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as Station;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is Station&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.name, _this.name) || other.name == _this.name)&&(identical(other.lat, _this.lat) || other.lat == _this.lat)&&(identical(other.lon, _this.lon) || other.lon == _this.lon)&&(identical(other.mode, _this.mode) || other.mode == _this.mode)&&const DeepCollectionEquality().equals(other.modes, _this.modes)&&(identical(other.city, _this.city) || other.city == _this.city)&&(identical(other.operator, _this.operator) || other.operator == _this.operator)&&(identical(other.source, _this.source) || other.source == _this.source)&&(identical(other.nameEn, _this.nameEn) || other.nameEn == _this.nameEn)&&const DeepCollectionEquality().equals(other.lines, _this.lines));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as Station;
  return Object.hash(runtimeType,_this.id,_this.name,_this.lat,_this.lon,_this.mode,const DeepCollectionEquality().hash(_this.modes),_this.city,_this.operator,_this.source,_this.nameEn,const DeepCollectionEquality().hash(_this.lines));
}

@override
String toString() {
  final _this = this as Station;
  return 'Station(id: ${_this.id}, name: ${_this.name}, lat: ${_this.lat}, lon: ${_this.lon}, mode: ${_this.mode}, modes: ${_this.modes}, city: ${_this.city}, operator: ${_this.operator}, source: ${_this.source}, nameEn: ${_this.nameEn}, lines: ${_this.lines})';
}


}

/// @nodoc
abstract mixin class $StationCopyWith<$Res>  {
  factory $StationCopyWith(Station value, $Res Function(Station) _then) = _$StationCopyWithImpl;
@useResult
$Res call({
 String id, String name, double lat, double lon, String? mode,@JsonKey(name: 'modes') List<String> modes, String? city, String? operator, String? source, String? nameEn, List<StationLineRef> lines
});




}
/// @nodoc
class _$StationCopyWithImpl<$Res>
    implements $StationCopyWith<$Res> {
  _$StationCopyWithImpl(this._self, this._then);

  final Station _self;
  final $Res Function(Station) _then;

/// Create a copy of Station
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? name = null,Object? lat = null,Object? lon = null,Object? mode = freezed,Object? modes = null,Object? city = freezed,Object? operator = freezed,Object? source = freezed,Object? nameEn = freezed,Object? lines = null,}) {
  return _then(Station(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,lat: null == lat ? _self.lat : lat // ignore: cast_nullable_to_non_nullable
as double,lon: null == lon ? _self.lon : lon // ignore: cast_nullable_to_non_nullable
as double,mode: freezed == mode ? _self.mode : mode // ignore: cast_nullable_to_non_nullable
as String?,modes: null == modes ? _self.modes : modes // ignore: cast_nullable_to_non_nullable
as List<String>,city: freezed == city ? _self.city : city // ignore: cast_nullable_to_non_nullable
as String?,operator: freezed == operator ? _self.operator : operator // ignore: cast_nullable_to_non_nullable
as String?,source: freezed == source ? _self.source : source // ignore: cast_nullable_to_non_nullable
as String?,nameEn: freezed == nameEn ? _self.nameEn : nameEn // ignore: cast_nullable_to_non_nullable
as String?,lines: null == lines ? _self.lines : lines // ignore: cast_nullable_to_non_nullable
as List<StationLineRef>,
  ));
}

}


/// Adds pattern-matching-related methods to [Station].
extension StationPatterns on Station {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _Station value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _Station() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _Station value)  $default,){
final _that = this;
switch (_that) {
case _Station():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _Station value)?  $default,){
final _that = this;
switch (_that) {
case _Station() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String name,  double lat,  double lon,  String? mode, @JsonKey(name: 'modes')  List<String> modes,  String? city,  String? operator,  String? source,  String? nameEn,  List<StationLineRef> lines)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _Station() when $default != null:
return $default(_that.id,_that.name,_that.lat,_that.lon,_that.mode,_that.modes,_that.city,_that.operator,_that.source,_that.nameEn,_that.lines);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String name,  double lat,  double lon,  String? mode, @JsonKey(name: 'modes')  List<String> modes,  String? city,  String? operator,  String? source,  String? nameEn,  List<StationLineRef> lines)  $default,) {final _that = this;
switch (_that) {
case _Station():
return $default(_that.id,_that.name,_that.lat,_that.lon,_that.mode,_that.modes,_that.city,_that.operator,_that.source,_that.nameEn,_that.lines);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String name,  double lat,  double lon,  String? mode, @JsonKey(name: 'modes')  List<String> modes,  String? city,  String? operator,  String? source,  String? nameEn,  List<StationLineRef> lines)?  $default,) {final _that = this;
switch (_that) {
case _Station() when $default != null:
return $default(_that.id,_that.name,_that.lat,_that.lon,_that.mode,_that.modes,_that.city,_that.operator,_that.source,_that.nameEn,_that.lines);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _Station extends Station {
  const _Station({required this.id, required this.name, required this.lat, required this.lon, this.mode, @JsonKey(name: 'modes')  List<String> modes = const <String>[], this.city, this.operator, this.source, this.nameEn,  List<StationLineRef> lines = const <StationLineRef>[]}): _modes = modes,_lines = lines,super._();
  factory _Station.fromJson(Map<String, dynamic> json) => _$StationFromJson(json);

@override final  String id;
@override final  String name;
@override final  double lat;
@override final  double lon;
/// Seed mode: `bus` | `train` | `metro` | `rail` | `unknown`, or a
/// `louage*` / `taxi` value for the secondary-seed stops.
@override final  String? mode;
/// Every mode a multi-modal stop (e.g. a louage hub) belongs to.
 final  List<String> _modes;
/// Every mode a multi-modal stop (e.g. a louage hub) belongs to.
@override@JsonKey(name: 'modes') List<String> get modes {
  if (_modes is EqualUnmodifiableListView) return _modes;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_modes);
}

/// Governorate, derived by the backend from the nearest seat.
@override final  String? city;
@override final  String? operator;
@override final  String? source;
@override final  String? nameEn;
 final  List<StationLineRef> _lines;
@override@JsonKey() List<StationLineRef> get lines {
  if (_lines is EqualUnmodifiableListView) return _lines;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_lines);
}


/// Create a copy of Station
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$StationCopyWith<_Station> get copyWith => __$StationCopyWithImpl<_Station>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$StationToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _Station&&(identical(other.id, id) || other.id == id)&&(identical(other.name, name) || other.name == name)&&(identical(other.lat, lat) || other.lat == lat)&&(identical(other.lon, lon) || other.lon == lon)&&(identical(other.mode, mode) || other.mode == mode)&&const DeepCollectionEquality().equals(other.modes, _modes)&&(identical(other.city, city) || other.city == city)&&(identical(other.operator, operator) || other.operator == operator)&&(identical(other.source, source) || other.source == source)&&(identical(other.nameEn, nameEn) || other.nameEn == nameEn)&&const DeepCollectionEquality().equals(other.lines, _lines));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,id,name,lat,lon,mode,const DeepCollectionEquality().hash(_modes),city,operator,source,nameEn,const DeepCollectionEquality().hash(_lines));
}

@override
String toString() {
    return 'Station(id: $id, name: $name, lat: $lat, lon: $lon, mode: $mode, modes: $modes, city: $city, operator: $operator, source: $source, nameEn: $nameEn, lines: $lines)';
}


}

/// @nodoc
abstract mixin class _$StationCopyWith<$Res> implements $StationCopyWith<$Res> {
  factory _$StationCopyWith(_Station value, $Res Function(_Station) _then) = __$StationCopyWithImpl;
@override @useResult
$Res call({
 String id, String name, double lat, double lon, String? mode,@JsonKey(name: 'modes') List<String> modes, String? city, String? operator, String? source, String? nameEn, List<StationLineRef> lines
});




}
/// @nodoc
class __$StationCopyWithImpl<$Res>
    implements _$StationCopyWith<$Res> {
  __$StationCopyWithImpl(this._self, this._then);

  final _Station _self;
  final $Res Function(_Station) _then;

/// Create a copy of Station
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? name = null,Object? lat = null,Object? lon = null,Object? mode = freezed,Object? modes = null,Object? city = freezed,Object? operator = freezed,Object? source = freezed,Object? nameEn = freezed,Object? lines = null,}) {
  return _then(_Station(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,lat: null == lat ? _self.lat : lat // ignore: cast_nullable_to_non_nullable
as double,lon: null == lon ? _self.lon : lon // ignore: cast_nullable_to_non_nullable
as double,mode: freezed == mode ? _self.mode : mode // ignore: cast_nullable_to_non_nullable
as String?,modes: null == modes ? _self._modes : modes // ignore: cast_nullable_to_non_nullable
as List<String>,city: freezed == city ? _self.city : city // ignore: cast_nullable_to_non_nullable
as String?,operator: freezed == operator ? _self.operator : operator // ignore: cast_nullable_to_non_nullable
as String?,source: freezed == source ? _self.source : source // ignore: cast_nullable_to_non_nullable
as String?,nameEn: freezed == nameEn ? _self.nameEn : nameEn // ignore: cast_nullable_to_non_nullable
as String?,lines: null == lines ? _self._lines : lines // ignore: cast_nullable_to_non_nullable
as List<StationLineRef>,
  ));
}


}


/// @nodoc
mixin _$StationLineRef {

@JsonKey(name: 'route_short_name') String? get routeShortName;@JsonKey(name: 'route_color') String? get routeColor; String? get direction;@JsonKey(name: 'route_id') String? get routeId;
/// Create a copy of StationLineRef
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$StationLineRefCopyWith<StationLineRef> get copyWith => _$StationLineRefCopyWithImpl<StationLineRef>(this as StationLineRef, _$identity);

  /// Serializes this StationLineRef to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as StationLineRef;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is StationLineRef&&(identical(other.routeShortName, _this.routeShortName) || other.routeShortName == _this.routeShortName)&&(identical(other.routeColor, _this.routeColor) || other.routeColor == _this.routeColor)&&(identical(other.direction, _this.direction) || other.direction == _this.direction)&&(identical(other.routeId, _this.routeId) || other.routeId == _this.routeId));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as StationLineRef;
  return Object.hash(runtimeType,_this.routeShortName,_this.routeColor,_this.direction,_this.routeId);
}

@override
String toString() {
  final _this = this as StationLineRef;
  return 'StationLineRef(routeShortName: ${_this.routeShortName}, routeColor: ${_this.routeColor}, direction: ${_this.direction}, routeId: ${_this.routeId})';
}


}

/// @nodoc
abstract mixin class $StationLineRefCopyWith<$Res>  {
  factory $StationLineRefCopyWith(StationLineRef value, $Res Function(StationLineRef) _then) = _$StationLineRefCopyWithImpl;
@useResult
$Res call({
@JsonKey(name: 'route_short_name') String? routeShortName,@JsonKey(name: 'route_color') String? routeColor, String? direction,@JsonKey(name: 'route_id') String? routeId
});




}
/// @nodoc
class _$StationLineRefCopyWithImpl<$Res>
    implements $StationLineRefCopyWith<$Res> {
  _$StationLineRefCopyWithImpl(this._self, this._then);

  final StationLineRef _self;
  final $Res Function(StationLineRef) _then;

/// Create a copy of StationLineRef
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? routeShortName = freezed,Object? routeColor = freezed,Object? direction = freezed,Object? routeId = freezed,}) {
  return _then(StationLineRef(
routeShortName: freezed == routeShortName ? _self.routeShortName : routeShortName // ignore: cast_nullable_to_non_nullable
as String?,routeColor: freezed == routeColor ? _self.routeColor : routeColor // ignore: cast_nullable_to_non_nullable
as String?,direction: freezed == direction ? _self.direction : direction // ignore: cast_nullable_to_non_nullable
as String?,routeId: freezed == routeId ? _self.routeId : routeId // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

}


/// Adds pattern-matching-related methods to [StationLineRef].
extension StationLineRefPatterns on StationLineRef {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _StationLineRef value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _StationLineRef() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _StationLineRef value)  $default,){
final _that = this;
switch (_that) {
case _StationLineRef():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _StationLineRef value)?  $default,){
final _that = this;
switch (_that) {
case _StationLineRef() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function(@JsonKey(name: 'route_short_name')  String? routeShortName, @JsonKey(name: 'route_color')  String? routeColor,  String? direction, @JsonKey(name: 'route_id')  String? routeId)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _StationLineRef() when $default != null:
return $default(_that.routeShortName,_that.routeColor,_that.direction,_that.routeId);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function(@JsonKey(name: 'route_short_name')  String? routeShortName, @JsonKey(name: 'route_color')  String? routeColor,  String? direction, @JsonKey(name: 'route_id')  String? routeId)  $default,) {final _that = this;
switch (_that) {
case _StationLineRef():
return $default(_that.routeShortName,_that.routeColor,_that.direction,_that.routeId);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function(@JsonKey(name: 'route_short_name')  String? routeShortName, @JsonKey(name: 'route_color')  String? routeColor,  String? direction, @JsonKey(name: 'route_id')  String? routeId)?  $default,) {final _that = this;
switch (_that) {
case _StationLineRef() when $default != null:
return $default(_that.routeShortName,_that.routeColor,_that.direction,_that.routeId);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _StationLineRef extends StationLineRef {
  const _StationLineRef({@JsonKey(name: 'route_short_name') this.routeShortName, @JsonKey(name: 'route_color') this.routeColor, this.direction, @JsonKey(name: 'route_id') this.routeId}): super._();
  factory _StationLineRef.fromJson(Map<String, dynamic> json) => _$StationLineRefFromJson(json);

@override@JsonKey(name: 'route_short_name') final  String? routeShortName;
@override@JsonKey(name: 'route_color') final  String? routeColor;
@override final  String? direction;
@override@JsonKey(name: 'route_id') final  String? routeId;

/// Create a copy of StationLineRef
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$StationLineRefCopyWith<_StationLineRef> get copyWith => __$StationLineRefCopyWithImpl<_StationLineRef>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$StationLineRefToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _StationLineRef&&(identical(other.routeShortName, routeShortName) || other.routeShortName == routeShortName)&&(identical(other.routeColor, routeColor) || other.routeColor == routeColor)&&(identical(other.direction, direction) || other.direction == direction)&&(identical(other.routeId, routeId) || other.routeId == routeId));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,routeShortName,routeColor,direction,routeId);
}

@override
String toString() {
    return 'StationLineRef(routeShortName: $routeShortName, routeColor: $routeColor, direction: $direction, routeId: $routeId)';
}


}

/// @nodoc
abstract mixin class _$StationLineRefCopyWith<$Res> implements $StationLineRefCopyWith<$Res> {
  factory _$StationLineRefCopyWith(_StationLineRef value, $Res Function(_StationLineRef) _then) = __$StationLineRefCopyWithImpl;
@override @useResult
$Res call({
@JsonKey(name: 'route_short_name') String? routeShortName,@JsonKey(name: 'route_color') String? routeColor, String? direction,@JsonKey(name: 'route_id') String? routeId
});




}
/// @nodoc
class __$StationLineRefCopyWithImpl<$Res>
    implements _$StationLineRefCopyWith<$Res> {
  __$StationLineRefCopyWithImpl(this._self, this._then);

  final _StationLineRef _self;
  final $Res Function(_StationLineRef) _then;

/// Create a copy of StationLineRef
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? routeShortName = freezed,Object? routeColor = freezed,Object? direction = freezed,Object? routeId = freezed,}) {
  return _then(_StationLineRef(
routeShortName: freezed == routeShortName ? _self.routeShortName : routeShortName // ignore: cast_nullable_to_non_nullable
as String?,routeColor: freezed == routeColor ? _self.routeColor : routeColor // ignore: cast_nullable_to_non_nullable
as String?,direction: freezed == direction ? _self.direction : direction // ignore: cast_nullable_to_non_nullable
as String?,routeId: freezed == routeId ? _self.routeId : routeId // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}


}

// dart format on
