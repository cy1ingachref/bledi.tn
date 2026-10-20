import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/transport_mode_l10n.dart';
import '../../../data/models/station.dart';
import '../../../providers/providers.dart';

/// Add or remove the transports a trip may use.
///
/// Each chip toggles one mode. The selection is sent to the backend as
/// `modes_include`, which the router applies while expanding its graph, so a
/// transport switched off here cannot reappear in a result -- rather than
/// being priced by the router and merely hidden by the UI.
///
/// Turning off the last remaining transport is refused: a trip with no
/// transport is not a trip, and an empty include would silently mean
/// "everything".
class TransportSelector extends ConsumerWidget {
  const TransportSelector({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(transportSelectionProvider);
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Text('Transports', style: theme.textTheme.labelLarge),
            const Spacer(),
            Text(
              '${selected.length}/${TransportMode.selectable.length}',
              key: const ValueKey<String>('transport_count'),
              style: theme.textTheme.labelMedium,
            ),
            TextButton(
              key: const ValueKey<String>('transport_select_all'),
              onPressed: ref
                  .read(transportSelectionProvider.notifier)
                  .selectAll,
              child: const Text('Tous'),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final mode in TransportMode.selectable)
              FilterChip(
                key: ValueKey<String>('transport_chip_${mode.name}'),
                label: Text(mode.tr()),
                selected: selected.contains(mode),
                showCheckmark: false,
                visualDensity: VisualDensity.compact,
                avatar: Icon(_iconFor(mode), size: 16),
                selectedColor: theme.colorScheme.primaryContainer,
                side: BorderSide(
                  color: selected.contains(mode)
                      ? theme.colorScheme.primary
                      : theme.colorScheme.outlineVariant,
                ),
                // Refuses to empty the selection; the chip simply does not move.
                onSelected: (_) =>
                    ref.read(transportSelectionProvider.notifier).toggle(mode),
              ),
          ],
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
