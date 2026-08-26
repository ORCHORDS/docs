# json-translation-keys-best-practices

**Issue:** Naming and structuring JSON translation keys for long-term maintainability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Poor key naming (source strings as keys, auto-incremented IDs) makes translations difficult to maintain and creates merge conflicts.

## Pattern / Solution
```json
{
  "auth.login.title": "Sign in",
  "auth.login.submit": "Continue",
  "auth.login.errors.invalid_credentials": "Email or password is incorrect",
  "common.actions.save": "Save",
  "common.actions.cancel": "Cancel"
}
```
Rules:
- Use dot-separated namespace segments: `<feature>.<component>.<element>`
- Use snake_case within segments: `invalid_credentials` not `invalidCredentials`
- Never use source text as a key
- Never use sequential IDs
- Include semantic type in leaf names: `.title`, `.label`, `.placeholder`, `.error`, `.hint`

## Gotchas
- Renaming keys requires updating all source code references -- treat keys as public API
- Avoid keys encoding UI position ("right_column_header") -- layouts change, semantics do not
- Very long dot-paths become unwieldy; use i18next namespace files instead

## Related
- `nested-vs-flat-keys.md`
- `react-i18next-namespaces.md`
- `interpolation-patterns.md`
