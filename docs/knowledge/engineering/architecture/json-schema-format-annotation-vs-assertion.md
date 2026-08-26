# JSON Schema Format Annotation versus Assertion

**Issue:** A schema containing `format: email`, `uri`, or `date-time` may appear to validate syntax while a Draft 2020-12 implementation is allowed to treat the keyword as annotation only.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Pin `$schema` and record whether the validator enables the format-assertion vocabulary. Do not infer enforcement from the presence of `format` alone.
- Use the format-assertion vocabulary or an explicit validator option when format validity is a contract requirement.
- Add deterministic application checks for security-sensitive semantics such as redirect URI policy, mailbox ownership, identifier normalization, and calendar constraints.
- Test every format relied upon; validator support can differ by format and build even when basic schema validation succeeds.
- Keep annotations useful for documentation and generated UI, but label them separately from hard acceptance criteria.
- Reject configuration drift where local, CI, gateway, and production validators use different format modes.

## Verification
- Feed each relied-upon format a structurally valid value and several invalid edge cases, then assert the expected failures in all environments.
- Inspect the active metaschema and validator options in CI rather than checking only library version.
- Include internationalized, timezone, leap-day, escaping, and normalization cases appropriate to the format.

## Gotchas
Format assertion checks lexical format, not whether an email exists, a URI is safe to fetch, or a date is permitted by the business.

## Official sources
- https://json-schema.org/draft/2020-12/json-schema-validation
