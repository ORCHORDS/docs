# Unknown-Field Policy Is a Versioning Decision

**Issue:** Silently ignoring unknown fields improves forward compatibility but hides misspellings; rejecting them catches mistakes but can break rolling upgrades.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Choose reject, ignore, or preserve semantics per boundary and document it.
- Use strict handling for operator configuration and security policy; consider tolerant readers for versioned messages.
- Emit observable warnings for ignored fields without leaking payload data.
- Preserve unknown fields only when round-trip compatibility requires it.

## Verification

- Send misspelled, future, nested, and extension fields during mixed-version rollout.
- Verify strict boundaries fail with actionable paths.
- Confirm tolerant readers do not authorize behavior from unknown data.

## Gotchas

- Schema validation defaults differ by library.
- Additional properties can become a covert policy bypass if later code reads them.

## Official sources

- https://json-schema.org/understanding-json-schema/reference/object#additional-properties
