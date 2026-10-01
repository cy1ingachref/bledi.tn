import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/constants.dart';
import '../core/utils/state.dart';
import '../data/datasources/api_client.dart';
import '../data/datasources/stations_data_source.dart';
import '../data/models/city.dart';
import '../data/models/health.dart';
import '../data/models/itinerary.dart';
import '../data/models/station.dart';
import '../data/repositories/routing_repository.dart';

/// Persisted backend base URL. Editable from Settings, so the app can be
/// pointed at a LAN host or staging deployment without a rebuild.
class BaseUrlNotifier extends Notifier<String> {
  static const _prefsKey = 'bledi.api_base_url';

  @override
  String build() {
    unawaited(_restore());
    return AppConstants.apiBaseUrl;
  }

  Future<void> _restore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final stored = prefs.getString(_prefsKey);
      if (stored != null && stored.isNotEmpty && stored != state) {
        state = stored;
      }
    } catch (e) {
      debugPrint('Failed to restore base URL: $e');
    }
  }

  /// Updates and persists the URL. Rebuilds [apiClientProvider] automatically
  /// since it watches this provider.
  Future<void> setBaseUrl(String url) async {
    final cleaned = _normalize(url);
    if (cleaned.isEmpty || cleaned == state) return;
    state = cleaned;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefsKey, cleaned);
    } catch (e) {
      debugPrint('Failed to persist base URL: $e');
    }
  }

  static String _normalize(String url) {
    var cleaned = url.trim();
    if (cleaned.isEmpty) return '';
    if (!cleaned.startsWith('http://') && !cleaned.startsWith('https://')) {
      cleaned = 'http://$cleaned';
    }
    while (cleaned.endsWith('/')) {
      cleaned = cleaned.substring(0, cleaned.length - 1);
    }
    return cleaned;
  }
}

final baseUrlProvider =
    NotifierProvider<BaseUrlNotifier, String>(BaseUrlNotifier.new);

/// The single [ApiClient]; rebuilt whenever the base URL changes.
final apiClientProvider = Provider<ApiClient>((ref) {
  final baseUrl = ref.watch(baseUrlProvider);
  final client = ApiClient(baseUrl: baseUrl);
  ref.onDispose(client.close);
  return client;
});

final stationsDataSourceProvider = Provider<StationsDataSource>((ref) {
  return StationsDataSource(ref.watch(apiClientProvider));
});

final routingDataSourceProvider = Provider<RoutingDataSource>((ref) {
  return RoutingDataSource(ref.watch(apiClientProvider));
});

final linesDataSourceProvider = Provider<LinesDataSource>((ref) {
  return LinesDataSource(ref.watch(apiClientProvider));
});

final stationsRepositoryProvider = Provider<StationsRepository>((ref) {
  return StationsRepository(ref.watch(stationsDataSourceProvider));
});

final routingRepositoryProvider = Provider<RoutingRepository>((ref) {
  return RoutingRepository(ref.watch(routingDataSourceProvider));
});

/// All stations, loaded once and cached by [StationsRepository].
///
/// Deliberately NOT autoDispose: the station list is the app's base dataset and
/// re-fetching 1 711 records every time Home rebuilds would be wasteful.
final stationsProvider = FutureProvider<StationsPayload>((ref) async {
  return ref.watch(stationsRepositoryProvider).getAll();
});

/// Backend health, checked on demand from Settings / Home.
final healthProvider = FutureProvider.autoDispose<Health>((ref) async {
  return ref.watch(linesDataSourceProvider).fetchHealth();
});

/// Client-side station search query.
///
/// Riverpod 3 removed `StateProvider`, so this is a plain `Notifier`.
class StationSearchQueryNotifier extends Notifier<String> {
  @override
  String build() => '';

  void setQuery(String value) => state = value;

  void clear() => state = '';
}

final stationSearchQueryProvider =
    NotifierProvider<StationSearchQueryNotifier, String>(
      StationSearchQueryNotifier.new,
    );

/// Search results derived from the cached station list.
final stationSearchResultsProvider = Provider<List<Station>>((ref) {
  final query = ref.watch(stationSearchQueryProvider);
  if (query.trim().isEmpty) return const <Station>[];
  final repository = ref.watch(stationsRepositoryProvider);
  return repository.search(query);
});

// ── Routing state ──────────────────────────────────────────────────────────

/// Which endpoint the user is currently editing on the map.
enum SelectionTarget { origin, destination }

/// Current origin / destination selection and the active picker target.
class RouteSelection {
  const RouteSelection({
    this.origin,
    this.destination,
    this.target = SelectionTarget.origin,
  });

  final MapPoint? origin;
  final MapPoint? destination;
  final SelectionTarget target;

  bool get hasBoth => origin != null && destination != null;

  RouteSelection copyWith({
    MapPoint? origin,
    MapPoint? destination,
    SelectionTarget? target,
    bool clearOrigin = false,
    bool clearDestination = false,
  }) {
    return RouteSelection(
      origin: clearOrigin ? null : (origin ?? this.origin),
      destination: clearDestination ? null : (destination ?? this.destination),
      target: target ?? this.target,
    );
  }

  /// Swaps origin and destination.
  RouteSelection swapped() => RouteSelection(
    origin: destination,
    destination: origin,
    target: target == SelectionTarget.origin
        ? SelectionTarget.destination
        : SelectionTarget.origin,
  );

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RouteSelection &&
          other.origin == origin &&
          other.destination == destination &&
          other.target == target;

  @override
  int get hashCode => Object.hash(origin, destination, target);
}

class RouteSelectionNotifier extends Notifier<RouteSelection> {
  @override
  RouteSelection build() => const RouteSelection();

  void setOrigin(MapPoint point) =>
      state = state.copyWith(origin: point, target: SelectionTarget.destination);

  void setDestination(MapPoint point) =>
      state = state.copyWith(destination: point, target: SelectionTarget.origin);

  void swap() => state = state.swapped();

  void clear() => state = const RouteSelection();

  void setTarget(SelectionTarget target) =>
      state = RouteSelection(
        origin: state.origin,
        destination: state.destination,
        target: target,
      );
}

final routeSelectionProvider =
    NotifierProvider<RouteSelectionNotifier, RouteSelection>(
      RouteSelectionNotifier.new,
    );

/// Result of the last routing request.
class RoutingResult {
  const RoutingResult({this.itinerary, this.errorMessage, this.isLoading = false});

  final Itinerary? itinerary;
  final String? errorMessage;
  final bool isLoading;

  bool get hasItinerary => itinerary != null && itinerary!.steps.isNotEmpty;
  bool get hasError => errorMessage != null;

  RoutingResult copyWith({Itinerary? itinerary, String? errorMessage, bool? isLoading, bool clearError = false}) {
    return RoutingResult(
      itinerary: itinerary ?? this.itinerary,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

/// Drives `/api/v1/route/transit` for the selected origin/destination.
class RoutingNotifier extends Notifier<RoutingResult> {
  @override
  RoutingResult build() => const RoutingResult();

  /// Requests a route for the current selection.
  ///
  /// Returns false when the selection is incomplete or the request failed.
  Future<bool> routeCurrentSelection() async {
    final selection = ref.read(routeSelectionProvider);
    final origin = selection.origin;
    final destination = selection.destination;
    if (origin == null || destination == null) return false;

    state = const RoutingResult(isLoading: true);
    try {
      final response = await ref.read(routingRepositoryProvider).findTransitRoute(
        startLat: origin.lat,
        startLon: origin.lon,
        endLat: destination.lat,
        endLon: destination.lon,
      );

      if (response.hasError) {
        state = RoutingResult(errorMessage: response.error);
        return false;
      }

      final itinerary = response.primary;
      if (itinerary == null || itinerary.steps.isEmpty) {
        state = const RoutingResult(errorMessage: 'no_route');
        return false;
      }

      // The router always answers, degrading to a taxi (or, for an identical
      // origin/destination pair, a 0 m walk). A degenerate route is not a
      // usable itinerary, so it is reported as "no route" instead of drawing
      // an invisible polyline and a misleading "0 min" summary.
      final isDegenerate =
          itinerary.allPoints.every((p) => p == itinerary.steps.first.start) ||
          itinerary.durationMin <= 0;
      if (isDegenerate) {
        state = const RoutingResult(errorMessage: 'no_route');
        return false;
      }

      state = RoutingResult(itinerary: itinerary);
      return true;
    } on Object catch (e) {
      state = RoutingResult(errorMessage: _message(e));
      return false;
    }
  }

  void clear() => state = const RoutingResult();

  static String _message(Object error) {
    if (error is ApiException) return error.message;
    return error.toString();
  }
}

final routingProvider =
    NotifierProvider<RoutingNotifier, RoutingResult>(RoutingNotifier.new);

/// Current map zoom level.
///
/// The station overlay needs this to decide between clustered and individual
/// dots. It is fed from the map's position callback rather than read back from
/// a controller, so it stays in sync during animated camera moves.
class MapZoomNotifier extends Notifier<double> {
  @override
  double build() => AppConstants.tunisZoom;

  void update(double zoom) {
    if ((zoom - state).abs() < 0.01) return;
    state = zoom;
  }
}

final mapZoomProvider =
    NotifierProvider<MapZoomNotifier, double>(MapZoomNotifier.new);

/// Whether the station/stop overlay is visible.
class StationOverlayNotifier extends Notifier<bool> {
  @override
  bool build() => true;

  void toggle() => state = !state;
  void set(bool value) => state = value;
}

final stationOverlayProvider =
    NotifierProvider<StationOverlayNotifier, bool>(StationOverlayNotifier.new);

/// Which transport categories the map shows.
class ModeFilterNotifier extends Notifier<Set<TransportMode>> {
  @override
  Set<TransportMode> build() => {
    TransportMode.rail,
    TransportMode.bus,
    TransportMode.louage,
  };

  void toggle(TransportMode mode) {
    final next = Set<TransportMode>.from(state);
    if (!next.remove(mode)) next.add(mode);
    // Never allow an empty selection: the map would show nothing at all.
    state = next.isEmpty ? {mode} : next;
  }

  void showAll() => state = {
    TransportMode.rail,
    TransportMode.bus,
    TransportMode.louage,
  };
}

final modeFilterProvider =
    NotifierProvider<ModeFilterNotifier, Set<TransportMode>>(
      ModeFilterNotifier.new,
    );

/// The city whose stations are currently shown, or null for the whole country.
class SelectedCityNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String? city) => state = city;
}

final selectedCityProvider =
    NotifierProvider<SelectedCityNotifier, String?>(SelectedCityNotifier.new);

/// Cities derived from the loaded stations, largest first.
///
/// Computed from data already in memory, so it is available the moment the
/// station payload resolves and never needs its own request.
final citiesProvider = Provider<List<City>>((ref) {
  final payload = ref.watch(stationsProvider).asData?.value;
  if (payload == null) return const <City>[];
  return payload.citySummaries();
});

/// The user's GPS position, requested lazily.
class UserLocation {
  const UserLocation({this.lat, this.lon, this.isLoading = false, this.error});

  final double? lat;
  final double? lon;
  final bool isLoading;
  final String? error;

  bool get hasFix => lat != null && lon != null;
}

/// Requests the device GPS fix via geolocator.
///
/// Permission and platform failures are surfaced as [UserLocation.error]
/// rather than thrown, because every caller is UI code.
class UserLocationNotifier extends Notifier<UserLocation> {
  @override
  UserLocation build() => const UserLocation();

  Future<void> refresh() async {
    state = const UserLocation(isLoading: true);
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        state = const UserLocation(error: 'location_disabled');
        return;
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        state = const UserLocation(error: 'permission_denied');
        return;
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
      state = UserLocation(
        lat: position.latitude,
        lon: position.longitude,
      );
    } on Object catch (e) {
      debugPrint('Location request failed: $e');
      state = UserLocation(error: 'unavailable');
    }
  }
}

final userLocationProvider =
    NotifierProvider<UserLocationNotifier, UserLocation>(UserLocationNotifier.new);