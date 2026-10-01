import 'package:flutter/material.dart';

import '../data/models/station.dart';

/// Material 3 theme for BLEDI.TN.
///
/// The seed colour is the Tunisian flag red. Mode colours are the product's
/// specified palette and are defined here rather than in the map layer so the
/// legend, the filter chips, the station dots and the line overlays all agree.
class AppTheme {
  const AppTheme._();

  static const Color seedColor = Color(0xFFE70013); // Tunisian flag red

  /// Rail family: train, metro, RFR.
  static const Color railColor = Color(0xFF1B9E4B);

  /// Bus.
  static const Color busColor = Color(0xFFD32F2F);

  /// Taxi / louage.
  static const Color louageColor = Color(0xFFF2B705);

  /// Stops with no recognised mode.
  static const Color unknownColor = Color(0xFF9AA0A6);

  /// Walk legs and generic fallback.
  static const Color walkColor = Color(0xFF8B949E);

  /// The backend's own per-step colours, used when it supplies one for a
  /// routing step. Metro blue / train purple / RFR orange / bus red.
  static const Color metroColor = Color(0xFF339AF0);
  static const Color trainColor = Color(0xFF845EF7);
  static const Color rfrColor = Color(0xFFFF922B);

  /// Colour for a transport category.
  static Color modeColor(TransportMode mode) => switch (mode) {
    TransportMode.rail => railColor,
    TransportMode.bus => busColor,
    TransportMode.louage => louageColor,
    TransportMode.unknown => unknownColor,
  };

  /// Colour for a backend mode string, used for routing-step polylines.
  static Color stepColor(String? mode, {Color fallback = walkColor}) {
    return switch (mode) {
      'metro' => metroColor,
      'train' => trainColor,
      'rfr' => rfrColor,
      'bus' => busColor,
      'walk' => walkColor,
      'taxi' => louageColor,
      _ => fallback,
    };
  }

  static ThemeData light() => _base(Brightness.light);
  static ThemeData dark() => _base(Brightness.dark);

  static ThemeData _base(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(
      seedColor: seedColor,
      brightness: brightness,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      appBarTheme: AppBarTheme(
        centerTitle: false,
        elevation: 0,
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 14,
        ),
      ),
    );
  }
}