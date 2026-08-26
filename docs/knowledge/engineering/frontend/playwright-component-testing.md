# playwright-component-testing

**Issue:** Unit tests with jsdom miss real browser rendering bugs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A CSS-in-JS bug manifests only in a real browser but passes in jsdom-based tests.

## Pattern / Solution
```ts
// Button.test.ts (Playwright Component Test)
import { test, expect } from '@playwright/experimental-ct-react';
import { Button } from './Button';

test('renders primary variant', async ({ mount }) => {
  const component = await mount(<Button variant="primary">Click me</Button>);
  await expect(component).toHaveClass(/btn--primary/);
  await expect(component).toBeVisible();
  await component.click();
  await expect(component).not.toHaveAttribute('aria-busy', 'true');
});

test('snapshot', async ({ mount, page }) => {
  await mount(<Button variant="primary">Click me</Button>);
  await expect(page).toHaveScreenshot();
});
```

## Gotchas
- Requires Vite or webpack config; slower than jsdom tests
- Use for integration tests of interactive components, not pure unit tests
- Screenshots need to be updated when component visuals change intentionally

## Related
- `storybook-component-driven.md`
- `testing-library-patterns.md`
