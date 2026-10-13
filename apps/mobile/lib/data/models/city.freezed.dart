// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'city.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$City {

 String get name; double get lat; double get lon;@JsonKey(name: 'station_count') int get stationCount;@JsonKey(name: 'by_mode') Map<String, int> get byMode;
/// Create a copy of City
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$CityCopyWith<City> get copyWith => _$CityCopyWithImpl<City>(this as City, _$identity);

  /// Serializes this City to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as City;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is City&&(identical(other.name, _this.name) || other.name == _this.name)&&(identical(other.lat, _this.lat) || other.lat == _this.lat)&&(identical(other.lon, _this.lon) || other.lon == _this.lon)&&(identical(other.stationCount, _this.stationCount) || other.stationCount == _this.stationCount)&&const DeepCollectionEquality().equals(other.byMode, _this.byMode));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as City;
  return Object.hash(runtimeType,_this.name,_this.lat,_this.lon,_this.stationCount,const DeepCollectionEquality().hash(_this.byMode));
}

@override
String toString() {
  final _this = this as City;
  return 'City(name: ${_this.name}, lat: ${_this.lat}, lon: ${_this.lon}, stationCount: ${_this.stationCount}, byMode: ${_this.byMode})';
}


}

/// @nodoc
abstract mixin class $CityCopyWith<$Res>  {
  factory $CityCopyWith(City value, $Res Function(City) _then) = _$CityCopyWithImpl;
@useResult
$Res call({
 String name, double lat, double lon,@JsonKey(name: 'station_count') int stationCount,@JsonKey(name: 'by_mode') Map<String, int> byMode
});




}
/// @nodoc
class _$CityCopyWithImpl<$Res>
    implements $CityCopyWith<$Res> {
  _$CityCopyWithImpl(this._self, this._then);

  final City _self;
  final $Res Function(City) _then;

/// Create a copy of City
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? name = null,Object? lat = null,Object? lon = null,Object? stationCount = null,Object? byMode = null,}) {
  return _then(City(
name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,lat: null == lat ? _self.lat : lat // ignore: cast_nullable_to_non_nullable
as double,lon: null == lon ? _self.lon : lon // ignore: cast_nullable_to_non_nullable
as double,stationCount: null == stationCount ? _self.stationCount : stationCount // ignore: cast_nullable_to_non_nullable
as int,byMode: null == byMode ? _self.byMode : byMode // ignore: cast_nullable_to_non_nullable
as Map<String, int>,
  ));
}

}


/// Adds pattern-matching-related methods to [City].
extension CityPatterns on City {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _City value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _City() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _City value)  $default,){
final _that = this;
switch (_that) {
case _City():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _City value)?  $default,){
final _that = this;
switch (_that) {
case _City() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String name,  double lat,  double lon, @JsonKey(name: 'station_count')  int stationCount, @JsonKey(name: 'by_mode')  Map<String, int> byMode)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _City() when $default != null:
return $default(_that.name,_that.lat,_that.lon,_that.stationCount,_that.byMode);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String name,  double lat,  double lon, @JsonKey(name: 'station_count')  int stationCount, @JsonKey(name: 'by_mode')  Map<String, int> byMode)  $default,) {final _that = this;
switch (_that) {
case _City():
return $default(_that.name,_that.lat,_that.lon,_that.stationCount,_that.byMode);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String name,  double lat,  double lon, @JsonKey(name: 'station_count')  int stationCount, @JsonKey(name: 'by_mode')  Map<String, int> byMode)?  $default,) {final _that = this;
switch (_that) {
case _City() when $default != null:
return $default(_that.name,_that.lat,_that.lon,_that.stationCount,_that.byMode);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _City extends City {
  const _City({required this.name, required this.lat, required this.lon, @JsonKey(name: 'station_count') required this.stationCount, @JsonKey(name: 'by_mode')  Map<String, int> byMode = const <String, int>{}}): _byMode = byMode,super._();
  factory _City.fromJson(Map<String, dynamic> json) => _$CityFromJson(json);

@override final  String name;
@override final  double lat;
@override final  double lon;
@override@JsonKey(name: 'station_count') final  int stationCount;
 final  Map<String, int> _byMode;
@override@JsonKey(name: 'by_mode') Map<String, int> get byMode {
  if (_byMode is EqualUnmodifiableMapView) return _byMode;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableMapView(_byMode);
}


/// Create a copy of City
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$CityCopyWith<_City> get copyWith => __$CityCopyWithImpl<_City>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$CityToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _City&&(identical(other.name, name) || other.name == name)&&(identical(other.lat, lat) || other.lat == lat)&&(identical(other.lon, lon) || other.lon == lon)&&(identical(other.stationCount, stationCount) || other.stationCount == stationCount)&&const DeepCollectionEquality().equals(other.byMode, _byMode));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,name,lat,lon,stationCount,const DeepCollectionEquality().hash(_byMode));
}

@override
String toString() {
    return 'City(name: $name, lat: $lat, lon: $lon, stationCount: $stationCount, byMode: $byMode)';
}


}

/// @nodoc
abstract mixin class _$CityCopyWith<$Res> implements $CityCopyWith<$Res> {
  factory _$CityCopyWith(_City value, $Res Function(_City) _then) = __$CityCopyWithImpl;
@override @useResult
$Res call({
 String name, double lat, double lon,@JsonKey(name: 'station_count') int stationCount,@JsonKey(name: 'by_mode') Map<String, int> byMode
});




}
/// @nodoc
class __$CityCopyWithImpl<$Res>
    implements _$CityCopyWith<$Res> {
  __$CityCopyWithImpl(this._self, this._then);

  final _City _self;
  final $Res Function(_City) _then;

/// Create a copy of City
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? name = null,Object? lat = null,Object? lon = null,Object? stationCount = null,Object? byMode = null,}) {
  return _then(_City(
name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,lat: null == lat ? _self.lat : lat // ignore: cast_nullable_to_non_nullable
as double,lon: null == lon ? _self.lon : lon // ignore: cast_nullable_to_non_nullable
as double,stationCount: null == stationCount ? _self.stationCount : stationCount // ignore: cast_nullable_to_non_nullable
as int,byMode: null == byMode ? _self._byMode : byMode // ignore: cast_nullable_to_non_nullable
as Map<String, int>,
  ));
}


}


/// @nodoc
mixin _$CitiesResponse {

 List<City> get cities; int get count;
/// Create a copy of CitiesResponse
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$CitiesResponseCopyWith<CitiesResponse> get copyWith => _$CitiesResponseCopyWithImpl<CitiesResponse>(this as CitiesResponse, _$identity);

  /// Serializes this CitiesResponse to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as CitiesResponse;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is CitiesResponse&&const DeepCollectionEquality().equals(other.cities, _this.cities)&&(identical(other.count, _this.count) || other.count == _this.count));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as CitiesResponse;
  return Object.hash(runtimeType,const DeepCollectionEquality().hash(_this.cities),_this.count);
}

@override
String toString() {
  final _this = this as CitiesResponse;
  return 'CitiesResponse(cities: ${_this.cities}, count: ${_this.count})';
}


}

/// @nodoc
abstract mixin class $CitiesResponseCopyWith<$Res>  {
  factory $CitiesResponseCopyWith(CitiesResponse value, $Res Function(CitiesResponse) _then) = _$CitiesResponseCopyWithImpl;
@useResult
$Res call({
 List<City> cities, int count
});




}
/// @nodoc
class _$CitiesResponseCopyWithImpl<$Res>
    implements $CitiesResponseCopyWith<$Res> {
  _$CitiesResponseCopyWithImpl(this._self, this._then);

  final CitiesResponse _self;
  final $Res Function(CitiesResponse) _then;

/// Create a copy of CitiesResponse
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? cities = null,Object? count = null,}) {
  return _then(CitiesResponse(
cities: null == cities ? _self.cities : cities // ignore: cast_nullable_to_non_nullable
as List<City>,count: null == count ? _self.count : count // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [CitiesResponse].
extension CitiesResponsePatterns on CitiesResponse {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _CitiesResponse value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _CitiesResponse() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _CitiesResponse value)  $default,){
final _that = this;
switch (_that) {
case _CitiesResponse():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _CitiesResponse value)?  $default,){
final _that = this;
switch (_that) {
case _CitiesResponse() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( List<City> cities,  int count)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _CitiesResponse() when $default != null:
return $default(_that.cities,_that.count);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( List<City> cities,  int count)  $default,) {final _that = this;
switch (_that) {
case _CitiesResponse():
return $default(_that.cities,_that.count);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( List<City> cities,  int count)?  $default,) {final _that = this;
switch (_that) {
case _CitiesResponse() when $default != null:
return $default(_that.cities,_that.count);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _CitiesResponse implements CitiesResponse {
  const _CitiesResponse({ List<City> cities = const <City>[], this.count = 0}): _cities = cities;
  factory _CitiesResponse.fromJson(Map<String, dynamic> json) => _$CitiesResponseFromJson(json);

 final  List<City> _cities;
@override@JsonKey() List<City> get cities {
  if (_cities is EqualUnmodifiableListView) return _cities;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_cities);
}

@override@JsonKey() final  int count;

/// Create a copy of CitiesResponse
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$CitiesResponseCopyWith<_CitiesResponse> get copyWith => __$CitiesResponseCopyWithImpl<_CitiesResponse>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$CitiesResponseToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _CitiesResponse&&const DeepCollectionEquality().equals(other.cities, _cities)&&(identical(other.count, count) || other.count == count));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,const DeepCollectionEquality().hash(_cities),count);
}

@override
String toString() {
    return 'CitiesResponse(cities: $cities, count: $count)';
}


}

/// @nodoc
abstract mixin class _$CitiesResponseCopyWith<$Res> implements $CitiesResponseCopyWith<$Res> {
  factory _$CitiesResponseCopyWith(_CitiesResponse value, $Res Function(_CitiesResponse) _then) = __$CitiesResponseCopyWithImpl;
@override @useResult
$Res call({
 List<City> cities, int count
});




}
/// @nodoc
class __$CitiesResponseCopyWithImpl<$Res>
    implements _$CitiesResponseCopyWith<$Res> {
  __$CitiesResponseCopyWithImpl(this._self, this._then);

  final _CitiesResponse _self;
  final $Res Function(_CitiesResponse) _then;

/// Create a copy of CitiesResponse
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? cities = null,Object? count = null,}) {
  return _then(_CitiesResponse(
cities: null == cities ? _self._cities : cities // ignore: cast_nullable_to_non_nullable
as List<City>,count: null == count ? _self.count : count // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

// dart format on
