---
title: "WAI-ARIA 1.2 Conformance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# WAI-ARIA 1.2 Conformance

## Pinned standard
This article pins **WAI-ARIA 1.2, W3C Recommendation 6 June 2023**. Conformance is evaluated together with the host language and accessibility API mappings. Authors must not use abstract roles, must supply required states/properties, must keep values valid, and must not expose elements whose semantics conflict with host-language restrictions.

## Role contracts
A `checkbox` requires `aria-checked`; `slider` requires `aria-valuemin`, `aria-valuemax`, and `aria-valuenow`; `scrollbar` additionally requires `aria-controls`; `heading` uses `aria-level` when host semantics do not supply a level. Composite widgets impose ownership: `listbox` owns `option`, `tablist` owns `tab`, `tree` owns `treeitem`, and `grid` owns rows containing gridcells, columnheaders, or rowheaders. `aria-owns` changes accessibility-tree ownership and must not create cycles or duplicate ownership.

States must track behavior: a disclosure button updates `aria-expanded`; selection uses the role-appropriate `aria-selected` or `aria-checked`; `aria-disabled` does not disable events and therefore needs behavior enforcement. `aria-activedescendant` identifies an owned or logically controlled active item while DOM focus remains on the composite. ID references must resolve uniquely.

## Widget verification
Prefer native HTML first. For every custom widget, map role, accessible name, required properties, supported states, owned elements, keyboard model, focus strategy, and expected accessibility-tree node. Exercise every state transition and inspect the computed tree in two browser/platform combinations. Confirm invalid ARIA values do not silently create an unintended fallback. Test generated, empty, loading, disabled, readonly, multiselect, and virtualized states.

A tab implementation must expose a named `tablist`, one `tab` with `aria-selected=true`, the others false, and each tab’s `aria-controls` relationship to a `tabpanel`; roving tabindex or `aria-activedescendant` must yield one keyboard focus stop. A combobox must use the 1.2 `combobox` contract, identify the popup with `aria-controls`, expose expansion, and synchronize active option and input value.

## Failure evidence
Retain DOM excerpt, computed role/name/states, accessibility-tree capture, keyboard transcript, browser/AT versions, and the violated role definition. Flag abstract roles, missing required properties, prohibited states, stale expanded/selected values, duplicate IDs, broken ownership, and ARIA that overrides functioning native semantics.

## Sources
- [WAI-ARIA 1.2 Recommendation](https://www.w3.org/TR/2023/REC-wai-aria-1.2-20230606/)
- [ARIA 1.2 roles model](https://www.w3.org/TR/wai-aria-1.2/#roles)
