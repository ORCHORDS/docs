# next-js-font-optimization

**Issue:** Self-hosted or third-party fonts cause layout shift and render blocking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Google Fonts loaded via <link> block rendering and cause CLS from font swap.

## Pattern / Solution
```ts
// app/layout.tsx
import { Inter, Roboto_Mono } from 'next/font/google';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
});

const mono = Roboto_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-mono',
});

export default function RootLayout({ children }) {
  return (
    <html className={`${inter.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```

```css
body { font-family: var(--font-inter), sans-serif; }
```

## Gotchas
- next/font self-hosts fonts at build time; no runtime network requests
- variable mode lets you use CSS custom properties for flexibility
- Local fonts: use next/font/local with src array for multiple weights

## Related
- `font-loading-optimization.md`
- `html-web-vitals-cls.md`
