import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/transport_mode_l10n.dart';
import '../../../data/models/station.dart';
import '../../../providers/providers.dart';

/// Add or remove transports from the trip.
///
/// Each chip is a toggle, so tapping "Metro" off removes it and tapping it back
/// on restores it. The selection is sent to the backend as `modes_include`,
/// which the router applies while expanding the graph -- so a transport that
/// is off here cannot turn up in a result, instead of being priced by the
/// router and then hidden by the UI.
///
/// The last enabled transport cannot be switched off: a trip with no transport
/// is not a trip, and an empty include would silently become "everything".
class TransportSelector extends ConsumerWidget {
  const TransportSelector({super.key, this.dense = false});

  final bool dense;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(transportSelectionProvider);
    final notifier = ref.read(transportSelectionProvider.notifier);
    final theme = Theme.of(context);

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final mode in TransportMode.selectable)
          FilterChip(
            key: ValueKey<String>('transport_chip_${mode.name}'),
            label: Text(mode.tr()),
            selected: selected.contains(mode),
            showCheckmark: false,
            visualDensity: dense ? VisualDensity.compact : null,
            avatar: Icon(_iconFor(mode), size: dense ? 16 : 18),
            selectedColor: theme.colorScheme.primaryContainer,
            side: BorderSide(
              color: selected.contains(mode)
                  ? theme.colorScheme.primary
                  : theme.colorScheme.outlineVariant,
            ),
            onSelected: (_) {
              // Refuses to empty the selection; the chip simply does not move.
              notifier.toggle(mode);
            },
          ),
      ],
    );
  }

  static IconData _iconFor(TransportMode mode) => switch (mode) {
    TransportMode.bus => Icons.directions_bus,
    TransportMode.metro => Icons.subway,
    TransportMode.tram => Icons.tram,
    TransportMode.rail => Icons.train,
    TransportMode.louage => Icons.local_taxi,
    TransportMode.walk => Icons.directions_walk,
    TransportMode.unknown => Icons.help_outline,
  };
}

/// Compact row: the selector plus "all" / "none but one" shortcuts.
class TransportSelectorBar extends ConsumerWidget {
  const TransportSelectorBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(transportSelectionProvider);
    final notifier = ref.read(transportSelectionProvider.notifier);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'Transports',
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const Spacer(),
            Text(
              '${selected.length}/${TransportMode.selectable.length}',
              key: const ValueKey<String>('transport_count'),
              style: Theme.of(context).textTheme.labelMedium,
            ),
            const SizedBox(width: 8),
            TextButton(
              key: const ValueKey<String>('transport_select_all'),
              onPressed: notifier.selectAll,
              child: const Text('Tous'),
            ),
          ],
        ),
        const SizedBox(height: 4),
        const TransportSelector(dense: true),
      ],
    );
  }
}