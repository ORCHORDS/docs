---
title: "ARIA in HTML Conformance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# ARIA in HTML Conformance

## Pinned specification
This article pins **ARIA in HTML, W3C Recommendation 5 August 2025**. It defines which ARIA roles and attributes authors may use on HTML elements. Browser repair behavior does not make nonconforming markup acceptable.

## Author rules
Do not repeat an element’s implicit role unless a documented exception makes it necessary. Do not use `role="presentation"` or `none` where descendants or focusability require semantics; focusable elements cannot be made presentational. An author-provided role must be one permitted for that HTML element. Strong native semantics—such as form controls—cannot be replaced arbitrarily. Global `aria-*` attributes are not universally valid when the element’s role prohibits them, and role-specific states must be supported by the final computed role.

Use native `button`, `a[href]`, `input`, `select`, headings, tables, and landmarks before adding roles to generic containers. A `div role=button` inherits no click activation, Enter/Space behavior, disabled behavior, form behavior, or focusability from ARIA. An `input type=checkbox` already has checkbox semantics and should not be relabeled as a switch unless the specification’s permitted-role table allows that use and the product truly presents switch behavior.

## Conformance procedure
For each element carrying `role` or `aria-*`, determine its HTML element/type/state, implicit role, permitted explicit roles, prohibited naming status, and supported properties from the pinned recommendation tables. Run the Nu HTML Checker, but review computed role manually because templating and runtime state may differ from static source. Inspect two accessibility trees and exercise native keyboard, activation, form submission, constraint validation, and disabled behavior after any override.

Create negative fixtures for an invalid role, multiple role tokens with fallback, prohibited naming, `aria-hidden=true` on focusable content, presentational tables with semantic descendants, and role/state mismatch. Confirm the checker flags author errors even where a browser chooses a fallback role.

## Evidence
Retain the exact table row or rule, serialized runtime DOM, checker output, computed accessibility node, and behavior transcript. Findings should distinguish HTML conformance errors from interoperability defects. Common failures are adding `role=button` to a button, naming elements whose semantics prohibit naming, using `aria-checked` on a role that does not support it, and suppressing native semantics while leaving keyboard focus.

## Sources
- [ARIA in HTML Recommendation, 5 August 2025](https://www.w3.org/TR/2025/REC-html-aria-20250805/)
- [Rules of ARIA attribute usage](https://www.w3.org/TR/html-aria/#docconformance)
