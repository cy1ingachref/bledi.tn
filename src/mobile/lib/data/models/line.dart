import 'package:freezed_annotation/freezed_annotation.dart';

part 'line.freezed.dart';
part 'line.g.dart';

/// A transport line summary.
///
/// Sourced from `GET /api/v1/lines` (`{lines: [...], count: n}`), whose
/// fields are snake_case on the wire.
@freezed
abstract class Line with _$Line {
  const Line._();

  const factory Line({
    required String id,
    String? number,
    @JsonKey(name: 'short_name') String? shortName,
    @JsonKey(name: 'long_name') String? longName,
    @Default('bus') String mode,
    String? color,
    @JsonKey(name: 'route_id') String? routeId,
    @JsonKey(name: 'stops_count') @Default(0) int stopsCount,
  }) = _Line;

  factory Line.fromJson(Map<String, dynamic> json) => _$LineFromJson(json);

  /// Best available human-readable name.
  String get displayName {
    for (final candidate in [shortName, longName, number, routeId]) {
      if (candidate != null && candidate.trim().isNotEmpty) {
        return candidate.trim();
      }
    }
    return id;
  }

  /// Line colour as `#RRGGBB`, or `null` when the backend omits it or sends
  /// something unparseable.
  ///
  /// The seed stores colours without a leading `#` (e.g. `"829EC0"`), so both
  /// forms are accepted.
  String? get hexColor {
    final value = color?.trim();
    if (value == null || value.isEmpty) return null;
    final withHash = value.startsWith('#') ? value : '#$value';
    return RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(withHash) ? withHash : null;
  }
}

/// Wrapper for the `/api/v1/lines` list envelope.
@freezed
abstract class LinesResponse with _$LinesResponse {
  const factory LinesResponse({
    @Default(<Line>[]) List<Line> lines,
    @Default(0) int count,
  }) = _LinesResponse;

  factory LinesResponse.fromJson(Map<String, dynamic> json) =>
      _$LinesResponseFromJson(json);
}