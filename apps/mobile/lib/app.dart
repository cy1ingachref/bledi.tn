import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/home/home_screen.dart';
import '../features/settings/settings_screen.dart';

/// App routes. Two screens for now; the stations and lines screens can slot in
/// here later without changing the map/home wiring.
final GoRouter appRouter = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const HomeScreen(),
      routes: [
        GoRoute(
          path: 'settings',
          builder: (context, state) => const SettingsScreen(),
        ),
      ],
    ),
  ],
  errorBuilder: (context, state) => Scaffold(
    appBar: AppBar(title: const Text('BLEDI.TN')),
    body: Center(child: Text('Page not found: ${state.uri}')),
  ),
);

/// Convenience reference to the router's home path.
const String homeRoute = '/';
const String settingsRoute = '/settings';