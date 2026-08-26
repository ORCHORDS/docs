# xliff-format-handling

**Issue:** Working with XLIFF 1.2 and 2.0 files for translation exchange
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
XLIFF is the standard format for sending content to translators and receiving it back. Version differences cause import failures between tools.

## Pattern / Solution
XLIFF 1.2:
```xml
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en" target-language="fr" datatype="plaintext">
    <body>
      <trans-unit id="welcome.title">
        <source>Welcome</source>
        <target state="needs-translation">Bienvenue</target>
        <note>Header on landing page</note>
      </trans-unit>
    </body>
  </file>
</xliff>
```
XLIFF 2.0:
```xml
<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0"
       srcLang="en" trgLang="fr">
  <file id="f1">
    <unit id="welcome.title">
      <notes><note category="context">Header on landing page</note></notes>
      <segment state="initial">
        <source>Welcome</source>
        <target>Bienvenue</target>
      </segment>
    </unit>
  </file>
</xliff>
```
XLIFF 2.0 states: `initial`, `translated`, `reviewed`, `final`

## Gotchas
- XLIFF 1.2 `state` is on `<target>`; XLIFF 2.0 `state` is on `<segment>`
- Inline elements differ between versions (`<ph>` vs `<pc>`)
- Angular exports XLIFF 1.2 by default; use `--format xliff2` for XLIFF 2

## Related
- `translation-memory-tmx.md`
- `po-gettext-format.md`
