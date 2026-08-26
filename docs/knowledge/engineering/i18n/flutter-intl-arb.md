# flutter-intl-arb

**Issue:** Using ARB files and flutter_localizations for Flutter i18n
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Flutter recommends ARB (Application Resource Bundle) files. Misconfigured `l10n.yaml` causes missing generated Dart code.

## Pattern / Solution
`pubspec.yaml`:
```yaml
dependencies:
  flutter_localizations:
    sdk: flutter
  intl: ^0.19.0
flutter:
  generate: true
```
`l10n.yaml`:
```yaml
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
```
`lib/l10n/app_en.arb`:
```json
{
  "@@locale": "en",
  "helloName": "Hello, {name}!",
  "@helloName": { "placeholders": { "name": { "type": "String" } } },
  "itemCount": "{count, plural, one{1 item} other{{count} items}}",
  "@itemCount": { "placeholders": { "count": { "type": "int" } } }
}
```
Usage:
```dart
Text(AppLocalizations.of(context)!.helloName('World'));
```

## Gotchas
- Run `flutter gen-l10n` to regenerate after ARB changes
- `@` metadata keys must immediately follow their message key
- Plural messages use ICU syntax inside ARB values

## Related
- `icu-message-format.md`
- `plural-rules-cldr.md`
