import 'package:bledi_app/data/models/city.dart';
import 'package:bledi_app/data/models/station.dart';

import 'api_client.dart';

/// Parses backend payloads into [Station] models.
///
/// GeoJSON coordinates arrive as `[lon, lat]` (RFC 7946), unlike the transit
/// steps which use `[lat, lon]` — the conversion lives here so the rest of the
/// app only ever sees `lat`/`lon` fields.
class StationsDataSource {
  StationsDataSource(this._client);

  final ApiClient _client;

  /// `GET /api/v1/cities` — raw JSON, shaped by the repository into
  /// [CitiesResponse].
  Future<Map<String, dynamic>> fetchCities() async {
    final data = await _client.getJson('/api/v1/cities');
    if (data is! Map<String, dynamic>) {
      throw const ApiException('Unexpected cities payload shape');
    }
    return data;
  }

  /// `GET /api/v1/stations` — full FeatureCollection (1 729 features).
  Future<StationsPayload> fetchAll() async {
    final data = await _client.getJson('/api/v1/stations');
    if (data is! Map<String, dynamic>) {
      throw const ApiException('Unexpected stations payload shape');
    }

    final rawFeatures = data['features'];
    final features = rawFeatures is List ? rawFeatures : const <dynamic>[];

    final stations = <Station>[];
    for (final feature in features) {
      final station = _parseFeature(feature);
      if (station != null) stations.add(station);
    }

    final metadata =
        data['metadata'] is Map<String, dynamic>
        ? data['metadata'] as Map<String, dynamic>
        : const <String, dynamic>{};

    return StationsPayload(
      stations: stations,
      total: (metadata['total'] as num?)?.toInt() ?? stations.length,
    );
  }

  Station? _parseFeature(dynamic feature) {
    if (feature is! Map<String, dynamic>) return null;

    final properties =
        feature['properties'] is Map<String, dynamic>
        ? feature['properties'] as Map<String, dynamic>
        : const <String, dynamic>{};
    final geometry =
        feature['geometry'] is Map<String, dynamic>
        ? feature['geometry'] as Map<String, dynamic>
        : const <String, dynamic>{};
    final coordinates =
        geometry['coordinates'] is List ? geometry['coordinates'] as List : const [];

    if (coordinates.length < 2) return null;
    final lon = (coordinates[0] as num?)?.toDouble();
    final lat = (coordinates[1] as num?)?.toDouble();
    final id = properties['id'];
    if (id == null || lat == null || lon == null) return null;

    final rawLines = properties['lines'];
    final lines = <StationLineRef>[];
    if (rawLines is List) {
      for (final entry in rawLines) {
        if (entry is Map<String, dynamic>) {
          lines.add(
            StationLineRef(
              routeShortName: entry['route_short_name'] as String?,
              routeColor: entry['route_color'] as String?,
              direction: entry['direction'] as String?,
              routeId: entry['route_id'] as String?,
            ),
          );
        }
      }
    }

    final rawModes = properties['modes'];
    final modes = <String>[
      for (final m in (rawModes is List ? rawModes : const <dynamic>[]))
        if (m is String && m.isNotEmpty) m,
    ];

    return Station(
      id: id.toString(),
      name: (properties['name'] ?? id).toString(),
      lat: lat,
      lon: lon,
      mode: properties['mode'] as String?,
      modes: modes,
      city: properties['city'] as String?,
      operator: properties['operator'] as String?,
      source: properties['source'] as String?,
      nameEn: properties['name_en'] as String?,
      lines: lines,
    );
  }
}

/// All stations plus the backend's own count.
class StationsPayload {
  const StationsPayload({required this.stations, required this.total});

  final List<Station> stations;
  final int total;

  /// Distinct cities, with counts, ordered by size.
  ///
  /// Derived from the stations already in memory rather than a second request:
  /// `/api/v1/cities` exists for clients that want the list before downloading
  /// every stop, but once the stations are loaded this is free.
  List<City> get cities => citySummaries();

  /// Cities present in the loaded stations, largest first.
  ///
  /// Centres are the mean position of their stops, which is what the map
  /// zooms to when a city is picked.
  List<City> citySummaries() {
    final buckets = <String, List<Station>>{};
    for (final station in stations) {
      final city = station.city;
      if (city == null || city.isEmpty) continue;
      buckets.putIfAbsent(city, () => <Station>[]).add(station);
    }

    final out = <City>[];
    buckets.forEach((name, members) {
      var sumLat = 0.0;
      var sumLon = 0.0;
      final byMode = <String, int>{};
      for (final station in members) {
        sumLat += station.lat;
        sumLon += station.lon;
        final raw = station.mode ?? 'unknown';
        byMode[raw] = (byMode[raw] ?? 0) + 1;
      }
      out.add(
        City(
          name: name,
          lat: sumLat / members.length,
          lon: sumLon / members.length,
          stationCount: members.length,
          byMode: byMode,
        ),
      );
    });

    out.sort((a, b) => b.stationCount.compareTo(a.stationCount));
    return out;
  }
}

/// Station lookups backed by the API.
class StationsRepository {
  StationsRepository(this._remote);

  final StationsDataSource _remote;

  StationsPayload? _cache;
  Future<StationsPayload>? _inFlight;

  /// Cached stations, or `null` if never loaded.
  StationsPayload? get cached => _cache;

  bool get isCached => _cache != null;

  /// Returns all stations, fetching once and caching for the session.
  ///
  /// Concurrent callers share a single in-flight request so the 1 700-station
  /// payload is not fetched twice during app start.
  Future<StationsPayload> getAll({bool forceRefresh = false}) {
    if (!forceRefresh && _cache != null) return Future.value(_cache);
    final pending = _inFlight;
    if (!forceRefresh && pending != null) return pending;

    late final Future<StationsPayload> future;
    future = _remote.fetchAll().then((payload) {
      _cache = payload;
      return payload;
    }).whenComplete(() {
      if (identical(_inFlight, future)) _inFlight = null;
    });

    _inFlight = future;
    return future;
  }

  /// `GET /api/v1/cities` — cities with per-mode counts.
  ///
  /// Used by the city picker before all stations are loaded; once they are,
  /// [StationsPayload.citySummaries] serves the same data without a request.
  Future<CitiesResponse> fetchCities() async {
    final data = await _remote.fetchCities();
    return CitiesResponse.fromJson(data);
  }

  /// Client-side substring search over cached stations.
  ///
  /// The backend `/stations` endpoint has no `q` parameter in the deployed
  /// version, so search happens locally against the cached payload.
  List<Station> search(String query, {int limit = 30}) {
    final stations = _cache?.stations ?? const <Station>[];
    final needle = query.trim().toLowerCase();
    if (needle.isEmpty) return const <Station>[];

    final matches = <Station>[];
    for (final station in stations) {
      if (station.name.toLowerCase().contains(needle)) {
        matches.add(station);
        if (matches.length >= limit) break;
      }
    }
    return matches;
  }

  void clearCache() => _cache = null;
}