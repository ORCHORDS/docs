# storybook-component-driven

**Issue:** Components are developed in the context of full pages, making isolation and edge-case testing difficult
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Testing an error state of a Card requires navigating to a page where that state can be triggered, rather than isolating it.

## Pattern / Solution
```ts
// Button.stories.ts
import type { Meta, StoryObj } from '@storybook/react';
import { Button } from './Button';

const meta: Meta<typeof Button> = {
  component: Button,
  args: { children: 'Click me' },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = { args: { variant: 'primary' } };
export const Loading: Story = { args: { loading: true } };
export const Disabled: Story = { args: { disabled: true } };
```

## Gotchas
- Use play functions for interaction testing within Storybook
- MSW addon mocks API calls in stories without a real server
- args and argTypes enable interactive controls in the Storybook UI

## Related
- `chromatic-visual-testing.md`
- `testing-library-patterns.md`
