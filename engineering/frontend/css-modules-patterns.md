# css-modules-patterns

**Issue:** Global CSS class names cause unintentional style collisions in large apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Two components define .button and the last imported stylesheet wins, breaking the first component.

## Pattern / Solution
```css
/* Button.module.css */
.button { padding: 8px 16px; }
.primary { background: blue; color: white; }
.secondary { background: gray; }
```

```tsx
import styles from './Button.module.css';
import clsx from 'clsx';

function Button({ variant = 'primary', className }) {
  return (
    <button className={clsx(styles.button, styles[variant], className)}>
      Click me
    </button>
  );
}
```

## Gotchas
- :global(.foo) escapes the module scope; use sparingly
- Composition with composes: BaseButton from './base.module.css'
- TypeScript: add declare module '*.module.css' or use typed-css-modules

## Related
- `css-in-js-tradeoffs.md`
- `tailwind-component-patterns.md`
