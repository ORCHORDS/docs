# snapshot-testing-pitfalls

**Issue:** Avoiding common snapshot testing anti-patterns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Snapshots become a rubber-stamp — developers run `--updateSnapshot` without reviewing what changed, defeating the purpose.

## Pattern / Solution
Anti-patterns to avoid:
```ts
// BAD: entire component snapshot is too large
expect(screen.getByTestId("dashboard")).toMatchSnapshot();

// BAD: snapshot includes timestamps, IDs — always different
expect(apiResponse).toMatchSnapshot(); // has createdAt: "2026-..."

// GOOD: snapshot only stable output
expect(formatCurrency(1234.56)).toMatchInlineSnapshot(`"$1,234.56"`);

// GOOD: exclude dynamic fields
expect(response).toMatchSnapshot({
  id: expect.any(String),
  createdAt: expect.any(String),
});
```

Code review checklist for snapshot updates:
- Is the change intentional?
- Does the new snapshot reflect correct behavior?
- Is the snapshot diff readable?

## Gotchas
- Never use `--updateSnapshot` in CI
- Large snapshots cause merge conflicts that are impossible to review
- Use inline snapshots for outputs under 20 lines

## Related
- `jest-snapshot-testing.md`
- `approval-testing.md`
- `golden-master-testing.md`
