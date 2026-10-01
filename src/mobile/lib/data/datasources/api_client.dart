import 'dart:async';

import 'package:dio/dio.dart';

import '../../core/constants.dart';

/// Thrown for any failed API interaction, carrying a message safe to show in
/// the UI.
class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.source});

  final String message;
  final int? statusCode;

  /// The backend's `source` discriminator (e.g. `local-router`), when present.
  final String? source;

  bool get isNotFound => statusCode == 404;
  bool get isServerError => (statusCode ?? 0) >= 500;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Configures and owns the single [Dio] instance used by the app.
class ApiClient {
  ApiClient({Dio? dio, String? baseUrl})
    : _dio = dio ?? Dio(),
      baseUrl = baseUrl ?? AppConstants.apiBaseUrl {
    _dio.options
      ..baseUrl = this.baseUrl
      ..connectTimeout = AppConstants.requestTimeout
      ..receiveTimeout = AppConstants.requestTimeout
      ..sendTimeout = AppConstants.requestTimeout
      ..headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      }
      // We map non-2xx into ApiException ourselves so error handling is
      // uniform across repositories.
      ..validateStatus = (status) => status != null && status < 400;

    _dio.interceptors.add(
      InterceptorsWrapper(
        onError: (error, handler) {
          handler.next(error); // mapped in _guard below
        },
      ),
    );
  }

  final Dio _dio;
  final String baseUrl;

  Dio get dio => _dio;

  /// Runs [action], converting Dio transport failures into [ApiException] with
  /// a human-readable message.
  Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } on DioException catch (e) {
      throw _mapError(e);
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException('Unexpected error: $e');
    }
  }

  ApiException _mapError(DioException e) {
    final status = e.response?.statusCode;
    final data = e.response?.data;

    // The backend returns 200 with {"error": "..."} for routing failures, and
    // a JSON {"detail": "..."} body for HTTPException cases.
    String? detail;
    if (data is Map<String, dynamic>) {
      final d = data['detail'] ?? data['error'];
      if (d is String) detail = d;
      final src = data['source'];
      if (src is String) {
        return ApiException(detail ?? 'Request failed', source: src);
      }
    } else if (data is String && data.isNotEmpty) {
      detail = data.length > 200 ? '${data.substring(0, 200)}…' : data;
    }

    final message = switch (e.type) {
      DioExceptionType.connectionTimeout ||
      DioExceptionType.sendTimeout ||
      DioExceptionType.receiveTimeout =>
        'The server took too long to respond. Is the backend running at $baseUrl?',
      DioExceptionType.connectionError =>
        'Cannot reach the backend at $baseUrl. Check that it is running and reachable.',
      DioExceptionType.badCertificate => 'The backend certificate was rejected.',
      DioExceptionType.cancel => 'Request cancelled.',
      _ => detail ?? 'Request failed (HTTP ${status ?? 'error'}).',
    };

    return ApiException(message, statusCode: status);
  }

  /// GET [path] returning decoded JSON, with [query] appended.
  ///
  /// Throws [ApiException] on transport failure or non-2xx status.
  Future<dynamic> getJson(
    String path, {
    Map<String, dynamic>? query,
  }) {
    return _guard(() async {
      final cleaned = <String, dynamic>{};
      query?.forEach((key, value) {
        if (value != null) cleaned[key] = value;
      });

      final response = await _dio.get<dynamic>(
        path,
        queryParameters: cleaned.isEmpty ? null : cleaned,
      );
      return response.data;
    });
  }

  void close() => _dio.close(force: true);
}