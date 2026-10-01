import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../core/utils/transport_mode_l10n.dart';
import '../../data/models/station.dart';
import 'station_map_model.dart';

/// Detail sheet for a tapped station: its modes, and the lines serving it.
///
/// Each line is shown as a coloured chip so the user can see at a glance what
/// runs from that stop. Line colours are derived from the line's own mode; the
/// seed's `route_color` is only used when it is a valid hex value.
class StationInfoSheet extends StatelessWidget {
  const StationInfoSheet({super.key, required this.station});

  final MapStation station;

  static Future<void> show(BuildContext context, MapStation station) {
    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => StationInfoSheet(station: station),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.7,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    margin: const EdgeInsets.only(top: 4),
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(
                      color: station.color,
                      shape: BoxShape.circle,
                      border: Border.all(color: Colors.white, width: 2),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          station.name,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          [
                            if (station.city != null) station.city!,
                            '${station.lat.toStringAsFixed(4)}, '
                                '${station.lon.toStringAsFixed(4)}',
                          ].join(' · '),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  _ModeChip(mode: station.mode),
                  if (station.city != null)
                    Chip(
                      label: Text(station.city!),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                ],
              ),
              if (station.lineLabels.isNotEmpty) ...[
                const SizedBox(height: 18),
                Text(
                  'lines_here'.tr(),
                  style: theme.textTheme.labelMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final label in station.lineLabels.take(18))
                      _LineChip(label: label, mode: station.mode),
                  ],
                ),
              ] else ...[
                const SizedBox(height: 18),
                Text(
                  'no_lines'.tr(),
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ModeChip extends StatelessWidget {
  const _ModeChip({required this.mode});

  final TransportMode mode;

  @override
  Widget build(BuildContext context) {
    final color = AppTheme.modeColor(mode);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            mode.tr(),
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Theme.of(context).colorScheme.onSurface,
            ),
          ),
        ],
      ),
    );
  }
}

/// One line serving the station, tinted by its transport mode.
class _LineChip extends StatelessWidget {
  const _LineChip({required this.label, required this.mode});

  final String label;
  final TransportMode mode;

  @override
  Widget build(BuildContext context) {
    final color = AppTheme.modeColor(mode);
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border(
          left: BorderSide(color: color, width: 3),
          top: const BorderSide(color: Colors.transparent),
          right: const BorderSide(color: Colors.transparent),
          bottom: const BorderSide(color: Colors.transparent),
        ),
      ),
      child: Text(
        label,
        style: theme.textTheme.labelSmall?.copyWith(
          color: theme.colorScheme.onSurface,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}