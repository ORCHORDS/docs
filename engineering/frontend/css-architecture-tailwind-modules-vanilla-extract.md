# CSS Architecture — Tailwind, CSS Modules, CSS-in-JS, and vanilla-extract

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your React application uses styled-components for styling. After
migrating to React Server Components, styles break because runtime
CSS-in-JS injects `<style>` tags on the client — incompatible with
RSC's server-rendering model. Your bundle includes 85KB of the
styled-components runtime. A new developer joins and asks which
styling approach to use — the codebase has Tailwind in some files,
CSS Modules in others, and styled-components in the component
library, with no clear decision on when to use each.

## Context

The core axis in CSS architecture is compile-time vs runtime style
generation. Tailwind CSS and CSS Modules ship static stylesheets
with zero JavaScript execution needed to produce styles. Traditional
CSS-in-JS (styled-components, Emotion) parses and injects styles at
render time, adding JS parsing cost and bundle size. vanilla-extract
is authored in TypeScript but extracts to static CSS at build time
(zero runtime). The 2025-2026 trend is a strong shift away from
runtime CSS-in-JS toward zero-runtime approaches, driven by React
Server Components incompatibility and bundle size concerns. A common
pragmatic stack: Tailwind for ~90% of styling, CSS Modules or
vanilla-extract for the design system / component library layer.

## Comparison

```
Approach         Runtime cost  Type safety  RSC compatible
──────────────────────────────────────────────────────────────
Tailwind CSS     Zero          No           Yes
CSS Modules      Zero          No*          Yes
styled-components Runtime     No           No (client only)
Emotion          Runtime       No           No (client only)
vanilla-extract  Zero          Yes (TS)     Yes

* CSS Modules can get partial type safety with
  typed-css-modules or css-modules-typescript-loader
```

## Tailwind CSS v4

```css
/* v4 configuration — CSS-native, no tailwind.config.js */
@import "tailwindcss";

@theme {
  --color-brand-500: oklch(0.6 0.2 260);
  --font-display: "Inter", sans-serif;
  --breakpoint-xl: 1280px;
}
```

```
Tailwind CSS v4 (January 2025) — full Rust rewrite:

  Performance:
    → Full builds ~5x faster
    → Incremental builds >100x faster

  Configuration changes:
    → @import "tailwindcss" replaces three @tailwind directives
    → @theme blocks replace tailwind.config.js
    → Automatic content detection (no content: [] needed)
    → Dedicated packages: @tailwindcss/postcss,
      @tailwindcss/cli, @tailwindcss/vite

  CSS features:
    → Cascade layers (@layer)
    → @property for custom property types
    → color-mix() for color manipulation
    → Native CSS nesting

When to pick Tailwind:
  → Rapid product development and prototyping
  → Teams wanting shared visual vocabulary
  → Largest ecosystem and AI tooling support
  → ~90% of styling needs in most applications
```

## CSS Modules

```css
/* button.module.css */
.button {
  padding: 8px 16px;
  border-radius: 4px;
}
.button:hover {
  opacity: 0.8;
}
```

```typescript
// button.tsx
import styles from './button.module.css';

export function Button({ children }) {
  return <button className={styles.button}>{children}</button>;
}
// Renders: <button class="button_abc123">
```

```
CSS Modules:
  → Locally-scoped class names via build-tool hashing
  → Zero runtime, works with Vite, webpack, Next.js
  → composes: for sharing between modules
  → No built-in design-token system
  → Dynamic styling requires classnames/clsx composition

When to pick CSS Modules:
  → Plain CSS with scoping, minimal tooling opinion
  → Incrementally modernizing legacy apps
  → Teams comfortable with standard CSS
```

## CSS-in-JS (runtime) — declining adoption

```
styled-components / Emotion:

  Status (2025-2026):
    → Declining adoption
    → styled-components maintainers signaled reduced investment
    → React Server Components incompatible
    → Bundle size overhead (runtime parsing + injection)

  Migration drivers:
    → RSC incompatibility (no client-side <style> mutation)
    → 2-3x smaller output with zero-runtime alternatives
    → Performance cost of runtime style computation

  Still viable for:
    → Highly dynamic, prop-driven styling
    → Client-only applications not using RSC
    → Existing codebases with heavy investment
```

## vanilla-extract

```typescript
// button.css.ts — styles authored in TypeScript
import { style, createTheme, createThemeContract } from '@vanilla-extract/css';

const themeContract = createThemeContract({
  color: { primary: null, background: null },
  space: { small: null, medium: null },
});

export const lightTheme = createTheme(themeContract, {
  color: { primary: '#007bff', background: '#ffffff' },
  space: { small: '4px', medium: '8px' },
});

export const button = style({
  padding: themeContract.space.medium,
  backgroundColor: themeContract.color.primary,
  color: '#fff',
  ':hover': { opacity: 0.8 },
});
```

```
vanilla-extract:
  → "Zero-runtime Stylesheets-in-TypeScript"
  → Styles in .css.ts files → static .css at build time
  → Full TypeScript type-safety on theme tokens
  → IDE autocomplete for theme values
  → Locally-scoped classes, CSS variables, keyframes
  → Framework-agnostic (React, Vue, Svelte)
  → Build plugins: Vite, webpack, esbuild, Next.js

When to pick vanilla-extract:
  → Multi-brand/themeable design systems
  → Token type-safety and IDE autocomplete matter
  → Component library consumed by many teams
  → Zero runtime cost with TS-native ergonomics
```

## Decision framework

```
Scenario                           Recommended approach
──────────────────────────────────────────────────────────────
Rapid product development          Tailwind CSS
Design system / component library  vanilla-extract or CSS Modules
Legacy app incremental modernize   CSS Modules
Client-only dynamic styling        styled-components (existing)
                                   or Tailwind + dynamic classes
RSC / Next.js App Router           Tailwind or CSS Modules
Multi-brand theming                vanilla-extract
Polyglot team (not TS-heavy)       Tailwind or CSS Modules

Common 2025-2026 pragmatic stack:
  Tailwind for ~90% of application styling
  + vanilla-extract or CSS Modules for design system layer
```

## Anti-patterns

- **Mixing all approaches in one codebase** — having Tailwind,
  CSS Modules, AND styled-components creates confusion and
  inconsistency. Pick one primary approach with one secondary
  for the design system layer.
- **Adopting runtime CSS-in-JS with RSC** — styled-components
  and Emotion are fundamentally incompatible with React Server
  Components. Migrate to zero-runtime alternatives.
- **Overusing @apply in Tailwind** — defeats the purpose of
  utility-first CSS by recreating component classes. Extract
  React components instead of @apply blocks.
- **No design tokens in CSS Modules** — without a token system,
  CSS Modules codebases drift with hardcoded values. Use CSS
  custom properties as a token layer.

## Gotchas

- **Tailwind v3 → v4 migration** — custom plugins relying on
  the JS config API may break. Use the compatibility shim
  during migration. The `@theme` CSS syntax replaces
  `tailwind.config.js`.
- **vanilla-extract .css.ts file naming** — styles must be in
  files ending with `.css.ts` or `.css.js`. Regular `.ts` files
  cannot use `style()` — the build plugin only processes the
  special file extension.
- **CSS Modules and TypeScript** — importing `.module.css` files
  produces `any`-typed objects by default. Use `typed-css-modules`
  to generate `.d.ts` files for type-safe class name imports.
- **styled-components SSR hydration mismatches** — runtime style
  injection can cause hydration mismatches in SSR frameworks.
  This is a fundamental architectural issue, not a configuration
  problem.

## Verification

- Single primary CSS approach chosen and documented.
- Zero-runtime approach used with React Server Components.
- Design tokens defined as CSS custom properties or theme contracts.
- Tailwind v4 configuration using CSS-native @theme blocks.
- Build output verified for zero runtime CSS overhead.
- TypeScript type safety enabled for style imports.

## Related

- `documentation/categories/frontend/react-19-server-components-streaming-ssr.md`
- `documentation/categories/frontend/view-transitions-api-navigation.md`
- `documentation/categories/performance/critical-rendering-path-css-optimization.md`

## Source URLs (verified 2026-08-16)

- Tailwind CSS v4.0 Release — https://tailwindcss.com/blog
- vanilla-extract Official Site — https://vanilla-extract.style/
- CSS-in-JS vs Tailwind vs CSS Modules 2025 — https://dev.to/_d7eb1c1703182e3ce1782/css-in-js-vs-tailwind-css-vs-css-modules-which-to-choose-in-2025-cbi
- Design System Migration from styled-components — https://www.gperrucci.com/blog/react/why-migrating-design-systems-away-from-styled-components
