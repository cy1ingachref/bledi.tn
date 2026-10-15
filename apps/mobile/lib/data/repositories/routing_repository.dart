import '../models/health.dart';
import '../models/itinerary.dart';
import '../models/line.dart';
import '../datasources/api_client.dart';

/// Calls the local multi-modal transit router.
///
/// The routing algorithm itself lives in the backend
/// (`services/transit`); this app only requests and renders it.
class RoutingDataSource {
  RoutingDataSource(this._client);

  final ApiClient _client;

  /// `GET /api/v1/route/transit`.
  ///
  /// Returns the envelope even when the backend reports an error, because the
  /// router signals "no route found" with HTTP 200 + an `error` field.
  Future<RouteResponse> fetchTransitRoute({
    required double startLat,
    required double startLon,
    required double endLat,
    required double endLon,
  }) async {
    final data = await _client.getJson(
      '/api/v1/route/transit',
      query: {
        'start_lat': startLat,
        'start_lon': startLon,
        'end_lat': endLat,
        'end_lon': endLon,
      },
    );

    if (data is! Map<String, dynamic>) {
      throw const ApiException('Unexpected transit response shape');
    }
    return RouteResponse.fromJson(data);
  }

  /// `GET /api/v1/route/plan` -- multi-objective, mode-filtered routing.
  ///
  /// [include] / [exclude] are the user's transport selection. They are sent
  /// straight through to the backend, which applies them INSIDE the search, so
  /// an excluded mode cannot appear in any leg. Both are comma-separated lists
  /// of user-facing mode names (`bus`, `metro`, `tram`, `train`, `louaj`).
  ///
  /// Returns [RoutePlan.fromJson]-shaped data. Throws [ApiException] on HTTP
  /// 400, which the backend returns for an unknown mode name -- the detail
  /// message lists the valid modes so the UI can show it.
  Future<Map<String, dynamic>> fetchRoutePlan({
    required double startLat,
    required double startLon,
    required double endLat,
    required double endLon,
    List<String>? include,
    List<String>? exclude,
    String objective = 'fastest',
    int? maxTransfers,
    double? maxWalkM,
    int maxItineraries = 3,
  }) async {
    final query = <String, dynamic>{
      'start_lat': startLat,
      'start_lon': startLon,
      'end_lat': endLat,
      'end_lon': endLon,
      'objective': objective,
      'max_itineraries': maxItineraries,
      if (include case final List<String> v? when v.isNotEmpty)
        'modes_include': v.join(','),
      if (exclude case final List<String> v? when v.isNotEmpty)
        'modes_exclude': v.join(','),
      if (maxTransfers case final int v?) 'max_transfers': v,
      if (maxWalkM case final double v?) 'max_walk_m': v,
    };
    final data = await _client.getJson('/api/v1/route/plan', query: query);
    if (data is! Map<String, dynamic>) {
      throw const ApiException('Unexpected route plan response shape');
    }
    return data;
  }

}

/// Transit routing access for the UI layer.
class RoutingRepository {
  RoutingRepository(this._remote);

  final RoutingDataSource _remote;

  /// Requests an itinerary between two coordinates.
  ///
  /// Returns `null` when the backend found no route; a thrown [ApiException]
  /// means the request itself failed.
  Future<RouteResponse> findTransitRoute({
    required double startLat,
    required double startLon,
    required double endLat,
    required double endLon,
  }) => _remote.fetchTransitRoute(
    startLat: startLat,
    startLon: startLon,
    endLat: endLat,
    endLon: endLon,
  );
}

/// Raw line/health calls.
class LinesDataSource {
  LinesDataSource(this._client);

  final ApiClient _client;

  Future<LinesResponse> fetchLines({
    int limit = 500,
    String? mode,
    String? operator,
  }) async {
    final data = await _client.getJson(
      '/api/v1/lines',
      query: {'limit': limit, 'mode': mode, 'operator': operator},
    );

    if (data is! Map<String, dynamic>) {
      throw const ApiException('Unexpected lines payload shape');
    }
    return LinesResponse.fromJson(data);
  }

  /// `GET /api/v1/health`.
  Future<Health> fetchHealth() async {
    final data = await _client.getJson('/api/v1/health');
    if (data is! Map<String, dynamic>) {
      throw const ApiException('Unexpected health payload shape');
    }
    return Health.fromJson(data);
  }
}