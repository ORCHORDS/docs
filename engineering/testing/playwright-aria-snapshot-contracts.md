# Playwright ARIA snapshot contracts

**Issue:** DOM or screenshot assertions can pass while a control's computed role, accessible name, hierarchy, or state changes for assistive-technology users.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `toMatchAriaSnapshot()` on a bounded landmark, dialog, menu, or widget whose accessible structure is a reviewed interface. Prefer stable roles, names, and states over incidental wrapper text. Choose `/children` matching deliberately: containment tolerates unrelated descendants, while equal or deep-equal modes make child structure part of the contract. Use regular expressions only for genuinely dynamic accessible names.

Keep snapshot updates in reviewed diffs; never run `--update-snapshots` as an automatic green-build repair. Generate external YAML snapshots when ownership and change review benefit from a dedicated file, and use one browser-independent baseline unless a proven platform accessibility-tree difference requires a scoped exception.

## Verification

Mutate a role, label, expanded/selected state, heading level, ordering, and hidden content and require the intended failures. Run keyboard, focus, contrast, zoom, and screen-reader checks separately because an ARIA snapshot is neither a visual snapshot nor a complete accessibility audit.

## Gotchas

- A matching accessibility tree does not prove the interaction works.
- Overly broad snapshots create noisy churn and invite blind regeneration.
- Invalid ARIA can change the computed tree rather than the DOM attribute you expected.

## Official source

- [Playwright ARIA snapshot testing](https://playwright.dev/docs/aria-snapshots)
