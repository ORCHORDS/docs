# testing-library-user-event

**Issue:** Simulating real user interactions instead of raw fireEvent calls
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`fireEvent.click()` fires a single event. Real users trigger `pointerover`, `pointerenter`, `mouseover`, `mouseenter`, `pointermove`, `mousemove`, `pointerdown`, `mousedown`, `pointerup`, `mouseup`, `click` in sequence. `userEvent` replicates this.

## Pattern / Solution
```bash
npm install -D @testing-library/user-event
```

```ts
import userEvent from "@testing-library/user-event";

// Setup (v14+) — call outside tests for better performance
const user = userEvent.setup();

it("submits the form", async () => {
  render(<LoginForm onSubmit={onSubmit} />);

  await user.type(screen.getByLabelText("Email"), "test@example.com");
  await user.type(screen.getByLabelText("Password"), "secret");
  await user.click(screen.getByRole("button", { name: /login/i }));

  expect(onSubmit).toHaveBeenCalledWith({
    email: "test@example.com",
    password: "secret",
  });
});
```

Keyboard interactions:
```ts
await user.keyboard("{Tab}{Enter}");
await user.selectOptions(screen.getByRole("combobox"), "option-value");
```

## Gotchas
- All userEvent methods are async — always `await`
- `userEvent.setup()` should be called once per test suite for perf
- Use `fireEvent` only when you specifically need a single synthetic event

## Related
- `testing-library-queries.md`
- `testing-library-async-patterns.md`
