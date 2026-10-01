import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'core/theme.dart';

/// Supported locales. Arabic is first so it becomes the default.
const List<Locale> supportedLocales = [
  Locale('ar'),
  Locale('fr'),
  Locale('en'),
];

const List<Locale> easyLocalizationSupportedLocales = supportedLocales;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: BlediApp()));
}

class BlediApp extends StatelessWidget {
  const BlediApp({super.key});

  @override
  Widget build(BuildContext context) {
    return EasyLocalization(
              supportedLocales: easyLocalizationSupportedLocales,
              // Asset key prefix. Flutter registers `assets: [assets/l10n/]` under
              // the key `assets/l10n/`, and easy_localization appends
              // `<locale>.json` to this — so it must not start with `assets/`.
              path: 'assets/l10n',
          fallbackLocale: const Locale('fr'),
          startLocale: const Locale('fr'),
          child: Builder(
            builder: (context) => MaterialApp.router(
              title: 'BLEDI.TN',
              debugShowCheckedModeBanner: false,
              routerConfig: appRouter,
              themeMode: ThemeMode.system,
              theme: AppTheme.light(),
              darkTheme: AppTheme.dark(),
              localizationsDelegates: [
                              ...EasyLocalization.of(context)!.delegates,
                              GlobalMaterialLocalizations.delegate,
                              GlobalWidgetsLocalizations.delegate,
                              GlobalCupertinoLocalizations.delegate,
                            ],
                            supportedLocales: EasyLocalization.of(context)!.supportedLocales,
            ),
          ),
        );
  }
}