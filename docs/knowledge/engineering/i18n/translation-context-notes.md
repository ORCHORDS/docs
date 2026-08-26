# translation-context-notes

**Issue:** Providing translators with enough context to produce accurate translations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Translators without context mistranslate ambiguous words ("Save" = save data vs. rescue), gender-dependent phrases, and UI labels whose meaning depends on surrounding elements.

## Pattern / Solution
JSON with `@` metadata (i18next convention):
```json
{
  "save_button": "Save",
  "@save_button": {
    "comment": "Button in document editor. Saves file to disk. Not rescue. Max 10 chars.",
    "maxLength": 10
  }
}
```
XLIFF `<note>`:
```xml
<trans-unit id="save_button">
  <source>Save</source>
  <note>Button in document editor. Saves file. Character limit: 10.</note>
</trans-unit>
```
ARB (Flutter) metadata:
```json
{
  "saveButton": "Save",
  "@saveButton": {
    "description": "Button label. Saves current file.",
    "context": "Editor toolbar, top-right"
  }
}
```

## Gotchas
- Context notes are stripped by many TMS platforms unless explicitly mapped at import
- Screenshots are more effective than text descriptions
- Adding context retroactively is expensive -- build it into the developer workflow

## Related
- `screenshot-based-translation.md`
- `json-translation-keys-best-practices.md`
