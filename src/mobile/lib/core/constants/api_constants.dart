class ApiConstants {
  // Base URL
  static const String baseUrl = 'https://api.bledi.tn';
  static const String apiVersion = '/api/v1';
  static const String fullBaseUrl = '$baseUrl$apiVersion';
  
  // Endpoints
  static const String stations = '/stations';
  static const String lines = '/lines';
  static const String routes = '/routes';
  static const String nearby = '/nearby';
  static const String departures = '/departures';
  static const String search = '/search';
  
  // Timeouts
  static const Duration connectTimeout = Duration(seconds: 10);
  static const Duration receiveTimeout = Duration(seconds: 30);
  
  // Cache
  static const String cacheKeyStations = 'stations_cache';
  static const String cacheKeyLines = 'lines_cache';
  static const Duration cacheValidity = Duration(hours: 24);
}
