import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/datasources/stations_data_source.dart';
import '../../data/models/station.dart';
import '../../providers/providers.dart';

/// Bottom sheet for picking an origin or destination station.
///
/// Search runs client-side against the cached station list because the
/// deployed `/api/v1/stations` endpoint takes no query parameter.
class StationSearchSheet extends ConsumerStatefulWidget {
  const StationSearchSheet({super.key});

  /// Returns the picked station, or null if dismissed.
  static Future<Station?> show(BuildContext context) {
    return showModalBottomSheet<Station>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const StationSearchSheet(),
    );
  }

  @override
  ConsumerState<StationSearchSheet> createState() => _StationSearchSheetState();
}

class _StationSearchSheetState extends ConsumerState<StationSearchSheet> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  String _query = '';

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final stationsAsync = ref.watch(stationsProvider);

    // Keep the local mirror in sync when the query is cleared elsewhere
    // (e.g. the provider's clear()).
    ref.listen(stationSearchQueryProvider, (_, next) {
      if (next != _query) {
        setState(() => _query = next);
        if (_controller.text != next) _controller.text = next;
      }
    });

    final results = ref.watch(stationSearchResultsProvider);
    final height = MediaQuery.of(context).size.height * 0.75;

    return SizedBox(
      height: height,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: TextField(
              controller: _controller,
              focusNode: _focusNode,
              autofocus: true,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: 'search_hint'.tr(),
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _query.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () {
                          _controller.clear();
                          ref
                              .read(stationSearchQueryProvider.notifier)
                              .clear();
                          setState(() => _query = '');
                        },
                      ),
              ),
              onChanged: (value) {
                ref.read(stationSearchQueryProvider.notifier).setQuery(value);
                setState(() => _query = value);
              },
            ),
          ),
          Expanded(
            child: stationsAsync.when(
              loading: () => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const CircularProgressIndicator(),
                    const SizedBox(height: 12),
                    Text('loading'.tr()),
                  ],
                ),
              ),
              error: (error, _) => _ErrorView(
                message: error.toString(),
                onRetry: () => ref.invalidate(stationsProvider),
              ),
              data: (payload) => _ResultsList(
                payload: payload,
                results: results,
                query: _query,
                onPick: (station) => Navigator.of(context).pop(station),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ResultsList extends StatelessWidget {
  const _ResultsList({
    required this.payload,
    required this.results,
    required this.query,
    required this.onPick,
  });

  final StationsPayload payload;
  final List<Station> results;
  final String query;
  final ValueChanged<Station> onPick;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (query.trim().isEmpty) {
      return ListView(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: Text(
              '${payload.stations.length} ${'stations_loaded'.tr()}',
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          // Newest-first sample so the sheet is useful without typing.
          for (final station in payload.stations.take(50))
            _StationTile(station: station, onTap: () => onPick(station)),
        ],
      );
    }

    if (results.isEmpty) {
      return Center(
        child: Text('no_stations'.tr(), style: theme.textTheme.bodyMedium),
      );
    }

    return ListView.builder(
      itemCount: results.length,
      itemBuilder: (context, index) {
        final station = results[index];
        return _StationTile(station: station, onTap: () => onPick(station));
      },
    );
  }
}

class _StationTile extends StatelessWidget {
  const _StationTile({required this.station, required this.onTap});

  final Station station;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lineLabels = station.lines
        .map((l) => l.shortName ?? l.label)
        .whereType<String>()
        .toSet()
        .take(3)
        .toList();

    return ListTile(
      onTap: onTap,
      leading: Icon(
        Icons.directions_bus,
        color: theme.colorScheme.primary,
      ),
      title: Text(station.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: lineLabels.isEmpty
          ? null
          : Text(
              lineLabels.join(' · '),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
      trailing: const Icon(Icons.chevron_right),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 40),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.tonal(
              onPressed: onRetry,
              child: Text('retry'.tr()),
            ),
          ],
        ),
      ),
    );
  }
}