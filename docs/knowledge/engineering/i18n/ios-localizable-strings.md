# ios-localizable-strings

**Issue:** Managing Localizable.strings and Localizable.stringsdict in iOS projects
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
iOS localizes via `.strings` (key=value) and `.stringsdict` (plural XML) in `.lproj` folders. Missing entries silently fall back to the key.

## Pattern / Solution
```
en.lproj/Localizable.strings
fr.lproj/Localizable.strings
en.lproj/Localizable.stringsdict
```
`Localizable.strings`:
```
"welcome_title" = "Welcome";
"greeting_name" = "Hello, %@!";
```
`Localizable.stringsdict` plural:
```xml
<key>items_count</key>
<dict>
  <key>NSStringLocalizedFormatKey</key><string>%#@count@</string>
  <key>count</key>
  <dict>
    <key>NSStringFormatSpecTypeKey</key><string>NSStringPluralRuleType</string>
    <key>NSStringFormatValueTypeKey</key><string>d</string>
    <key>one</key><string>%d item</string>
    <key>other</key><string>%d items</string>
  </dict>
</dict>
```
Swift usage:
```swift
NSLocalizedString("welcome_title", comment: "Main screen title")
String.localizedStringWithFormat(NSLocalizedString("items_count", comment: ""), count)
```

## Gotchas
- Encoding: UTF-8 accepted in Xcode 14+; earlier versions require UTF-16
- `genstrings` only scans Swift/ObjC; SwiftUI uses `extractLocStrings`
- Missing `.stringsdict` causes runtime crash when plural key is missing

## Related
- `plural-rules-cldr.md`
- `android-strings-xml.md`
