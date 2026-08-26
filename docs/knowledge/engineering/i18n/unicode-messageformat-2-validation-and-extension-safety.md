# Unicode MessageFormat 2 Validation and Extension Safety

**Issue:** MessageFormat 2 enables portable structured messages and extensible formatting, but accepting merely parseable patterns, unsafe invisible characters, or untrusted extension code can create misleading translations and code-execution or privacy risks.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Distinguish well-formed syntax from a valid message. Reject both syntax errors and data-model errors during build-time catalog validation.
- Pin the Unicode LDML/CLDR revision and the implementation version used by build, translation tooling, and runtime; conformance and registry behavior must not drift independently.
- Permit only reviewed functions, selectors, options, and markup. Treat third-party extension implementations as code and sandbox or prohibit them.
- Validate external variables and expected operand types at message boundaries. Do not let formatter failures silently expose raw patterns or fallback identifiers to users.
- Detect bidi controls, unexpected ASCII controls, and other invisible characters in source and translated catalogs. Review intentional controls with Unicode-aware tooling.
- Preserve the structured data model through translation exchange rather than flattening patterns into ad hoc strings.
- Define deterministic fallback behavior for unknown functions, missing variables, unsupported operations, and unavailable locales; emit telemetry without including sensitive variable values.

## Verification

1. Compile every locale catalog against the pinned parser and registry.
2. Test malformed grammar, well-formed-but-invalid data, unknown functions, bad options, missing variables, bidi controls, and hostile extensions.
3. Round-trip syntax through the interchange data model and confirm equivalent selection and formatting.
4. Snapshot representative plural, date, number, and bidirectional messages across supported runtimes.

## Gotchas

- Parse success alone does not establish validity.
- MessageFormat permits many characters that a host resource format or code-review UI may render deceptively.
- Runtime-specific extensions reduce interchange portability.

## Sources

- [Unicode LDML Part 9 — MessageFormat](https://www.unicode.org/reports/tr35/tr35-messageFormat.html)
- [Unicode LDML status and conformance](https://www.unicode.org/reports/tr35/)
