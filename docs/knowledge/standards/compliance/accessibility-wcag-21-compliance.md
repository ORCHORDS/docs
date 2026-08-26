# accessibility-wcag-21-compliance

**Issue:** A digital service relies on ad-hoc accessibility checks and cannot demonstrate an operational accessibility process for applicable legal and product requirements.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

Accessibility work happens only before launch or after a complaint. Automated checks pass while keyboard users, screen-reader users, or users of magnification and alternative input cannot complete essential flows.

## Root cause

WCAG success criteria guide implementation, but compliance requires a repeatable product process: scope assessment, accessible design and content, engineering checks, assistive-technology testing, defect ownership, and change evidence. The European Accessibility Act entered into application on 28 June 2025 for covered products and services in the EU; applicability must be assessed for the specific offering and jurisdiction.

**Source:** [European Commission — European Accessibility Act](https://digital-strategy.ec.europa.eu/en/news/eu-becomes-more-accessible-all) and [W3C WCAG 2.1](https://www.w3.org/TR/WCAG21/).

## Fix

- record scope and legal applicability with qualified counsel; do not assume every product has the same obligations;
- include accessibility acceptance criteria in the definition of done for each user-facing flow;
- use semantic HTML first, then accessible names, keyboard behavior, focus management, contrast, captions, error messaging, and responsive reflow;
- run automated checks in CI, but treat them as a baseline rather than proof of accessibility;
- test key journeys manually with keyboard-only navigation and relevant assistive technology;
- maintain an accessible support and feedback path, triage defects by user impact, and preserve release evidence.

## Verification

- **Keyboard:** every critical flow is usable without a pointer and focus remains visible and predictable.
- **Screen reader:** controls expose a useful name, role, state, and error message.
- **Visual:** text contrast, reflow, zoom, and non-text alternatives meet the stated design standard.
- **Regression:** CI catches high-confidence defects and manual test evidence covers high-risk releases.
- **Process:** unresolved issues have an owner, severity, target release, and user-impact description.

## Gotchas

- ARIA cannot repair incorrect native semantics or broken keyboard behavior.
- A passing automated scan does not validate reading order, meaningful alternative text, usable focus, or task completion.
- Accessibility and legal applicability vary by product and jurisdiction; record the evidence behind the decision.

## Related

- `lessons/accessibility-is-not-optional.md`
- `i18n/rtl-layout.md`
- `testing/playwright-accessibility.md`
