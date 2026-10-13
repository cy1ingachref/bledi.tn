import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/models/city.dart';
import '../../data/models/station.dart';
import '../../providers/providers.dart';

/// Picker listing every city with its stops, grouped by governorate.
///
/// Selecting a city filters the map to it and zooms the camera in.
class CityPickerSheet extends ConsumerWidget {
  const CityPickerSheet({super.key});

  /// Returns the chosen city name, or null when dismissed / cleared.
  static Future<String?> show(BuildContext context) {
    return showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const CityPickerSheet(),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cities = ref.watch(citiesProvider);
    final selected = ref.watch(selectedCityProvider);
    final theme = Theme.of(context);

    return SizedBox(
      height: MediaQuery.of(context).size.height * 0.75,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'cities'.tr(),
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                if (selected != null)
                  TextButton.icon(
                    onPressed: () {
                      ref.read(selectedCityProvider.notifier).select(null);
                      Navigator.of(context).pop();
                    },
                    icon: const Icon(Icons.public, size: 18),
                    label: Text('all_cities'.tr()),
                  ),
              ],
            ),
          ),
          if (cities.isEmpty)
            Expanded(child: Center(child: Text('loading'.tr())))
          else
            Expanded(
              child: ListView.separated(
                itemCount: cities.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (context, index) {
                  final city = cities[index];
                  final isSelected = city.name == selected;
                  return ListTile(
                    selected: isSelected,
                    onTap: () {
                      ref.read(selectedCityProvider.notifier).select(city.name);
                      Navigator.of(context).pop(city.name);
                    },
                    leading: Icon(
                      Icons.location_city,
                      color: isSelected
                          ? theme.colorScheme.primary
                          : theme.colorScheme.onSurfaceVariant,
                    ),
                    title: Text(
                      city.name,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    subtitle: _ModeBreakdown(city: city),
                    trailing: Text(
                      '${city.stationCount}',
                      style: theme.textTheme.labelMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

/// Per-mode dot counts for a city row.
class _ModeBreakdown extends StatelessWidget {
  const _ModeBreakdown({required this.city});

  final City city;

  @override
  Widget build(BuildContext context) {
    final counts = city.countsByCategory;
    final present = TransportMode.all
        .where((m) => (counts[m] ?? 0) > 0)
        .toList(growable: false);
    if (present.isEmpty) return const SizedBox.shrink();

    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: [
          for (final mode in present)
            Padding(
              padding: const EdgeInsets.only(right: 10),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: AppTheme.modeColor(mode),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '${counts[mode]}',
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}