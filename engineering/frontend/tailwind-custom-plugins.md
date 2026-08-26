# tailwind-custom-plugins

**Issue:** Repeating design system patterns across utility classes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The same focus ring, scrollbar hide, or text gradient utilities are copy-pasted across components.

## Pattern / Solution
```js
// tailwind.config.js
const plugin = require('tailwindcss/plugin');

module.exports = {
  plugins: [
    plugin(function ({ addUtilities, addComponents, theme }) {
      addUtilities({
        '.scrollbar-hide': {
          '-ms-overflow-style': 'none',
          'scrollbar-width': 'none',
          '&::-webkit-scrollbar': { display: 'none' },
        },
        '.text-gradient': {
          background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
          '-webkit-background-clip': 'text',
          '-webkit-text-fill-color': 'transparent',
        },
      });
      addComponents({
        '.card': {
          backgroundColor: theme('colors.white'),
          borderRadius: theme('borderRadius.lg'),
          padding: theme('spacing.6'),
          boxShadow: theme('boxShadow.md'),
        },
      });
    }),
  ],
};
```

## Gotchas
- addUtilities classes are included in purging automatically
- Use theme() to reference design tokens rather than hard-coded values
- Official plugins: @tailwindcss/forms, @tailwindcss/typography, @tailwindcss/container-queries

## Related
- `tailwind-component-patterns.md`
- `css-custom-properties-theming.md`
