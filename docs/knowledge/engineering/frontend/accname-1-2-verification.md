---
title: "Accessible Name and Description Computation 1.2"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Accessible Name and Description Computation 1.2

## Pinned algorithm
This article pins **Accessible Name and Description Computation 1.2, W3C Working Draft 27 August 2026**. It is not a Recommendation; assessments must record this dated draft because algorithm details may change. User agents compute a flat string by running the name or description computation with a current node, traversal context, and visited-node set. Authors should test the computed result, not infer it from visual text.

## Name computation walkthrough
The algorithm first handles hidden nodes: hidden content contributes nothing unless reached through an `aria-labelledby` or `aria-describedby` traversal that permits hidden referenced content. It then evaluates naming mechanisms according to role and host-language rules. `aria-labelledby` references are followed in IDREF order; each referenced node is computed and concatenated, and already-visited references prevent loops. A non-empty `aria-label` supplies a string when permitted. Host-language label mechanisms, such as an HTML `label`, `alt`, or caption rule, are then considered according to the HTML accessibility mapping.

For roles that allow **name from content**, child text and eligible descendant contributions are accumulated in rendered order. Embedded controls inside a label contribute their value: a textbox contributes its value, a combobox/listbox its selected option, and a range control its value text or value. CSS generated content may contribute where the algorithm specifies. Whitespace is normalized into the final flat string. Description computation uses `aria-describedby`, `aria-description`, and host-language description features under its own precedence; it must not be assumed to append automatically to the name.

## Targeted tests
Create fixtures for `aria-labelledby` with multiple IDs, hidden referenced labels, cyclic references, duplicate references, an empty `aria-label`, native `label`, image `alt`, name-from-content buttons, and labels containing embedded controls. For each fixture, record expected token order and normalized output, then compare browser accessibility trees in at least two engines. Change referenced text dynamically and verify recomputation.

Test precedence explicitly: add visible text, `aria-label`, and `aria-labelledby`, then remove each mechanism in turn. Verify speech-input label-in-name separately; a technically computed name that omits visible wording can still violate WCAG 2.5.3. Do not confuse placeholder text with a reliable HTML label.

## Failure analysis
Capture source DOM, role, computation path, visited references, final name, final description, browser build, and accessibility API output. Typical defects are dangling IDs, cycles, hidden content wrongly omitted from an explicit reference, whitespace surprises, empty author names suppressing native text, and state text embedded in names so announcements become stale.

## Sources
- [AccName 1.2 Working Draft, 27 August 2026](https://www.w3.org/TR/2026/WD-accname-1.2-20260827/)
- [Name and Description Computation](https://www.w3.org/TR/accname-1.2/#mapping_additional_nd_name)
