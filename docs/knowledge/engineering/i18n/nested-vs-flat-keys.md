# nested-vs-flat-keys

**Issue:** Choosing between nested JSON objects and flat dotted-path keys for translation files
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Translation files can use deeply nested JSON objects or flat dotted keys. Each has trade-offs for tooling, merging, and runtime lookup.

## Pattern / Solution
Nested:
```json
{
  "auth": {
    "login": {
      "title": "Sign in",
      "submit": "Continue"
    }
  }
}
```
Flat:
```json
{
  "auth.login.title": "Sign in",
  "auth.login.submit": "Continue"
}
```
i18next handles both identically: `t('auth.login.title')`.

| Concern | Nested | Flat |
|---------|--------|------|
| Readability | Better structure | Verbose |
| Git diffs | Extra nesting noise | Cleaner |
| Key conflicts | Impossible | Possible |
| Partial overrides | Harder | Easier |

## Gotchas
- i18next `keySeparator: false` disables dot-path parsing -- all dots become literal
- A key cannot share a prefix with a value: `{ "foo": "bar", "foo.baz": "qux" }` is invalid
- Some TMS platforms import only flat JSON; use the `flat` npm package to convert

## Related
- `json-translation-keys-best-practices.md`
- `flat-dotted-vs-nested-keys.md`
