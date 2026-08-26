# testing-library-patterns

**Issue:** Tests tightly coupled to implementation details break on safe refactors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Selecting by CSS class name means the test breaks when a class is renamed even though behaviour is unchanged.

## Pattern / Solution
```tsx
import { render, screen, userEvent } from '@testing-library/react';

test('submits the form', async () => {
  const onSubmit = vi.fn();
  render(<LoginForm onSubmit={onSubmit} />);

  await userEvent.type(screen.getByLabelText('Email'), 'test@example.com');
  await userEvent.type(screen.getByLabelText('Password'), 'secret');
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

  expect(onSubmit).toHaveBeenCalledWith({ email: 'test@example.com', password: 'secret' });
});
```

Priority order for queries:
getByRole > getByLabelText > getByPlaceholderText > getByText > getByTestId

## Gotchas
- getByRole is the most accessible and most resilient query
- Avoid getByTestId unless no semantic query exists
- userEvent from @testing-library/user-event simulates real events; better than fireEvent

## Related
- `msw-api-mocking.md`
- `playwright-component-testing.md`
