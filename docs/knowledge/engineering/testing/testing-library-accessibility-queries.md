# testing-library-accessibility-queries

**Issue:** Using ARIA roles and labels for queries that also verify accessibility
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Components pass tests but are inaccessible — screen readers cannot navigate them because tests use CSS selectors instead of ARIA queries.

## Pattern / Solution
```ts
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe"; // or vitest-axe

it("navigation has correct ARIA landmark", () => {
  render(<Navigation />);
  expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
});

it("modal traps focus and has accessible name", () => {
  render(<ConfirmDialog title="Delete file?" />);
  const dialog = screen.getByRole("dialog", { name: "Delete file?" });
  expect(dialog).toBeInTheDocument();
  expect(dialog).toHaveFocus();
});

it("has no accessibility violations", async () => {
  const { container } = render(<Form />);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

Common roles: `button`, `link`, `heading`, `list`, `listitem`, `dialog`, `alert`, `navigation`, `main`, `form`.

## Gotchas
- `role="button"` on a `<div>` won't be keyboard-accessible — test keyboard interaction too
- `aria-hidden` elements are not queryable by role
- `getByRole("heading", { level: 2 })` matches `<h2>` specifically

## Related
- `testing-library-queries.md`
- `a11y-automated-testing-axe.md`
