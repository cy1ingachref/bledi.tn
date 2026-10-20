import 'package:flutter_test/flutter_test.dart';

import 'package:bledi_app/core/theme.dart';
import 'package:bledi_app/core/utils/transport_mode_l10n.dart';
import 'package:bledi_app/data/models/station.dart';

/// The transport taxonomy is the contract between the mode selector and
/// `/api/v1/route/plan`. Metro used to collapse into `rail`, which made "no
/// metro but trains are fine" impossible to express end to end.
void main() {
  group('TransportMode.fromName', () {
    test('metro and tram are distinct from rail', () {
      expect(TransportMode.fromName('metro'), TransportMode.metro);
      expect(TransportMode.fromName('tram'), TransportMode.tram);
      expect(TransportMode.fromName('train'), TransportMode.rail);
      expect(TransportMode.fromName('rail'), TransportMode.rail);
      expect(TransportMode.metro, isNot(TransportMode.rail));
    });

    test('backend seed aliases map correctly', () {
      expect(TransportMode.fromName('subway'), TransportMode.metro);
      expect(TransportMode.fromName('rfr'), TransportMode.bus);
      expect(TransportMode.fromName('louage'), TransportMode.louage);
      expect(TransportMode.fromName('louage_red'), TransportMode.louage);
      expect(TransportMode.fromName('taxi'), TransportMode.louage);
      expect(TransportMode.fromName('walk'), TransportMode.walk);
    });

    test('unknown stays unknown rather than silently becoming bus', () {
      // Mapping an unrecognised tag to bus would invent services the data does
      // not have, so it must be visible instead.
      expect(TransportMode.fromName('hovercraft'), TransportMode.unknown);
      expect(TransportMode.fromName(null), TransportMode.unknown);
      expect(TransportMode.fromName('  '), TransportMode.unknown);
    });
  });

  group('TransportMode.apiValue', () {
    test('round-trips through fromName', () {
      for (final mode in TransportMode.selectable) {
        expect(
          TransportMode.fromName(mode.apiValue),
          mode,
          reason: '${mode.name} -> ${mode.apiValue} must parse back',
        );
      }
    });

    test('uses the wire names the backend accepts', () {
      // These are what goes into modes_include; a mismatch here silently
      // changes which transports the router is allowed to use.
      expect(TransportMode.rail.apiValue, 'train');
      expect(TransportMode.louage.apiValue, 'louaj');
      expect(TransportMode.metro.apiValue, 'metro');
    });
  });

  group('TransportMode.selectable', () {
    test('omits walk -- it is access/egress, never a transport family', () {
      expect(TransportMode.selectable, isNot(contains(TransportMode.walk)));
    });

    test('omits unknown -- not offerable', () {
      expect(TransportMode.selectable, isNot(contains(TransportMode.unknown)));
    });

    test('covers the five real transports, each once', () {
      expect(TransportMode.selectable.length, 5);
      expect(TransportMode.selectable.toSet(), {
        TransportMode.bus,
        TransportMode.metro,
        TransportMode.tram,
        TransportMode.rail,
        TransportMode.louage,
      });
    });
  });

  group('theme colours', () {
    test('modeColor is total over the enum and distinct per mode', () {
      // A missing arm used to be a compile error the analyzer caught; this
      // pins the behaviour so adding an enum value cannot slip through with a
      // shared colour.
      final colours = {
        for (final mode in TransportMode.values) mode: AppTheme.modeColor(mode),
      };
      expect(colours.keys.length, TransportMode.values.length);
      // metro / tram / rail must not share a colour or the map cannot tell an
      // urban metro leg from an intercity train.
      expect(colours[TransportMode.metro], isNot(colours[TransportMode.rail]));
      expect(colours[TransportMode.tram], isNot(colours[TransportMode.rail]));
      expect(colours[TransportMode.metro], isNot(colours[TransportMode.tram]));
    });

    test('stepColor recognises every backend mode string', () {
      // 'tram' and 'rail' used to fall through to the walk colour, which made a
      // tram or regional-rail leg render grey on the map.
      expect(AppTheme.stepColor('metro'), AppTheme.metroColor);
      expect(AppTheme.stepColor('tram'), AppTheme.tramColor);
      expect(AppTheme.stepColor('train'), AppTheme.trainColor);
      expect(AppTheme.stepColor('rail'), AppTheme.railColor);
      expect(AppTheme.stepColor('rfr'), AppTheme.rfrColor);
      expect(AppTheme.stepColor('bus'), AppTheme.busColor);
      expect(AppTheme.stepColor('walk'), AppTheme.walkColor);
      expect(AppTheme.stepColor('taxi'), AppTheme.louageColor);
      expect(AppTheme.stepColor('louaj'), AppTheme.louageColor);
      // An unknown tag still falls back rather than throwing.
      expect(AppTheme.stepColor('hovercraft'), AppTheme.walkColor);
    });
  });

  group('localised labels', () {
    test('every selectable mode has a non-empty label', () {
      for (final mode in TransportMode.selectable) {
        expect(mode.tr(), isNotEmpty, reason: '${mode.name} needs a label');
      }
    });
  });
}
