import 'package:flutter/material.dart';

import '../../core/constants.dart';
import '../../data/models/health.dart';
import '../../providers/providers.dart';
import 'package:easy_localization/easy_localization.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Backend URL editor + connectivity check.
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(
      text: ref.read(baseUrlProvider),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final notifier = ref.read(baseUrlProvider.notifier);
    await notifier.setBaseUrl(_controller.text);
    // The ApiClient and every repository rebuild from the new URL.
    ref.invalidate(healthProvider);
    ref.invalidate(stationsProvider);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('${'backend_url'.tr()}: ${ref.read(baseUrlProvider)}')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final healthAsync = ref.watch(healthProvider);

    return Scaffold(
      appBar: AppBar(title: Text('settings'.tr())),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('backend_url'.tr(), style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          TextField(
            controller: _controller,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: InputDecoration(
              hintText: 'http://localhost:8000',
              suffixIcon: IconButton(
                icon: const Icon(Icons.save),
                onPressed: _save,
              ),
            ),
            onSubmitted: (_) => _save(),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => ref.invalidate(healthProvider),
              icon: const Icon(Icons.refresh, size: 18),
              label: Text('check_connection'.tr()),
            ),
          ),
          const SizedBox(height: 16),
          healthAsync.when(
            loading: () => const LinearProgressIndicator(),
            error: (error, _) => Card(
              child: ListTile(
                leading: Icon(
                  Icons.cloud_off,
                  color: theme.colorScheme.error,
                ),
                title: Text('backend_unreachable'.tr()),
                subtitle: Text(error.toString()),
              ),
            ),
            data: (health) => _HealthCard(health: health),
          ),
          const SizedBox(height: 24),
          Text(
            '${AppConstants.appName} v${AppConstants.appVersion}',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _HealthCard extends StatelessWidget {
  const _HealthCard({required this.health});

  final Health health;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final ok = health.isHealthy;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  ok ? Icons.check_circle : Icons.error,
                  color: ok ? const Color(0xFF2F9E44) : theme.colorScheme.error,
                ),
                const SizedBox(width: 8),
                Text(
                  (ok ? 'backend_healthy' : 'backend_unreachable').tr(),
                  style: theme.textTheme.titleSmall,
                ),
              ],
            ),
            const SizedBox(height: 12),
            _kv(context, 'Version', health.version ?? '—'),
            _kv(context, 'Seed', health.seedFile ?? '—'),
            _kv(
              context,
              'stations'.tr(),
              '${health.stationsCount} ${'stations_loaded'.tr()}',
            ),
            _kv(
              context,
              'lines'.tr(),
              '${health.linesCount} ${'lines_loaded'.tr()}',
            ),
          ],
        ),
      ),
    );
  }

  Widget _kv(BuildContext context, String key, String value) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(
              key,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(child: Text(value, style: theme.textTheme.bodySmall)),
        ],
      ),
    );
  }
}