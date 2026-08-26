# css-custom-properties-theming

**Issue:** Hard-coded colour values make theme switching require full stylesheet replacement
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Implementing dark mode requires duplicating every colour rule inside a .dark selector.

## Pattern / Solution
```css
:root {
  --color-bg: #ffffff;
  --color-text: #1a1a1a;
  --color-primary: #3b82f6;
  --radius-md: 8px;
  --spacing-4: 1rem;
}

[data-theme="dark"] {
  --color-bg: #0f172a;
  --color-text: #f1f5f9;
  --color-primary: #60a5fa;
}

.button {
  background: var(--color-primary);
  border-radius: var(--radius-md);
  color: #fff;
}
```

```ts
// Programmatic theme switch
document.documentElement.setAttribute('data-theme', 'dark');
```

## Gotchas
- Custom properties are inherited; set on :root to make globally available
- Fallback: var(--color-text, black) in case the property is not set
- calc() works with custom properties: calc(var(--spacing-4) * 2)

## Related
- `tailwind-dark-mode.md`
- `css-cascade-layers.md`
