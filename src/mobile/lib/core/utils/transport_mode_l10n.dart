import 'package:easy_localization/easy_localization.dart';

import '../../data/models/station.dart';

/// Localised labels for the transport categories.
///
/// The enum names are singular and technical; these are what the UI shows.
/// `rail`, `metro` and `tram` are three separate labels: they used to collapse
/// into one "Train / Metro" string, which is exactly what stopped a user from
/// telling the app "no metro".
extension TransportModeL10n on TransportMode {
  String tr() => switch (this) {
    TransportMode.rail => 'rail'.tr(),
    TransportMode.metro => 'metro'.tr(),
    TransportMode.tram => 'tram'.tr(),
    TransportMode.bus => 'bus'.tr(),
    TransportMode.louage => 'louage'.tr(),
    TransportMode.walk => 'walk'.tr(),
    TransportMode.unknown => 'unknown'.tr(),
  };
}
