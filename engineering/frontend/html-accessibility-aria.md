# html-accessibility-aria

**Issue:** Custom interactive components lack semantic meaning for screen readers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A custom dropdown built from divs is invisible to VoiceOver; keyboard users cannot navigate it.

## Pattern / Solution
```html
<!-- Use native elements when possible -->
<button type="button">Open menu</button>

<!-- ARIA for custom widgets -->
<div role="combobox" aria-expanded="true" aria-haspopup="listbox" aria-controls="listbox-id">
  <input aria-autocomplete="list" aria-activedescendant="opt-1">
</div>
<ul role="listbox" id="listbox-id">
  <li role="option" id="opt-1" aria-selected="true">Option 1</li>
</ul>

<!-- Live regions for dynamic content -->
<div role="status" aria-live="polite">Form saved</div>
<div role="alert" aria-live="assertive">Error: invalid input</div>
```

## Gotchas
- ARIA only changes semantics, not behaviour; keyboard handling must still be implemented
- No ARIA is better than bad ARIA
- aria-label takes precedence over aria-labelledby; use one not both
- Test with actual screen readers: VoiceOver, NVDA, JAWS

## Related
- `react-portal-patterns.md`
- `html-form-validation.md`
