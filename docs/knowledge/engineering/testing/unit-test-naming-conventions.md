# unit-test-naming-conventions

**Issue:** Inconsistent test names make failures hard to diagnose
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests named `test1`, `should work`, or `it renders` give no information when they fail in CI.

## Pattern / Solution
Use the pattern: `[unit] [scenario] [expected outcome]`

```ts
// Jest / Vitest
describe("UserService", () => {
  describe("getUser", () => {
    it("returns user object when ID exists", async () => { ... });
    it("throws NotFoundError when ID is missing", async () => { ... });
    it("returns cached result on second call", async () => { ... });
  });
});
```

BDD style with `given/when/then` in describe blocks:
```ts
describe("given an authenticated user", () => {
  describe("when they request their profile", () => {
    it("then returns full profile data", () => { ... });
  });
});
```

## Gotchas
- Avoid vague words: `correctly`, `properly`, `works`
- Don't include `should` — it adds noise without meaning
- Keep names stable — renaming breaks CI history

## Related
- `unit-test-arrange-act-assert.md`
- `test-naming-best-practices.md`
