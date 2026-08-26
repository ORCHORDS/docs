# feature-cookbook-testing-frontend

**Issue:** Frontend testing — components, hooks, E2E
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write component tests. They take 5 seconds each. They
break on every refactor. You skip them. You ship broken
UI. You wish you had a fast, reliable test setup.

## Root cause
**Frontend tests are slow and fragile.** Without good
patterns, they're a maintenance burden.

**Source:** Various frontend testing guides.

## The "component test" pattern

For a React component:
```tsx
import { render, screen } from '@testing-library/react';
import { UserCard } from './UserCard';

test('renders the user name', () => {
  render(<UserCard user={{ id: 'u_1', displayName: 'Alice' }} />);
  expect(screen.getByText('Alice')).toBeInTheDocument();
});

test('renders the email when provided', () => {
  render(<UserCard user={{ id: 'u_1', displayName: 'Alice', email: 'a@x.test' }} />);
  expect(screen.getByText('a@x.test')).toBeInTheDocument();
});

test('handles click', async () => {
  const onClick = vi.fn();
  render(<UserCard user={...} onClick={onClick} />);
  await userEvent.click(screen.getByRole('button'));
  expect(onClick).toHaveBeenCalled();
});
```

The test is fast (~1ms); the assertions are user-centric.

## The "hook test" pattern

For a custom hook:
```tsx
import { renderHook, act } from '@testing-library/react';
import { useCounter } from './useCounter';

test('useCounter increments', () => {
  const { result } = renderHook(() => useCounter(0));

  act(() => result.current.increment());

  expect(result.current.count).toBe(1);
});
```

The hook is tested in isolation.

## The "mock" pattern for components

For a component that uses a context:
```tsx
import { ThemeContext } from './ThemeContext';

test('renders in dark mode', () => {
  render(
    <ThemeContext.Provider value="dark">
      <MyComponent />
    </ThemeContext.Provider>
  );
  expect(screen.getByTestId('component')).toHaveClass('dark');
});
```

The context is provided.

## The "MSW" pattern for API mocking

For API mocking:
```ts
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

const server = setupServer(
  http.get('/api/users/u_1', () => {
    return HttpResponse.json({ id: 'u_1', displayName: 'Alice' });
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());

test('loads the user', async () => {
  render(<UserProfile userId="u_1" />);

  expect(await screen.findByText('Alice')).toBeInTheDocument();
});
```

The API is mocked at the network level.

## The "snapshot" pattern

For visual regression:
```tsx
test('matches snapshot', () => {
  const { container } = render(<UserCard user={...} />);
  expect(container).toMatchSnapshot();
});
```

Update with: `vitest --update`.

## The "Playwright" pattern

For E2E:
```ts
import { test, expect } from '@playwright/test';

test('user can log in', async ({ page }) => {
  await page.goto('/login');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'password');
  await page.click('button[type="submit"]');

  await expect(page).toHaveURL(/dashboard/);
});
```

The test runs in a real browser.

## The "accessibility test" pattern

For a11y:
```ts
import AxeBuilder from '@axe-core/playwright';

test('page is accessible', async ({ page }) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

The test catches a11y issues.

## The "visual regression" pattern

For visual snapshots:
```ts
test('homepage visual snapshot', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveScreenshot('homepage.png');
});
```

The visual is compared.

## The "test isolation" pattern

For test isolation:
```ts
beforeEach(() => {
  // Reset the global state
  resetStores();

  // Mock the time
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-08-09'));
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});
```

Each test is isolated.

## The "user event" pattern

For user interactions:
```tsx
import userEvent from '@testing-library/user-event';

test('typing in the input updates the value', async () => {
  const user = userEvent.setup();
  render(<Input />);

  const input = screen.getByRole('textbox');
  await user.type(input, 'Hello');

  expect(input).toHaveValue('Hello');
});
```

The test simulates user behavior.

## The "async test" pattern

For async UI:
```tsx
import { findByText, waitFor } from '@testing-library/react';

test('shows loading then content', async () => {
  render(<AsyncUserCard userId="u_1" />);

  // Wait for the loading to finish
  expect(await screen.findByText('Alice')).toBeInTheDocument();
});
```

The test waits for the UI to update.

## The "form test" pattern

For a form:
```tsx
test('submits the form', async () => {
  const onSubmit = vi.fn();
  const user = userEvent.setup();

  render(<MyForm onSubmit={onSubmit} />);

  await user.type(screen.getByLabelText('Email'), 'a@x.test');
  await user.type(screen.getByLabelText('Password'), 'password');
  await user.click(screen.getByRole('button', { name: 'Submit' }));

  expect(onSubmit).toHaveBeenCalledWith({
    email: 'a@x.test',
    password: 'password',
  });
});
```

The form submission is tested.

## The "router test" pattern

For routing:
```tsx
import { MemoryRouter } from 'react-router-dom';

test('renders the user page', () => {
  render(
    <MemoryRouter initialEntries={['/users/u_1']}>
      <App />
    </MemoryRouter>
  );

  expect(screen.getByText('Alice')).toBeInTheDocument();
});
```

The router is mocked with MemoryRouter.

## The "i18n test" pattern

For i18n:
```tsx
import { I18nextProvider } from 'react-i18next';
import i18next from 'i18next';

i18next.init({ lng: 'es', resources: { es: { translation: { greeting: 'Hola' } } } });

test('renders in Spanish', () => {
  render(
    <I18nextProvider i18n={i18next}>
      <Greeting />
    </I18nextProvider>
  );

  expect(screen.getByText('Hola')).toBeInTheDocument();
});
```

The locale is set.

## Verification
- **Test:** Component tests pass
- **Test:** E2E tests pass
- **Live:** CI is fast
- **Audit:** Quarterly review of test patterns

## Gotchas
- **The "snapshot for everything" anti-pattern.** Snapshots
  catch everything; the noise is too much.
- **The "no user-centric" anti-pattern.** Tests that check
  implementation, not user behavior, are fragile.
- **The "real network in tests" anti-pattern.** Mock the
  network; don't make real calls.
- **The "no cleanup" anti-pattern.** Tests that leak state
  are flaky.
- **The "slow tests" anti-pattern.** Tests that take
  > 1s slow the CI.

## Related
- `unit-testing-patterns.md`
- `e2e-testing-patterns.md`
- `test-data-management.md`
- `feature-cookbook-frontend.md`
- `accessibility-wcag-detail.md`
- `visual-regression-testing.md`
- React Testing Library: https://testing-library.com/docs/react-testing-library/intro/
- Vitest: https://vitest.dev/
- Playwright: https://playwright.dev/
- MSW: https://mswjs.io/
