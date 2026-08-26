# accessibility-testing-workflow

**Issue:** Accessibility is treated as a final audit, not a development practice, resulting in expensive rework
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The team ships a feature, then an audit reveals 40 accessibility violations. Fixing them requires changes to component structure that affects other features. The "accessibility sprint" becomes a significant unplanned investment.

## Pattern / Solution
Integrate accessibility testing at every layer of development.

**Layer 1: Developer (in-editor / local dev)**
- ESLint plugin: `eslint-plugin-jsx-a11y` for React; `axe-linter` for HTML
- Browser extensions: `axe DevTools`, `WAVE` for manual spot-check
- Screen reader smoke test: macOS VoiceOver or NVDA (Windows) on every new UI component

**Layer 2: Component / unit tests**
- `jest-axe`: `expect(await axe(container)).toHaveNoViolations()`
- Add axe assertion to every Storybook story via `storybook-addon-a11y`

**Layer 3: CI (automated)**
- `axe-core` via Playwright or Cypress on key user flows
- Fail builds on WCAG 2.1 AA violations with severity "critical" or "serious"
- Use `@axe-core/cli` for static HTML pages

**Manual testing checklist (per feature):**
- [ ] All interactive elements reachable by keyboard (Tab, Enter, Space, Escape)
- [ ] Focus order is logical
- [ ] All images have descriptive `alt` text (or `alt=""` for decorative images)
- [ ] Color contrast ratio ≥ 4.5:1 for normal text, ≥ 3:1 for large text
- [ ] Error messages are associated with their form field (`aria-describedby`)
- [ ] Page has one `<h1>`, headings are hierarchical
- [ ] Dynamic content changes announced to screen readers (`aria-live`)

**Definition of Done addition:**
Add "axe scan passes in CI and keyboard navigation verified manually" to the team's DoD.

## Gotchas
- Automated tools catch only ~30-40% of accessibility issues; manual testing is required
- `aria-label` overuse can hurt screen reader UX — prefer semantic HTML first
- Color contrast failures are the most common automated find; fix design tokens at the source

## Related
- `definition-of-done-checklist.md`
- `shift-left-security-testing.md`
- `performance-budget-workflow.md`
