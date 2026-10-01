import '../models/health.dart';
import '../models/itinerary.dart';
import '../models/line.dart';
import '../datasources/api_client.dart';

/// Calls the local multi-modal transit router.
///
/// The routing algorithm itself lives in the backend
/// (`src/backend/app/routing.py`) — this app only requests and renders it.
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

  /// `GET /api/v1/stations/near`.
  Future<List<NearbyStation>> fetchNearbyStations({
    required double lat,
    required double lon,
    int limit = 10,
  }) async {
    final data = await _client.getJson(
      '/api/v1/stations/near',
      query: {'lat': lat, 'lon': lon, 'limit': limit},
    );

    if (data is! Map<String, dynamic>) return const <NearbyStation>[];
    final near = data['near'];
    if (near is! List) return const <NearbyStation>[];

    return near
        .whereType<Map<String, dynamic>>()
        .map(NearbyStation.fromJson)
        .toList(growable: false);
  }
}

/// Transit routing access for the UI layer.
class RoutingRepository {
  RoutingRepository(this._remote);

  final RoutingDataSource _remote;

  RouteResponse? _lastRoute;

  RouteResponse? get lastRoute => _lastRoute;

  /// Requests an itinerary between two coordinates.
  ///
  /// Returns `null` when the backend found no route; a thrown [ApiException]
  /// means the request itself failed.
  Future<RouteResponse> findTransitRoute({
    required double startLat,
    required double startLon,
    required double endLat,
    required double endLon,
  }) async {
    final response = await _remote.fetchTransitRoute(
      startLat: startLat,
      startLon: startLon,
      endLat: endLat,
      endLon: endLon,
    );
    _lastRoute = response;
    return response;
  }

  Future<List<NearbyStation>> nearbyStations({
    required double lat,
    required double lon,
    int limit = 10,
  }) => _remote.fetchNearbyStations(lat: lat, lon: lon, limit: limit);
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