# component-testing-storybook

**Issue:** Using Storybook as a component testing platform alongside unit tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Component tests in Jest don't catch visual or interaction issues. Storybook provides a living test environment with interaction tests.

## Pattern / Solution
```ts
// Button.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { userEvent, within, expect } from "@storybook/test";
import { Button } from "./Button";

const meta: Meta<typeof Button> = { component: Button };
export default meta;
type Story = StoryObj<typeof Button>;

export const ClickInteraction: Story = {
  args: { label: "Click me" },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = canvas.getByRole("button", { name: "Click me" });
    await userEvent.click(button);
    await expect(button).toHaveAttribute("aria-pressed", "true");
  },
};
```

Run interaction tests in CI:
```bash
npx storybook build
npx concurrently -k "npx http-server storybook-static" "npx wait-on http://localhost:8080 && npx test-storybook"
```

## Gotchas
- Storybook tests do not replace unit tests — complement them
- Stories are also documentation — keep them up to date
- MSW addon integrates with `msw` for API mocking in stories

## Related
- `react-testing-patterns.md`
- `visual-regression-testing-percy.md`
