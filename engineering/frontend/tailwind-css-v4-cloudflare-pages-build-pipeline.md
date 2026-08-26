# Tailwind CSS v4 with Cloudflare Pages Build Pipeline

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You migrate a project from Tailwind CSS v3 to v4 and deploy on Cloudflare Pages. The local
development build works perfectly, but the Pages build fails with `Cannot find module
'@tailwindcss/vite'`, produces an empty CSS output, or applies none of the utility classes in
production. Alternatively, you start a fresh project and want a reliable pipeline from day one.

## Context

Tailwind CSS v4 (stable since early 2025) is a ground-up rewrite. It drops the JavaScript
configuration file in favour of a CSS-first approach: the entire theme is expressed inside your
stylesheet with `@theme`, `@variant`, and `@import "tailwindcss"` directives. The PostCSS plugin is
replaced by a native Vite plugin (`@tailwindcss/vite`) for Vite-based projects and an independent
CLI (`@tailwindcss/cli`) for frameworks without Vite integration.

Cloudflare Pages builds run in an isolated Node.js environment managed by Cloudflare. The build
container supports Node 18/20, npm/yarn/pnpm, and Vite out of the box. Key differences from a
local machine:

- The build runs from `package.json` scripts; it has no filesystem write access outside the
  project root.
- Environment variables available during the Pages build come from the Pages project settings, not
  `.env` files.
- The Pages CDN cannot post-process CSS; final CSS must be fully resolved at build time.

## Installing Tailwind CSS v4

```bash
npm install tailwindcss@^4 @tailwindcss/vite@^4
```

For projects using the CLI instead of Vite:

```bash
npm install tailwindcss@^4 @tailwindcss/cli@^4
```

There is **no** `tailwind.config.js` or `tailwind.config.ts` in v4. Delete it. The old `content`
array for purging is replaced by automatic detection via the Lightning CSS content scanner.

## Vite Configuration

In `vite.config.ts` (Next.js with the Vite adapter, Remix, Astro, or plain Vite):

```typescript
import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [
    tailwindcss(),
    // … other plugins
  ],
});
```

The plugin registers two internal transforms: one for the `@import "tailwindcss"` directive and
one for the Lightning CSS post-processing pass. No PostCSS config is needed.

## CSS Entry Point

Replace the v3 directives with a single import:

```css
/* src/styles/global.css */
@import "tailwindcss";

/* Theme customisation lives here in v4 */
@theme {
  --color-brand: oklch(55% 0.22 250);
  --font-sans: "Inter Variable", ui-sans-serif, system-ui;
  --radius-card: 0.75rem;
}

/* Variants */
@variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));
```

Custom utilities and component classes use standard CSS with the `@utility` layer:

```css
@utility btn {
  display: inline-flex;
  align-items: center;
  padding-inline: var(--spacing-4);
  padding-block: var(--spacing-2);
  border-radius: var(--radius-card);
  font-weight: 600;
}
```

## Cloudflare Pages Build Settings

In the Pages dashboard (or `wrangler.toml` for v3 Pages):

| Setting | Value |
|---|---|
| Build command | `npm run build` |
| Build output directory | `dist` (Vite) or `.next` (Next.js) |
| Node.js version | `20` (set via `NODE_VERSION=20` env var) |

Because v4 uses Lightning CSS internally — which requires a compiled Rust binary — ensure Node 20
is selected. The binary ships in the npm package as a platform-specific optional dependency.
Cloudflare's build container resolves these automatically for `linux-x64`.

If you use `npm ci` (recommended in CI for reproducible installs), all optional dependencies are
installed by default.

## Next.js with @next/turbopack

When using Next.js 15+ with Turbopack (`next dev --turbopack`), Tailwind v4 integrates through its
PostCSS adapter *only if you are not using the Vite adapter*. For Next.js specifically:

```bash
npm install @tailwindcss/postcss@^4
```

```javascript
// postcss.config.mjs
export default {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};
```

Turbopack reads `postcss.config.mjs` natively. The Pages build uses `next build`, which also reads
this config, so the pipeline is consistent between local and CI.

## Content Detection and Purging

v4 automatically scans all files in the project that are not in `node_modules` or hidden
directories. There is no `content` array. The scanner looks for Tailwind class names in:

- `.js`, `.jsx`, `.ts`, `.tsx`, `.html`, `.vue`, `.svelte` files
- Template literal strings
- Class attribute values in JSX

If you generate class names dynamically (e.g., `text-${color}-500`), those strings will not be
detected. Use safelist via `@source`:

```css
@source "../node_modules/@company/ui/dist";  /* external component lib */
```

Or use the `safelist` option in `tailwind.config.ts` — wait, there is no config file in v4. Use
`@source` with a glob in the CSS file instead.

## Upgrading from v3

The official codemods handle most migrations:

```bash
npx @tailwindcss/upgrade@next
```

This rewrites:
- `tailwind.config.js` theme into `@theme {}` blocks in CSS
- `@tailwind base/components/utilities` directives to `@import "tailwindcss"`
- Renamed utilities (`shadow-sm` → `shadow-xs`, `ring-0` → `ring-0` stays, `blur-sm` → `blur-xs`)

After running codemod, audit these common v3→v4 breaks:

| v3 | v4 |
|---|---|
| `ring` (3px blue ring) | `ring-3` (ring is now width-0 by default) |
| `shadow` (default shadow) | `shadow-sm` (sizes shifted down) |
| `text-opacity-*` | `text-black/50` (opacity modifier) |
| `bg-opacity-*` | `bg-black/50` |
| `divide-*` colour utilities | Use `[&>*+*]:border-t` |

## Anti-patterns

**Keeping `tailwind.config.js`**: v4 ignores this file silently. Customisations inside it are
swallowed without error. Move everything to `@theme {}` in CSS.

**Using PostCSS `autoprefixer` alongside v4**: v4's Lightning CSS pass already adds vendor
prefixes. Running `autoprefixer` after it duplicates prefixes and can break some properties. Remove
`autoprefixer` from `postcss.config.*`.

**Setting `NODE_VERSION=18` on Cloudflare Pages**: The Lightning CSS native binary for Node 18
needs `node-gyp` which is unavailable in the Pages build container. Use Node 20+.

**Dynamic class construction without safelist**: `className={`bg-${brand}-600`}` produces classes
the scanner cannot see. Either switch to full class names or add `@source` for the pattern.

**Mixing `@tailwindcss/vite` with a manual PostCSS config**: Having both causes double processing.
Use one integration path: Vite plugin *or* PostCSS plugin, never both.

## Gotchas

- v4 emits CSS using `@layer` but the output uses native CSS cascade layers, not the Tailwind-
  specific layer handling of v3. Some CDN or framework layer-stripping middleware can break this.
- The `dark:` variant is **not** defined by default when `@variant dark` is omitted. If dark mode
  stops working after upgrade, add the `@variant dark` line shown in the CSS entry point above.
- Cloudflare Pages caches the `node_modules` directory between builds. If you switch from v3 to v4
  mid-project, clear the build cache in the Pages dashboard to avoid stale PostCSS plugin versions
  being loaded.
- `@apply` still works in v4 but is discouraged. It cannot apply utilities defined with `@utility`
  in the same file without a specific ordering guarantee.
- Source maps for the final CSS are generated but may reference internal Lightning CSS virtual
  paths. Browser devtools show the correct source line for your utility classes in most cases.

## Verification

1. Run `npm run build` locally and inspect `dist/assets/*.css`. It should contain your custom
   `@theme` variables as `--color-brand: oklch(…)` at `:root` and utility classes for every class
   found in the scanned files.
2. Deploy to a Cloudflare Pages preview URL and open DevTools → Network → filter by `css`. Verify
   the stylesheet is non-empty and Brotli-compressed.
3. Check that dark mode variants render correctly by toggling `data-theme="dark"` in the HTML
   element via DevTools console.
4. Run `npx tailwindcss --input src/styles/global.css --output /tmp/check.css` to get a
   standalone audit of what classes would be emitted.

## Related

- `css-architecture-tailwind-modules-vanilla-extract.md`
- `tailwind-component-patterns.md`
- `tailwind-dark-mode.md`
- `build-time-env-baking-chunk-hash.md`
- `vite-config-patterns.md`

## Sources

- Tailwind CSS v4 official docs: https://tailwindcss.com/docs/v4-beta (now stable docs)
- `@tailwindcss/upgrade` migration guide
- Cloudflare Pages build environment docs: https://developers.cloudflare.com/pages/configuration/build-configuration/
- Lightning CSS: https://lightningcss.dev/
