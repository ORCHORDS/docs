# Safety and Accessibility Invariants Must Cross Every Shell

**Issue:** A secondary web, mobile, desktop, or embedded shell may omit help, accessible authentication, account recovery, session control, data export, or account deletion even when its primary product features appear complete.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Define non-negotiable accessibility and account-safety outcomes above the presentation layer. Each supported shell must provide them directly or a tested, understandable handoff that preserves identity, state, and accessibility.

## Controls

- Inventory help, sign-in, step-up, recovery, credential change, active-session review, sign-out, export, and deletion as complete processes.
- Set shared invariants for authorization, user confirmation, error prevention, recovery evidence, notification, and audit logging.
- Apply the accessibility target to every responsive variation and every step in a complete process.
- Keep help mechanisms consistently identifiable and ordered within each shell.
- Avoid authentication tasks that depend on memory, transcription, puzzles, or a single sensory or motor interaction unless an accessible alternative meets policy.
- Test cross-shell handoffs for redirect integrity, preserved context, deep-link ownership, cancellation, and safe return.
- Prevent a “use desktop” escape hatch from becoming the only route for a safety-critical action without explicit scope and accommodation.

## Verification

- Run complete assistive-technology journeys for authentication, recovery, support, export, and deletion on every supported shell.
- Compare authorization and audit events for equivalent actions across shells.
- Interrupt and resume a cross-shell handoff and verify no duplicate, lost, or misdirected action.
- Confirm help and recovery remain reachable from failure and locked-account states.

## Gotchas

WCAG conformance applies to complete processes and responsive variations, not just a representative screen. A handoff can be valid, but requiring another device, inaccessible authentication, or lost context may defeat the invariant.

## Official sources

- [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [Apple accessibility guidance](https://developer.apple.com/design/human-interface-guidelines/accessibility/)
