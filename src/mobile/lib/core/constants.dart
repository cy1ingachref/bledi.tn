/// Global app-wide constants.
///
/// The API base URL is compile-time configurable so the same binary can point
/// at a local backend, a LAN host, or a staging deployment:
///
///   flutter run --dart-define=BLED_API_BASE=http://192.168.1.20:8000
library;

class AppConstants {
  const AppConstants._();

  /// Base URL of the BLEDI.TN FastAPI backend.
  ///
  /// Override with `--dart-define=BLED_API_BASE=<url>`.
  /// Note: no trailing slash.
  static const String apiBaseUrl = String.fromEnvironment(
    'BLED_API_BASE',
    defaultValue: 'http://localhost:8000',
  );

  /// API version prefix used by every endpoint.
  static const String apiPrefix = '/api/v1';

  /// Default map camera position — Tunis, Tunisia.
  static const double tunisLat = 36.8065;
  static const double tunisLon = 10.1815;
  static const double tunisZoom = 12.0;

  /// Geographic bounds of Tunisia, used to constrain the map camera.
  static const double tunisiaSouthLat = 30.0;
  static const double tunisiaNorthLat = 37.6;
  static const double tunisiaWestLon = 7.0;
  static const double tunisiaEastLon = 11.7;

  /// OpenStreetMap raster tiles (free, requires attribution).
  static const String osmTileUrl =
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

  /// Attribution required by the OSM tile usage policy.
  static const String osmAttribution = '© OpenStreetMap contributors';

  /// App metadata.
  static const String appName = 'BLEDI.TN';
  static const String appVersion = '0.1.0';

  /// Walking speed used to estimate leg durations when the backend does not
  /// provide them (km/h).
  static const double walkSpeedKmh = 4.5;

  /// HTTP timeout for API calls.
  static const Duration requestTimeout = Duration(seconds: 20);
}