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

// dart format on
