import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/models/itinerary.dart';
import '../../providers/providers.dart';
import '../home/widgets/bledi_map.dart';

/// Bottom sheet showing the itinerary summary and step-by-step instructions.
class RoutingPanel extends ConsumerWidget {
  const RoutingPanel({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final result = ref.watch(routingProvider);
    final theme = Theme.of(context);

    if (result.hasError) {
      return _ErrorBody(message: _errorText(context, result.errorMessage));
    }

    final itinerary = result.itinerary;
    if (itinerary == null) {
      return SizedBox(
        height: 220,
        child: Center(child: Text('routing'.tr())),
      );
    }

    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.55,
      minChildSize: 0.3,
      maxChildSize: 0.92,
      builder: (context, scrollController) => ListView(
        controller: scrollController,
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        children: [
          _SummaryCard(itinerary: itinerary),
          const SizedBox(height: 16),
          Text(
            'steps'.tr(),
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          for (var i = 0; i < itinerary.steps.length; i++)
            _StepTile(step: itinerary.steps[i], index: i),
        ],
      ),
    );
  }

  static String _errorText(BuildContext context, String? raw) {
    if (raw == null || raw.isEmpty) return 'no_route'.tr();
    // The backend sends English messages; pass them through rather than
    // showing a bare key.
    return raw;
  }
}

/// Duration / transfers / fare summary.
class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.itinerary});

  final Itinerary itinerary;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.schedule, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${'total_duration'.tr()}: ${formatDuration(context, itinerary.durationMin)}',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _Chip(
                  icon: Icons.swap_horiz,
                  label: '${'transfers'.tr()}: ${itinerary.transfers}',
                ),
                if (itinerary.hasFare)
                  _Chip(
                    icon: Icons.payments_outlined,
                    label:
                        '${'fare'.tr()}: ${itinerary.fareDinars!.toStringAsFixed(2)} DT',
                  ),
                _Chip(
                  icon: Icons.timeline,
                  label: '${'steps'.tr()}: ${itinerary.steps.length}',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 6),
          Text(label, style: theme.textTheme.labelMedium),
        ],
      ),
    );
  }
}

/// One instruction row: mode icon, label, distance and duration.
class _StepTile extends StatelessWidget {
  const _StepTile({required this.step, required this.index});

  final RouteStep step;
  final int index;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = _resolveColor(theme, step);
    final label = stepLabel(context, step);
    final title = step.isRide
        ? (step.line ?? label)
        : label;

    final durationMin = step.estimatedDurationMin();
    // The backend sends no per-step duration, so this figure is derived from
    // straight-line distance. It is marked with "~" so it is not read as a
    // timetable value.
    final details = <String>[
      if (step.distanceMeters > 5) formatDistance(step.distanceMeters),
      if (durationMin > 0) '~${formatDuration(context, durationMin)}',
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                  border: Border.all(color: color),
                ),
                child: Icon(stepIcon(step), size: 16, color: color),
              ),
              if (index < 99)
                Container(width: 2, height: 22, color: color.withValues(alpha: 0.4)),
            ],
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (step.endLabel.isNotEmpty)
                    Text(
                      step.endLabel,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  if (details.isNotEmpty)
                    Text(
                      details.join(' · '),
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  static Color _resolveColor(ThemeData theme, RouteStep step) {
    final hex = step.hexColor;
    if (hex != null) {
      final value = hex.replaceFirst('#', '');
      if (value.length == 6) {
        final parsed = int.tryParse(value, radix: 16);
        if (parsed != null) return Color(0xFF000000 | parsed);
      }
    }
    return AppTheme.stepColor(step.isRide ? step.mode : step.type);
  }
}

class _ErrorBody extends StatelessWidget {
  const _ErrorBody({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 40),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, size: 36, color: Theme.of(context).colorScheme.error),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          FilledButton.tonal(
            onPressed: () => Navigator.of(context).pop(),
            child: Text('close'.tr()),
          ),
        ],
      ),
    );
  }
}