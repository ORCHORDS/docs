# jest-snapshot-testing

**Issue:** Using snapshots effectively without creating brittle, noisy tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Snapshot files grow huge, diffs are meaningless, and developers blindly update snapshots without reviewing changes.

## Pattern / Solution
```ts
// Component snapshot
import { render } from "@testing-library/react";
it("renders error state", () => {
  const { container } = render(<Alert type="error" message="Oops" />);
  expect(container.firstChild).toMatchSnapshot();
});

// Inline snapshot — preferred for small outputs
it("formats user name", () => {
  expect(formatName({ first: "Ada", last: "Lovelace" })).toMatchInlineSnapshot(
    `"Lovelace, Ada"`
  );
});

// Object snapshot for API responses
expect(transformResponse(raw)).toMatchSnapshot({
  createdAt: expect.any(String), // dynamic fields
});
```

Update intentionally: `jest --updateSnapshot` or `jest -u`.

## Gotchas
- Never commit snapshot updates without reading the diff
- Large HTML snapshots hide meaningful changes
- Inline snapshots are better for small, readable outputs

## Related
- `snapshot-testing-pitfalls.md`
- `approval-testing.md`
