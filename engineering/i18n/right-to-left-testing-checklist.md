# right-to-left-testing-checklist

**Issue:** Systematic checklist for QA testing RTL language support in web applications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
RTL bugs are often missed in standard QA because most testers default to LTR. A dedicated checklist ensures coverage of the common failure modes.

## Pattern / Solution
Layout checks:
- [ ] Page direction (`dir="rtl"`) set on `<html>` element
- [ ] Navigation bar mirrors correctly (logo right, links left)
- [ ] Sidebar appears on the correct side
- [ ] Breadcrumbs read right-to-left
- [ ] Form labels aligned to the right of inputs
- [ ] Checkboxes and radio buttons appear to the right of their labels
- [ ] Progress bars fill from right to left
- [ ] Dropdown menus open to the correct side
- [ ] Tooltips and popovers positioned correctly

Text checks:
- [ ] Arabic/Hebrew text renders with proper letter joining (not isolated letters)
- [ ] Numbers display in correct numeral system (Arabic-Indic vs Western)
- [ ] Dates formatted per locale convention
- [ ] Text is not cut off by fixed-width containers

Icons and images:
- [ ] Directional icons (arrows, chevrons) are mirrored
- [ ] Non-directional icons (email, phone) are not mirrored
- [ ] Images with embedded text have localized versions

## Gotchas
- Chrome DevTools can emulate RTL via `document.documentElement.dir = 'rtl'` for quick checks
- Physical CSS properties (`margin-left`) often pass visual inspection but fail when locale switches dynamically
- Test with real Arabic/Hebrew content, not placeholder Latin text

## Related
- `bidi-rtl-layout-css.md`
- `i18n-rtl-testing-2026.md`
- `rtl-bidi-testing-2026.md`
