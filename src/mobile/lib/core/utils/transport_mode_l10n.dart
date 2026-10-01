import 'package:easy_localization/easy_localization.dart';

import '../../data/models/station.dart';

/// Localised labels for the transport categories.
///
/// The enum names are singular and technical; these are what the UI shows.
extension TransportModeL10n on TransportMode {
  String tr() => switch (this) {
    TransportMode.rail => 'rail'.tr(),
    TransportMode.bus => 'bus'.tr(),
    TransportMode.louage => 'louage'.tr(),
    TransportMode.unknown => 'unknown'.tr(),
  };
}