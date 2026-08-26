# Sieve filter script safety and governance

**Issue:** Server-side mail filters are accepted as arbitrary text and activated immediately. Unsupported extensions, destructive actions, resource-heavy tests, and unreviewed changes then turn a small rule edit into lost mail or delivery latency.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Language boundary

RFC 5228 defines Sieve as a limited mail-filtering language. It deliberately omits loops and variables in the core language, but scripts can still redirect, reject, discard, file messages, or cancel the implicit keep. “Not a general-purpose language” does not mean “no operational risk.”

A script declares optional capabilities with `require`. Validate those names against the extensions actually supported by the target interpreter. RFC 9122 defines the IANA registry structure for Sieve extensions and updates registration guidance; a product should not invent capability meaning from an extension-looking string.

## Controlled lifecycle

1. **Parse and validate before activation.** Reject invalid grammar, unavailable required capabilities, invalid comparators, and implementation-limit violations. Keep the currently active version unchanged on failure.
2. **Version immutable source.** Record the normalized source hash, actor, target account/domain, advertised capability set, validation result, and activation time.
3. **Apply policy above syntax.** Allow or require review for `redirect`, `reject`, and `discard`; constrain redirect destinations; and enforce tenant-specific action quotas.
4. **Set resource limits.** Bound script bytes, nesting, header/body inspection, number of actions, redirect fan-out, and execution time. Fail closed to a documented delivery-safe outcome rather than dropping a message.
5. **Use atomic activation and rollback.** Validate a candidate against the same runtime/capabilities that will execute it, then switch one active-version pointer. Keep a known-good version.
6. **Separate generated and user-authored rules.** A UI builder should round-trip its own subset without deleting unfamiliar clauses. If it cannot preserve a script, switch to read-only source mode.
7. **Audit outcomes.** Emit bounded reason codes and matched rule identifiers, not entire message bodies.

## Verification

Create table-driven fixtures for header folding, encoded display text, absent headers, multiple recipients, empty/multiple matches, extension availability, and every destructive action. Include a final-delivery assertion: either the implicit keep remains, or a deliberate action has replaced it.

Shadow-evaluate a new version against representative redacted messages before activation. Compare action plans rather than sending redirects or rejects during the shadow run.

## Gotchas

- Activating a script validated against a different capability set creates deployment-time failure.
- `stop` halts evaluation; it is not a delivery action by itself.
- Multiple actions can interact. Test the complete action plan, not each statement alone.
- Extension registries establish names and references, not product permission policy.
- Never let a validation error erase or deactivate the last known-good script.

## Sources

- [RFC 5228 — Sieve: An Email Filtering Language](https://www.rfc-editor.org/rfc/rfc5228.html)
- [RFC 9122 — IANA Registry for Sieve Extensions](https://www.rfc-editor.org/rfc/rfc9122.html)
