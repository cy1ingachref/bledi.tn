// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'line.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$Line {

 String get id; String? get number;@JsonKey(name: 'short_name') String? get shortName;@JsonKey(name: 'long_name') String? get longName; String get mode; String? get color;@JsonKey(name: 'route_id') String? get routeId;@JsonKey(name: 'stops_count') int get stopsCount;
/// Create a copy of Line
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$LineCopyWith<Line> get copyWith => _$LineCopyWithImpl<Line>(this as Line, _$identity);

  /// Serializes this Line to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as Line;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is Line&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.number, _this.number) || other.number == _this.number)&&(identical(other.shortName, _this.shortName) || other.shortName == _this.shortName)&&(identical(other.longName, _this.longName) || other.longName == _this.longName)&&(identical(other.mode, _this.mode) || other.mode == _this.mode)&&(identical(other.color, _this.color) || other.color == _this.color)&&(identical(other.routeId, _this.routeId) || other.routeId == _this.routeId)&&(identical(other.stopsCount, _this.stopsCount) || other.stopsCount == _this.stopsCount));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as Line;
  return Object.hash(runtimeType,_this.id,_this.number,_this.shortName,_this.longName,_this.mode,_this.color,_this.routeId,_this.stopsCount);
}

@override
String toString() {
  final _this = this as Line;
  return 'Line(id: ${_this.id}, number: ${_this.number}, shortName: ${_this.shortName}, longName: ${_this.longName}, mode: ${_this.mode}, color: ${_this.color}, routeId: ${_this.routeId}, stopsCount: ${_this.stopsCount})';
}


}

/// @nodoc
abstract mixin class $LineCopyWith<$Res>  {
  factory $LineCopyWith(Line value, $Res Function(Line) _then) = _$LineCopyWithImpl;
@useResult
$Res call({
 String id, String? number,@JsonKey(name: 'short_name') String? shortName,@JsonKey(name: 'long_name') String? longName, String mode, String? color,@JsonKey(name: 'route_id') String? routeId,@JsonKey(name: 'stops_count') int stopsCount
});




}
/// @nodoc
class _$LineCopyWithImpl<$Res>
    implements $LineCopyWith<$Res> {
  _$LineCopyWithImpl(this._self, this._then);

  final Line _self;
  final $Res Function(Line) _then;

/// Create a copy of Line
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? number = freezed,Object? shortName = freezed,Object? longName = freezed,Object? mode = null,Object? color = freezed,Object? routeId = freezed,Object? stopsCount = null,}) {
  return _then(Line(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,number: freezed == number ? _self.number : number // ignore: cast_nullable_to_non_nullable
as String?,shortName: freezed == shortName ? _self.shortName : shortName // ignore: cast_nullable_to_non_nullable
as String?,longName: freezed == longName ? _self.longName : longName // ignore: cast_nullable_to_non_nullable
as String?,mode: null == mode ? _self.mode : mode // ignore: cast_nullable_to_non_nullable
as String,color: freezed == color ? _self.color : color // ignore: cast_nullable_to_non_nullable
as String?,routeId: freezed == routeId ? _self.routeId : routeId // ignore: cast_nullable_to_non_nullable
as String?,stopsCount: null == stopsCount ? _self.stopsCount : stopsCount // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [Line].
extension LinePatterns on Line {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _Line value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _Line() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _Line value)  $default,){
final _that = this;
switch (_that) {
case _Line():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _Line value)?  $default,){
final _that = this;
switch (_that) {
case _Line() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String? number, @JsonKey(name: 'short_name')  String? shortName, @JsonKey(name: 'long_name')  String? longName,  String mode,  String? color, @JsonKey(name: 'route_id')  String? routeId, @JsonKey(name: 'stops_count')  int stopsCount)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _Line() when $default != null:
return $default(_that.id,_that.number,_that.shortName,_that.longName,_that.mode,_that.color,_that.routeId,_that.stopsCount);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String? number, @JsonKey(name: 'short_name')  String? shortName, @JsonKey(name: 'long_name')  String? longName,  String mode,  String? color, @JsonKey(name: 'route_id')  String? routeId, @JsonKey(name: 'stops_count')  int stopsCount)  $default,) {final _that = this;
switch (_that) {
case _Line():
return $default(_that.id,_that.number,_that.shortName,_that.longName,_that.mode,_that.color,_that.routeId,_that.stopsCount);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String? number, @JsonKey(name: 'short_name')  String? shortName, @JsonKey(name: 'long_name')  String? longName,  String mode,  String? color, @JsonKey(name: 'route_id')  String? routeId, @JsonKey(name: 'stops_count')  int stopsCount)?  $default,) {final _that = this;
switch (_that) {
case _Line() when $default != null:
return $default(_that.id,_that.number,_that.shortName,_that.longName,_that.mode,_that.color,_that.routeId,_that.stopsCount);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _Line extends Line {
  const _Line({required this.id, this.number, @JsonKey(name: 'short_name') this.shortName, @JsonKey(name: 'long_name') this.longName, this.mode = 'bus', this.color, @JsonKey(name: 'route_id') this.routeId, @JsonKey(name: 'stops_count') this.stopsCount = 0}): super._();
  factory _Line.fromJson(Map<String, dynamic> json) => _$LineFromJson(json);

@override final  String id;
@override final  String? number;
@override@JsonKey(name: 'short_name') final  String? shortName;
@override@JsonKey(name: 'long_name') final  String? longName;
@override@JsonKey() final  String mode;
@override final  String? color;
@override@JsonKey(name: 'route_id') final  String? routeId;
@override@JsonKey(name: 'stops_count') final  int stopsCount;

/// Create a copy of Line
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$LineCopyWith<_Line> get copyWith => __$LineCopyWithImpl<_Line>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$LineToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _Line&&(identical(other.id, id) || other.id == id)&&(identical(other.number, number) || other.number == number)&&(identical(other.shortName, shortName) || other.shortName == shortName)&&(identical(other.longName, longName) || other.longName == longName)&&(identical(other.mode, mode) || other.mode == mode)&&(identical(other.color, color) || other.color == color)&&(identical(other.routeId, routeId) || other.routeId == routeId)&&(identical(other.stopsCount, stopsCount) || other.stopsCount == stopsCount));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,id,number,shortName,longName,mode,color,routeId,stopsCount);
}

@override
String toString() {
    return 'Line(id: $id, number: $number, shortName: $shortName, longName: $longName, mode: $mode, color: $color, routeId: $routeId, stopsCount: $stopsCount)';
}


}

/// @nodoc
abstract mixin class _$LineCopyWith<$Res> implements $LineCopyWith<$Res> {
  factory _$LineCopyWith(_Line value, $Res Function(_Line) _then) = __$LineCopyWithImpl;
@override @useResult
$Res call({
 String id, String? number,@JsonKey(name: 'short_name') String? shortName,@JsonKey(name: 'long_name') String? longName, String mode, String? color,@JsonKey(name: 'route_id') String? routeId,@JsonKey(name: 'stops_count') int stopsCount
});




}
/// @nodoc
class __$LineCopyWithImpl<$Res>
    implements _$LineCopyWith<$Res> {
  __$LineCopyWithImpl(this._self, this._then);

  final _Line _self;
  final $Res Function(_Line) _then;

/// Create a copy of Line
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? number = freezed,Object? shortName = freezed,Object? longName = freezed,Object? mode = null,Object? color = freezed,Object? routeId = freezed,Object? stopsCount = null,}) {
  return _then(_Line(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,number: freezed == number ? _self.number : number // ignore: cast_nullable_to_non_nullable
as String?,shortName: freezed == shortName ? _self.shortName : shortName // ignore: cast_nullable_to_non_nullable
as String?,longName: freezed == longName ? _self.longName : longName // ignore: cast_nullable_to_non_nullable
as String?,mode: null == mode ? _self.mode : mode // ignore: cast_nullable_to_non_nullable
as String,color: freezed == color ? _self.color : color // ignore: cast_nullable_to_non_nullable
as String?,routeId: freezed == routeId ? _self.routeId : routeId // ignore: cast_nullable_to_non_nullable
as String?,stopsCount: null == stopsCount ? _self.stopsCount : stopsCount // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}


/// @nodoc
mixin _$LinesResponse {

 List<Line> get lines; int get count;
/// Create a copy of LinesResponse
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$LinesResponseCopyWith<LinesResponse> get copyWith => _$LinesResponseCopyWithImpl<LinesResponse>(this as LinesResponse, _$identity);

  /// Serializes this LinesResponse to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as LinesResponse;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is LinesResponse&&const DeepCollectionEquality().equals(other.lines, _this.lines)&&(identical(other.count, _this.count) || other.count == _this.count));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as LinesResponse;
  return Object.hash(runtimeType,const DeepCollectionEquality().hash(_this.lines),_this.count);
}

@override
String toString() {
  final _this = this as LinesResponse;
  return 'LinesResponse(lines: ${_this.lines}, count: ${_this.count})';
}


}

/// @nodoc
abstract mixin class $LinesResponseCopyWith<$Res>  {
  factory $LinesResponseCopyWith(LinesResponse value, $Res Function(LinesResponse) _then) = _$LinesResponseCopyWithImpl;
@useResult
$Res call({
 List<Line> lines, int count
});




}
/// @nodoc
class _$LinesResponseCopyWithImpl<$Res>
    implements $LinesResponseCopyWith<$Res> {
  _$LinesResponseCopyWithImpl(this._self, this._then);

  final LinesResponse _self;
  final $Res Function(LinesResponse) _then;

/// Create a copy of LinesResponse
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? lines = null,Object? count = null,}) {
  return _then(LinesResponse(
lines: null == lines ? _self.lines : lines // ignore: cast_nullable_to_non_nullable
as List<Line>,count: null == count ? _self.count : count // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [LinesResponse].
extension LinesResponsePatterns on LinesResponse {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _LinesResponse value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _LinesResponse() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _LinesResponse value)  $default,){
final _that = this;
switch (_that) {
case _LinesResponse():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _LinesResponse value)?  $default,){
final _that = this;
switch (_that) {
case _LinesResponse() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( List<Line> lines,  int count)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _LinesResponse() when $default != null:
return $default(_that.lines,_that.count);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( List<Line> lines,  int count)  $default,) {final _that = this;
switch (_that) {
case _LinesResponse():
return $default(_that.lines,_that.count);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( List<Line> lines,  int count)?  $default,) {final _that = this;
switch (_that) {
case _LinesResponse() when $default != null:
return $default(_that.lines,_that.count);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _LinesResponse implements LinesResponse {
  const _LinesResponse({ List<Line> lines = const <Line>[], this.count = 0}): _lines = lines;
  factory _LinesResponse.fromJson(Map<String, dynamic> json) => _$LinesResponseFromJson(json);

 final  List<Line> _lines;
@override@JsonKey() List<Line> get lines {
  if (_lines is EqualUnmodifiableListView) return _lines;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_lines);
}

@override@JsonKey() final  int count;

/// Create a copy of LinesResponse
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$LinesResponseCopyWith<_LinesResponse> get copyWith => __$LinesResponseCopyWithImpl<_LinesResponse>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$LinesResponseToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _LinesResponse&&const DeepCollectionEquality().equals(other.lines, _lines)&&(identical(other.count, count) || other.count == count));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,const DeepCollectionEquality().hash(_lines),count);
}

@override
String toString() {
    return 'LinesResponse(lines: $lines, count: $count)';
}


}

/// @nodoc
abstract mixin class _$LinesResponseCopyWith<$Res> implements $LinesResponseCopyWith<$Res> {
  factory _$LinesResponseCopyWith(_LinesResponse value, $Res Function(_LinesResponse) _then) = __$LinesResponseCopyWithImpl;
@override @useResult
$Res call({
 List<Line> lines, int count
});




}
/// @nodoc
class __$LinesResponseCopyWithImpl<$Res>
    implements _$LinesResponseCopyWith<$Res> {
  __$LinesResponseCopyWithImpl(this._self, this._then);

  final _LinesResponse _self;
  final $Res Function(_LinesResponse) _then;

/// Create a copy of LinesResponse
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? lines = null,Object? count = null,}) {
  return _then(_LinesResponse(
lines: null == lines ? _self._lines : lines // ignore: cast_nullable_to_non_nullable
as List<Line>,count: null == count ? _self.count : count // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

// dart format on
