// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'health.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$Health {

 String get status; String? get version; String? get service;@JsonKey(name: 'seed_file') String? get seedFile;@JsonKey(name: 'stations_count') int get stationsCount;@JsonKey(name: 'lines_count') int get linesCount;
/// Create a copy of Health
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$HealthCopyWith<Health> get copyWith => _$HealthCopyWithImpl<Health>(this as Health, _$identity);

  /// Serializes this Health to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as Health;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is Health&&(identical(other.status, _this.status) || other.status == _this.status)&&(identical(other.version, _this.version) || other.version == _this.version)&&(identical(other.service, _this.service) || other.service == _this.service)&&(identical(other.seedFile, _this.seedFile) || other.seedFile == _this.seedFile)&&(identical(other.stationsCount, _this.stationsCount) || other.stationsCount == _this.stationsCount)&&(identical(other.linesCount, _this.linesCount) || other.linesCount == _this.linesCount));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as Health;
  return Object.hash(runtimeType,_this.status,_this.version,_this.service,_this.seedFile,_this.stationsCount,_this.linesCount);
}

@override
String toString() {
  final _this = this as Health;
  return 'Health(status: ${_this.status}, version: ${_this.version}, service: ${_this.service}, seedFile: ${_this.seedFile}, stationsCount: ${_this.stationsCount}, linesCount: ${_this.linesCount})';
}


}

/// @nodoc
abstract mixin class $HealthCopyWith<$Res>  {
  factory $HealthCopyWith(Health value, $Res Function(Health) _then) = _$HealthCopyWithImpl;
@useResult
$Res call({
 String status, String? version, String? service,@JsonKey(name: 'seed_file') String? seedFile,@JsonKey(name: 'stations_count') int stationsCount,@JsonKey(name: 'lines_count') int linesCount
});




}
/// @nodoc
class _$HealthCopyWithImpl<$Res>
    implements $HealthCopyWith<$Res> {
  _$HealthCopyWithImpl(this._self, this._then);

  final Health _self;
  final $Res Function(Health) _then;

/// Create a copy of Health
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? status = null,Object? version = freezed,Object? service = freezed,Object? seedFile = freezed,Object? stationsCount = null,Object? linesCount = null,}) {
  return _then(Health(
status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,version: freezed == version ? _self.version : version // ignore: cast_nullable_to_non_nullable
as String?,service: freezed == service ? _self.service : service // ignore: cast_nullable_to_non_nullable
as String?,seedFile: freezed == seedFile ? _self.seedFile : seedFile // ignore: cast_nullable_to_non_nullable
as String?,stationsCount: null == stationsCount ? _self.stationsCount : stationsCount // ignore: cast_nullable_to_non_nullable
as int,linesCount: null == linesCount ? _self.linesCount : linesCount // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [Health].
extension HealthPatterns on Health {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _Health value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _Health() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _Health value)  $default,){
final _that = this;
switch (_that) {
case _Health():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _Health value)?  $default,){
final _that = this;
switch (_that) {
case _Health() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String status,  String? version,  String? service, @JsonKey(name: 'seed_file')  String? seedFile, @JsonKey(name: 'stations_count')  int stationsCount, @JsonKey(name: 'lines_count')  int linesCount)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _Health() when $default != null:
return $default(_that.status,_that.version,_that.service,_that.seedFile,_that.stationsCount,_that.linesCount);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String status,  String? version,  String? service, @JsonKey(name: 'seed_file')  String? seedFile, @JsonKey(name: 'stations_count')  int stationsCount, @JsonKey(name: 'lines_count')  int linesCount)  $default,) {final _that = this;
switch (_that) {
case _Health():
return $default(_that.status,_that.version,_that.service,_that.seedFile,_that.stationsCount,_that.linesCount);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String status,  String? version,  String? service, @JsonKey(name: 'seed_file')  String? seedFile, @JsonKey(name: 'stations_count')  int stationsCount, @JsonKey(name: 'lines_count')  int linesCount)?  $default,) {final _that = this;
switch (_that) {
case _Health() when $default != null:
return $default(_that.status,_that.version,_that.service,_that.seedFile,_that.stationsCount,_that.linesCount);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _Health extends Health {
  const _Health({this.status = 'ok', this.version, this.service, @JsonKey(name: 'seed_file') this.seedFile, @JsonKey(name: 'stations_count') this.stationsCount = 0, @JsonKey(name: 'lines_count') this.linesCount = 0}): super._();
  factory _Health.fromJson(Map<String, dynamic> json) => _$HealthFromJson(json);

@override@JsonKey() final  String status;
@override final  String? version;
@override final  String? service;
@override@JsonKey(name: 'seed_file') final  String? seedFile;
@override@JsonKey(name: 'stations_count') final  int stationsCount;
@override@JsonKey(name: 'lines_count') final  int linesCount;

/// Create a copy of Health
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$HealthCopyWith<_Health> get copyWith => __$HealthCopyWithImpl<_Health>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$HealthToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _Health&&(identical(other.status, status) || other.status == status)&&(identical(other.version, version) || other.version == version)&&(identical(other.service, service) || other.service == service)&&(identical(other.seedFile, seedFile) || other.seedFile == seedFile)&&(identical(other.stationsCount, stationsCount) || other.stationsCount == stationsCount)&&(identical(other.linesCount, linesCount) || other.linesCount == linesCount));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,status,version,service,seedFile,stationsCount,linesCount);
}

@override
String toString() {
    return 'Health(status: $status, version: $version, service: $service, seedFile: $seedFile, stationsCount: $stationsCount, linesCount: $linesCount)';
}


}

/// @nodoc
abstract mixin class _$HealthCopyWith<$Res> implements $HealthCopyWith<$Res> {
  factory _$HealthCopyWith(_Health value, $Res Function(_Health) _then) = __$HealthCopyWithImpl;
@override @useResult
$Res call({
 String status, String? version, String? service,@JsonKey(name: 'seed_file') String? seedFile,@JsonKey(name: 'stations_count') int stationsCount,@JsonKey(name: 'lines_count') int linesCount
});




}
/// @nodoc
class __$HealthCopyWithImpl<$Res>
    implements _$HealthCopyWith<$Res> {
  __$HealthCopyWithImpl(this._self, this._then);

  final _Health _self;
  final $Res Function(_Health) _then;

/// Create a copy of Health
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? status = null,Object? version = freezed,Object? service = freezed,Object? seedFile = freezed,Object? stationsCount = null,Object? linesCount = null,}) {
  return _then(_Health(
status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,version: freezed == version ? _self.version : version // ignore: cast_nullable_to_non_nullable
as String?,service: freezed == service ? _self.service : service // ignore: cast_nullable_to_non_nullable
as String?,seedFile: freezed == seedFile ? _self.seedFile : seedFile // ignore: cast_nullable_to_non_nullable
as String?,stationsCount: null == stationsCount ? _self.stationsCount : stationsCount // ignore: cast_nullable_to_non_nullable
as int,linesCount: null == linesCount ? _self.linesCount : linesCount // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}


/// @nodoc
mixin _$NearbyStation {

 String get id; String get name; double get lat; double get lon;@JsonKey(name: 'dist_m') double get distM; List<NearbyStationLine> get lines;
/// Create a copy of NearbyStation
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$NearbyStationCopyWith<NearbyStation> get copyWith => _$NearbyStationCopyWithImpl<NearbyStation>(this as NearbyStation, _$identity);

  /// Serializes this NearbyStation to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as NearbyStation;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is NearbyStation&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.name, _this.name) || other.name == _this.name)&&(identical(other.lat, _this.lat) || other.lat == _this.lat)&&(identical(other.lon, _this.lon) || other.lon == _this.lon)&&(identical(other.distM, _this.distM) || other.distM == _this.distM)&&const DeepCollectionEquality().equals(other.lines, _this.lines));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as NearbyStation;
  return Object.hash(runtimeType,_this.id,_this.name,_this.lat,_this.lon,_this.distM,const DeepCollectionEquality().hash(_this.lines));
}

@override
String toString() {
  final _this = this as NearbyStation;
  return 'NearbyStation(id: ${_this.id}, name: ${_this.name}, lat: ${_this.lat}, lon: ${_this.lon}, distM: ${_this.distM}, lines: ${_this.lines})';
}


}

/// @nodoc
abstract mixin class $NearbyStationCopyWith<$Res>  {
  factory $NearbyStationCopyWith(NearbyStation value, $Res Function(NearbyStation) _then) = _$NearbyStationCopyWithImpl;
@useResult
$Res call({
 String id, String name, double lat, double lon,@JsonKey(name: 'dist_m') double distM, List<NearbyStationLine> lines
});




}
/// @nodoc
class _$NearbyStationCopyWithImpl<$Res>
    implements $NearbyStationCopyWith<$Res> {
  _$NearbyStationCopyWithImpl(this._self, this._then);

  final NearbyStation _self;
  final $Res Function(NearbyStation) _then;

/// Create a copy of NearbyStation
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? name = null,Object? lat = null,Object? lon = null,Object? distM = null,Object? lines = null,}) {
  return _then(NearbyStation(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,lat: null == lat ? _self.lat : lat // ignore: cast_nullable_to_non_nullable
as double,lon: null == lon ? _self.lon : lon // ignore: cast_nullable_to_non_nullable
as double,distM: null == distM ? _self.distM : distM // ignore: cast_nullable_to_non_nullable
as double,lines: null == lines ? _self.lines : lines // ignore: cast_nullable_to_non_nullable
as List<NearbyStationLine>,
  ));
}

}


/// Adds pattern-matching-related methods to [NearbyStation].
extension NearbyStationPatterns on NearbyStation {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _NearbyStation value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _NearbyStation() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _NearbyStation value)  $default,){
final _that = this;
switch (_that) {
case _NearbyStation():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _NearbyStation value)?  $default,){
final _that = this;
switch (_that) {
case _NearbyStation() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String name,  double lat,  double lon, @JsonKey(name: 'dist_m')  double distM,  List<NearbyStationLine> lines)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _NearbyStation() when $default != null:
return $default(_that.id,_that.name,_that.lat,_that.lon,_that.distM,_that.lines);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String name,  double lat,  double lon, @JsonKey(name: 'dist_m')  double distM,  List<NearbyStationLine> lines)  $default,) {final _that = this;
switch (_that) {
case _NearbyStation():
return $default(_that.id,_that.name,_that.lat,_that.lon,_that.distM,_that.lines);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String name,  double lat,  double lon, @JsonKey(name: 'dist_m')  double distM,  List<NearbyStationLine> lines)?  $default,) {final _that = this;
switch (_that) {
case _NearbyStation() when $default != null:
return $default(_that.id,_that.name,_that.lat,_that.lon,_that.distM,_that.lines);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _NearbyStation implements NearbyStation {
  const _NearbyStation({required this.id, required this.name, required this.lat, required this.lon, @JsonKey(name: 'dist_m') this.distM = 0,  List<NearbyStationLine> lines = const <NearbyStationLine>[]}): _lines = lines;
  factory _NearbyStation.fromJson(Map<String, dynamic> json) => _$NearbyStationFromJson(json);

@override final  String id;
@override final  String name;
@override final  double lat;
@override final  double lon;
@override@JsonKey(name: 'dist_m') final  double distM;
 final  List<NearbyStationLine> _lines;
@override@JsonKey() List<NearbyStationLine> get lines {
  if (_lines is EqualUnmodifiableListView) return _lines;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_lines);
}


/// Create a copy of NearbyStation
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$NearbyStationCopyWith<_NearbyStation> get copyWith => __$NearbyStationCopyWithImpl<_NearbyStation>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$NearbyStationToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _NearbyStation&&(identical(other.id, id) || other.id == id)&&(identical(other.name, name) || other.name == name)&&(identical(other.lat, lat) || other.lat == lat)&&(identical(other.lon, lon) || other.lon == lon)&&(identical(other.distM, distM) || other.distM == distM)&&const DeepCollectionEquality().equals(other.lines, _lines));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,id,name,lat,lon,distM,const DeepCollectionEquality().hash(_lines));
}

@override
String toString() {
    return 'NearbyStation(id: $id, name: $name, lat: $lat, lon: $lon, distM: $distM, lines: $lines)';
}


}

/// @nodoc
abstract mixin class _$NearbyStationCopyWith<$Res> implements $NearbyStationCopyWith<$Res> {
  factory _$NearbyStationCopyWith(_NearbyStation value, $Res Function(_NearbyStation) _then) = __$NearbyStationCopyWithImpl;
@override @useResult
$Res call({
 String id, String name, double lat, double lon,@JsonKey(name: 'dist_m') double distM, List<NearbyStationLine> lines
});




}
/// @nodoc
class __$NearbyStationCopyWithImpl<$Res>
    implements _$NearbyStationCopyWith<$Res> {
  __$NearbyStationCopyWithImpl(this._self, this._then);

  final _NearbyStation _self;
  final $Res Function(_NearbyStation) _then;

/// Create a copy of NearbyStation
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? name = null,Object? lat = null,Object? lon = null,Object? distM = null,Object? lines = null,}) {
  return _then(_NearbyStation(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,lat: null == lat ? _self.lat : lat // ignore: cast_nullable_to_non_nullable
as double,lon: null == lon ? _self.lon : lon // ignore: cast_nullable_to_non_nullable
as double,distM: null == distM ? _self.distM : distM // ignore: cast_nullable_to_non_nullable
as double,lines: null == lines ? _self._lines : lines // ignore: cast_nullable_to_non_nullable
as List<NearbyStationLine>,
  ));
}


}


/// @nodoc
mixin _$NearbyStationLine {

@JsonKey(name: 'route_short_name') String? get routeShortName;@JsonKey(name: 'route_color') String? get routeColor; String? get direction;
/// Create a copy of NearbyStationLine
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$NearbyStationLineCopyWith<NearbyStationLine> get copyWith => _$NearbyStationLineCopyWithImpl<NearbyStationLine>(this as NearbyStationLine, _$identity);

  /// Serializes this NearbyStationLine to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as NearbyStationLine;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is NearbyStationLine&&(identical(other.routeShortName, _this.routeShortName) || other.routeShortName == _this.routeShortName)&&(identical(other.routeColor, _this.routeColor) || other.routeColor == _this.routeColor)&&(identical(other.direction, _this.direction) || other.direction == _this.direction));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as NearbyStationLine;
  return Object.hash(runtimeType,_this.routeShortName,_this.routeColor,_this.direction);
}

@override
String toString() {
  final _this = this as NearbyStationLine;
  return 'NearbyStationLine(routeShortName: ${_this.routeShortName}, routeColor: ${_this.routeColor}, direction: ${_this.direction})';
}


}

/// @nodoc
abstract mixin class $NearbyStationLineCopyWith<$Res>  {
  factory $NearbyStationLineCopyWith(NearbyStationLine value, $Res Function(NearbyStationLine) _then) = _$NearbyStationLineCopyWithImpl;
@useResult
$Res call({
@JsonKey(name: 'route_short_name') String? routeShortName,@JsonKey(name: 'route_color') String? routeColor, String? direction
});




}
/// @nodoc
class _$NearbyStationLineCopyWithImpl<$Res>
    implements $NearbyStationLineCopyWith<$Res> {
  _$NearbyStationLineCopyWithImpl(this._self, this._then);

  final NearbyStationLine _self;
  final $Res Function(NearbyStationLine) _then;

/// Create a copy of NearbyStationLine
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? routeShortName = freezed,Object? routeColor = freezed,Object? direction = freezed,}) {
  return _then(NearbyStationLine(
routeShortName: freezed == routeShortName ? _self.routeShortName : routeShortName // ignore: cast_nullable_to_non_nullable
as String?,routeColor: freezed == routeColor ? _self.routeColor : routeColor // ignore: cast_nullable_to_non_nullable
as String?,direction: freezed == direction ? _self.direction : direction // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

}


/// Adds pattern-matching-related methods to [NearbyStationLine].
extension NearbyStationLinePatterns on NearbyStationLine {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _NearbyStationLine value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _NearbyStationLine() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _NearbyStationLine value)  $default,){
final _that = this;
switch (_that) {
case _NearbyStationLine():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _NearbyStationLine value)?  $default,){
final _that = this;
switch (_that) {
case _NearbyStationLine() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function(@JsonKey(name: 'route_short_name')  String? routeShortName, @JsonKey(name: 'route_color')  String? routeColor,  String? direction)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _NearbyStationLine() when $default != null:
return $default(_that.routeShortName,_that.routeColor,_that.direction);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function(@JsonKey(name: 'route_short_name')  String? routeShortName, @JsonKey(name: 'route_color')  String? routeColor,  String? direction)  $default,) {final _that = this;
switch (_that) {
case _NearbyStationLine():
return $default(_that.routeShortName,_that.routeColor,_that.direction);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function(@JsonKey(name: 'route_short_name')  String? routeShortName, @JsonKey(name: 'route_color')  String? routeColor,  String? direction)?  $default,) {final _that = this;
switch (_that) {
case _NearbyStationLine() when $default != null:
return $default(_that.routeShortName,_that.routeColor,_that.direction);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _NearbyStationLine implements NearbyStationLine {
  const _NearbyStationLine({@JsonKey(name: 'route_short_name') this.routeShortName, @JsonKey(name: 'route_color') this.routeColor, this.direction});
  factory _NearbyStationLine.fromJson(Map<String, dynamic> json) => _$NearbyStationLineFromJson(json);

@override@JsonKey(name: 'route_short_name') final  String? routeShortName;
@override@JsonKey(name: 'route_color') final  String? routeColor;
@override final  String? direction;

/// Create a copy of NearbyStationLine
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$NearbyStationLineCopyWith<_NearbyStationLine> get copyWith => __$NearbyStationLineCopyWithImpl<_NearbyStationLine>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$NearbyStationLineToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _NearbyStationLine&&(identical(other.routeShortName, routeShortName) || other.routeShortName == routeShortName)&&(identical(other.routeColor, routeColor) || other.routeColor == routeColor)&&(identical(other.direction, direction) || other.direction == direction));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,routeShortName,routeColor,direction);
}

@override
String toString() {
    return 'NearbyStationLine(routeShortName: $routeShortName, routeColor: $routeColor, direction: $direction)';
}


}

/// @nodoc
abstract mixin class _$NearbyStationLineCopyWith<$Res> implements $NearbyStationLineCopyWith<$Res> {
  factory _$NearbyStationLineCopyWith(_NearbyStationLine value, $Res Function(_NearbyStationLine) _then) = __$NearbyStationLineCopyWithImpl;
@override @useResult
$Res call({
@JsonKey(name: 'route_short_name') String? routeShortName,@JsonKey(name: 'route_color') String? routeColor, String? direction
});




}
/// @nodoc
class __$NearbyStationLineCopyWithImpl<$Res>
    implements _$NearbyStationLineCopyWith<$Res> {
  __$NearbyStationLineCopyWithImpl(this._self, this._then);

  final _NearbyStationLine _self;
  final $Res Function(_NearbyStationLine) _then;

/// Create a copy of NearbyStationLine
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? routeShortName = freezed,Object? routeColor = freezed,Object? direction = freezed,}) {
  return _then(_NearbyStationLine(
routeShortName: freezed == routeShortName ? _self.routeShortName : routeShortName // ignore: cast_nullable_to_non_nullable
as String?,routeColor: freezed == routeColor ? _self.routeColor : routeColor // ignore: cast_nullable_to_non_nullable
as String?,direction: freezed == direction ? _self.direction : direction // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}


}

// dart format on
