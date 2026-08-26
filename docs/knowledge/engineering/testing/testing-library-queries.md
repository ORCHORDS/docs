# testing-library-queries

**Issue:** Choosing the right Testing Library query to find DOM elements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Using `querySelector` or `getByTestId` everywhere instead of semantic queries that test accessibility.

## Pattern / Solution
Priority order (highest to lowest):
1. `getByRole` — prefer always, uses ARIA roles
2. `getByLabelText` — for form inputs
3. `getByPlaceholderText` — fallback for inputs
4. `getByText` — for text content
5. `getByDisplayValue` — for select/input current values
6. `getByAltText` — for images
7. `getByTitle` — for title attributes
8. `getByTestId` — last resort

```ts
// GOOD
screen.getByRole("button", { name: /submit/i });
screen.getByLabelText("Email address");
screen.getByRole("dialog", { name: "Confirm deletion" });

// BAD
screen.getByTestId("submit-btn");
container.querySelector(".btn-primary");
```

Variant prefixes: `get` (throws), `query` (null), `find` (async).

## Gotchas
- `getAllByRole` returns array — use when multiple matches expected
- `findBy*` returns Promise — use for elements that appear asynchronously
- Custom roles require `aria-label` or `aria-labelledby`

## Related
- `testing-library-user-event.md`
- `testing-library-accessibility-queries.md`
