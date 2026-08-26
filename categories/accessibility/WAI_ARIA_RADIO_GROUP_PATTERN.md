---
title: "WAI-ARIA Radio Group Pattern"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WAI-ARIA Radio Group Pattern

## Purpose

Provide public implementation guidance for mutually exclusive choices using the WAI-ARIA Authoring Practices Guide radio group pattern.

## Pattern baseline

A radio group presents a set of choices where selecting one option normally deselects the previously selected option.

Accessible implementations should:

- prefer native HTML radio controls when native behavior meets the requirement;
- group custom radios with `role="radiogroup"` and give the group an accessible name;
- expose each custom option with `role="radio"`;
- use `aria-checked="true"` for the selected option and `false` for the others;
- ensure only one radio in a single-select group is selected at a time;
- manage keyboard focus predictably across the set.

## Keyboard interaction

Common interaction includes `Space` to check the focused radio and arrow keys to move focus and selection among radios. `Tab` enters or leaves the group rather than stepping through every option individually when roving focus is used.

## Implementation guidance

1. Use native `<input type="radio">` and `<fieldset>`/`<legend>` grouping wherever practical.
2. Keep visual selection, focus, and `aria-checked` synchronized.
3. Ensure arrow-key behavior follows the documented orientation and does not trap users unexpectedly.
4. Provide clear group-level instructions when the choice has unusual consequences or validation rules.
5. Test initial focus when no option is selected and after validation errors.

## Verification

Confirm that the group has a meaningful accessible name, exactly one selected state is exposed where required, arrow-key movement is predictable, `Space` selects the focused option, and tab order enters and exits the group correctly.

## Source

- W3C WAI-ARIA Authoring Practices Guide, **Radio Group Pattern**: https://www.w3.org/WAI/ARIA/apg/patterns/radio/
