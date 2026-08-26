# android-strings-xml

**Issue:** Structuring Android strings.xml resource files for localization
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Android resources live in `res/values/strings.xml` with locale overrides in `res/values-<BCP47>/strings.xml`. Incorrect folder naming causes wrong locale to load.

## Pattern / Solution
```
res/values/strings.xml
res/values-fr/strings.xml
res/values-zh-rCN/strings.xml
```
`strings.xml`:
```xml
<resources>
  <string name="app_name">MyApp</string>
  <string name="greeting">Hello, %1$s!</string>
  <plurals name="item_count">
    <item quantity="one">%d item</item>
    <item quantity="other">%d items</item>
  </plurals>
</resources>
```
Kotlin:
```kotlin
getString(R.string.greeting, userName)
resources.getQuantityString(R.plurals.item_count, count, count)
```

## Gotchas
- Region qualifier uses `r` prefix: `values-zh-rCN` not `values-zh-CN`
- XLIFF import/export via Android Studio is preferred for TM integration
- `tools:ignore="TypographyDashes"` silences lint on em-dash characters

## Related
- `plural-rules-cldr.md`
- `ios-localizable-strings.md`
