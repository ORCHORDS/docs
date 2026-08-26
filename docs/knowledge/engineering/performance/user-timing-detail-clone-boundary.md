# User Timing detail structured-clone boundary

**Issue:** Application marks attach large, sensitive, or mutable objects as User Timing detail, increasing memory/telemetry risk and producing inconsistent diagnostics.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

User Timing allows `detail` on marks/measures using structured-clone semantics. Attach only small, low-cardinality diagnostic context and export through an explicit privacy filter.

**Source:** [W3C User Timing Level 3](https://www.w3.org/TR/user-timing-3/)

## Controls

- allowlist primitive/enumerated detail fields;
- exclude DOM nodes, secrets, tokens, URLs, text, and user identifiers;
- cap serialized size and mark count;
- version detail schemas;
- clear marks/measures after the bounded observation window;
- clone/catch errors without affecting product flow.

## Verification

Test supported cloneable values, rejected values, mutation after creation, oversized detail, duplicate names, clear operations, serialization, and unsupported environments.

## Gotchas

Structured-clone support does not make data safe to collect. Detail can retain memory until entries clear. Mark names themselves can leak high-cardinality data.
