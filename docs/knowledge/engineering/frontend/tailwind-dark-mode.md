# tailwind-dark-mode

**Issue:** Implementing dark mode with Tailwind without flicker or class conflicts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dark mode flickers on load because the theme is applied after hydration; or user preference is not persisted.

## Pattern / Solution
```js
// tailwind.config.js
module.exports = { darkMode: 'class' };
```

```html
<!-- Inline script in <head> to avoid FOUC -->
<script>
  const theme = localStorage.getItem('theme') ??
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.classList.toggle('dark', theme === 'dark');
</script>
```

```tsx
// Toggle
function ThemeToggle() {
  const toggle = () => {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
  };
  return <button onClick={toggle}>Toggle</button>;
}
```

## Gotchas
- The inline script must run before React hydrates to prevent flash
- media strategy (Tailwind default) cannot be programmatically toggled
- class strategy requires setting the class on <html>

## Related
- `tailwind-component-patterns.md`
- `css-custom-properties-theming.md`
