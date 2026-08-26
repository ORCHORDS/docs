# react-testing-patterns

**Issue:** Common patterns for testing React components effectively
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
React component tests that test implementation details (state, lifecycle methods) instead of user-visible behavior.

## Pattern / Solution
```ts
// Test what the user sees, not how state changes
it("shows validation error when email is invalid", async () => {
  const user = userEvent.setup();
  render(<SignupForm />);

  await user.type(screen.getByLabelText("Email"), "not-an-email");
  await user.tab(); // trigger blur

  expect(screen.getByRole("alert")).toHaveTextContent("Invalid email");
});

// Test conditional rendering
it("shows premium badge for premium users", () => {
  render(<UserCard user={{ tier: "premium", name: "Alice" }} />);
  expect(screen.getByText("Premium")).toBeInTheDocument();
});

// Test hooks with renderHook
import { renderHook, act } from "@testing-library/react";
it("useCounter increments correctly", () => {
  const { result } = renderHook(() => useCounter(0));
  act(() => result.current.increment());
  expect(result.current.count).toBe(1);
});
```

## Gotchas
- Do not test implementation: avoid `instance()`, `state()`, `setState()`
- `act()` wraps state updates — Testing Library wraps most automatically
- For portals/modals, assert against `document.body` or use `within`

## Related
- `testing-library-custom-render.md`
- `testing-library-async-patterns.md`
