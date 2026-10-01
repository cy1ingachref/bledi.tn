import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Guards the localization assets that easy_localization loads at runtime.
///
/// This exists because the app once shipped only `.arb` files and rendered a
/// blank screen with `Unable to load asset: "assets/l10n/fr.json"` — a failure
/// that compiles fine and only appears at runtime.
void main() {
  final l10nDir = Directory('assets/l10n');

  test('the asset directory exists and ships the runtime JSON files', () {
    expect(l10nDir.existsSync(), isTrue,
        reason: 'assets/l10n must exist for easy_localization');

    for (final locale in ['ar', 'fr', 'en']) {
      final json = File('assets/l10n/$locale.json');
      expect(json.existsSync(), isTrue,
          reason: 'easy_localization loads <locale>.json — $locale.json missing');
    }
  });

  test('every locale file is valid JSON with identical key sets', () {
    Map<String, dynamic>? reference;
    for (final locale in ['en', 'fr', 'ar']) {
      final decoded =
          jsonDecode(File('assets/l10n/$locale.json').readAsStringSync())
              as Map<String, dynamic>;

      expect(decoded, isNotEmpty);
      expect(decoded['@@locale'], isNull,
          reason: 'the ARB @@locale marker must not ship at runtime');

      if (reference == null) {
        reference = decoded;
      } else {
        expect(
          decoded.keys.toSet(),
          reference.keys.toSet(),
          reason: '$locale has a different key set than en — '
              'a translation is missing or stale',
        );
      }
    }
  });

  test('translations are non-empty for every key', () {
    for (final locale in ['en', 'fr', 'ar']) {
      final decoded =
          jsonDecode(File('assets/l10n/$locale.json').readAsStringSync())
              as Map<String, dynamic>;
      for (final entry in decoded.entries) {
        expect(entry.value, isA<String>(), reason: '${entry.key} in $locale');
        expect((entry.value as String).trim(), isNotEmpty,
            reason: '${entry.key} in $locale is blank');
      }
    }
  });

  test('pubspec declares the l10n assets so they are bundled', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    expect(pubspec, contains('assets/l10n/'),
        reason: 'assets/l10n/ must be listed under flutter: assets: or it '
            'will not be bundled into the build');
  });
}