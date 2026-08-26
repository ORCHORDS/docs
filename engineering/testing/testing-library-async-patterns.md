# testing-library-async-patterns

**Issue:** Testing components with async data loading, transitions, and side effects
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests fail with `act()` warnings or elements not found because async state updates are not awaited properly.

## Pattern / Solution
```ts
import { render, screen, waitFor, waitForElementToBeRemoved } from "@testing-library/react";

it("loads and displays users", async () => {
  render(<UserList />);

  // Wait for loading state to disappear
  await waitForElementToBeRemoved(() => screen.queryByText("Loading..."));

  // Or wait for element to appear
  const users = await screen.findAllByRole("listitem");
  expect(users).toHaveLength(3);
});

it("shows error on failed fetch", async () => {
  server.use(http.get("/api/users", () => HttpResponse.error()));
  render(<UserList />);

  await waitFor(() => {
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
```

`waitFor` retries until assertion passes or times out (default 1000ms).

## Gotchas
- Wrap multiple assertions in single `waitFor` to avoid false intermediate failures
- `findBy*` = `waitFor` + `getBy*` combined — prefer for single element waits
- Set `server.resetHandlers()` in afterEach when using MSW

## Related
- `testing-library-user-event.md`
- `mock-server-msw.md`
