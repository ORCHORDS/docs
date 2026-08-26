# unit-test-test-doubles

**Issue:** Choosing the right kind of test double (mock, stub, spy, fake, dummy)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Misusing mocks everywhere causes tests that verify the wrong thing or are impossible to read.

## Pattern / Solution
Types of test doubles:
- **Dummy**: passed but never used (fills parameter slots)
- **Stub**: returns canned answers to calls
- **Spy**: records calls, delegates to real implementation
- **Mock**: pre-programmed with expectations
- **Fake**: working implementation, simplified (in-memory DB)

```ts
// Stub
const repo = { findById: vi.fn().mockResolvedValue({ id: 1 }) };

// Spy
const spy = vi.spyOn(console, "error");
doThing();
expect(spy).toHaveBeenCalled();

// Fake
class InMemoryUserRepo implements UserRepo {
  private users = new Map();
  async save(u: User) { this.users.set(u.id, u); }
  async findById(id: string) { return this.users.get(id); }
}
```

## Gotchas
- Mocks couple tests to implementation — prefer fakes or stubs
- Never mock the system under test itself
- Reset mocks between tests to avoid bleed

## Related
- `mocking-vs-stubbing-vs-spying.md`
- `jest-module-mocking.md`
