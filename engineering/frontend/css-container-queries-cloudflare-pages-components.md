# CSS Container Queries for Responsive Components on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a card or panel component that must adapt its layout based on how much space its *container* gives it—not the viewport width. Viewport-based media queries break when the same component appears in a narrow sidebar and a full-width grid. CSS Container Queries solve this. On Cloudflare Pages the CSS is processed by Lightning CSS (or PostCSS) for browser compatibility before being pushed to the CDN.

## Context

Container Queries (`@container`) let a child element inspect the dimensions of a named ancestor. The ancestor must declare `container-type: inline-size` (or `size`). A common mistake is applying `container-type` to the element whose children you want to query—the queried element must be the *parent*, not the element itself. Lightning CSS transpiles `@container` for older browsers and is available as a Vite plugin or PostCSS plugin.

## Container Query Implementation

```css
/* src/styles/card.css */

/* 1. The wrapper declares itself as a container */
.card-wrapper {
  container-type: inline-size;
  container-name: card;        /* optional — use for nested containers */
}

/* 2. Default (small) layout — single column */
.card {
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: auto 1fr auto;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
}

.card__image {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-radius: 0.25rem;
}

.card__body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.card__actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

/* 3. Medium container (>= 360px) — image left, content right */
@container card (min-width: 360px) {
  .card {
    grid-template-columns: 120px 1fr;
    grid-template-rows: 1fr auto;
  }

  .card__image {
    grid-row: 1 / 3;
    aspect-ratio: 1;
  }

  .card__body {
    grid-column: 2;
    grid-row: 1;
  }

  .card__actions {
    grid-column: 2;
    grid-row: 2;
    justify-content: flex-start;
  }
}

/* 4. Large container (>= 560px) — hero layout */
@container card (min-width: 560px) {
  .card {
    grid-template-columns: 200px 1fr;
    padding: 1.5rem;
  }

  .card__image {
    aspect-ratio: 4 / 3;
  }

  .card__body h2 {
    font-size: 1.25rem;
  }
}
```

```html
<!-- Usage: wrapper provides the container context, card queries it -->

<!-- Narrow sidebar: card renders in single-column layout -->
<aside style="width: 240px;">
  <div class="card-wrapper">
    <article class="card">
      <img class="card__image"  alt="" />
      <div class="card__body">
        <h2>Article title</h2>
        <p>Short description text.</p>
      </div>
      <div class="card__actions">
        <button>Read more</button>
      </div>
    </article>
  </div>
</aside>

<!-- Full-width grid: same card renders in hero layout -->
<main>
  <div class="grid" style="grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));">
    <div class="card-wrapper">
      <article class="card"><!-- same markup --></article>
    </div>
  </div>
</main>
```

```typescript
// vite.config.ts — Lightning CSS via the official Vite plugin
import { defineConfig } from 'vite';
import lightningcss from 'vite-plugin-lightningcss';

export default defineConfig({
  plugins: [
    lightningcss({
      browserslist: '>= 0.5%, last 2 versions, not dead',
    }),
  ],
  css: {
    transformer: 'lightningcss',
    lightningcss: {
      // Transpile @container for browsers that don't support it natively
      targets: {
        chrome: 105,   // first full support — no transform needed for modern target
        safari: 16,
        firefox: 110,
      },
    },
  },
});
```

```yaml
# .github/workflows/deploy.yml — Cloudflare Pages deployment
name: Deploy to Cloudflare Pages

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build
        env:
          NODE_ENV: production

      - name: Deploy to Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: pages deploy dist --project-name=my-design-system
```

## Design System Integration

When you ship a component library to Cloudflare Pages, each component owns its container declaration:

```css
/* tokens.css — shared design tokens */
:root {
  --card-gap: 0.75rem;
  --card-padding: 1rem;
  --card-radius: 0.5rem;
}

/* Each component file sets its own container */
.stat-widget-wrapper   { container-type: inline-size; container-name: stat-widget; }
.data-table-wrapper    { container-type: inline-size; container-name: data-table; }
.nav-panel-wrapper     { container-type: inline-size; container-name: nav-panel; }
```

Naming containers avoids ambiguity when containers are nested—a `@container card` rule only responds to the nearest ancestor named `card`, not any inline-size container.

## PostCSS Alternative

If you prefer PostCSS over Lightning CSS:

```bash
npm install -D postcss-container-query-polyfill
```

```javascript
// postcss.config.js
module.exports = {
  plugins: [
    require('postcss-container-query-polyfill'),
  ],
};
```

Note that the PostCSS polyfill uses a ResizeObserver-based JavaScript shim at runtime, adding ~6 kB. Lightning CSS emits native CSS with prefixes where needed—no runtime JS.

## Anti-patterns

- Applying `container-type` to `.card` itself and then writing `@container (min-width: 360px)` rules that target `.card`—a container cannot query itself. The container must be the *parent*.
- Using `container-type: size` when you only need inline (width) queries—`size` also tracks block size and creates a new block-formatting context that can break percentage heights.
- Writing `@container (min-width: 360px)` without `container-name` when multiple containers are nested—the query matches the nearest ancestor container, which may not be the one you intend.
- Mixing viewport `@media` and `@container` queries on the same property without a clear specificity strategy—they do not interact but can conflict when the cascade order is unclear.

## Gotchas

- Container Queries are supported in all modern browsers since late 2023 (Chrome 106, Firefox 110, Safari 16). You only need Lightning CSS or PostCSS for users on older versions.
- A `container-type` element establishes a new stacking context and a new block-formatting context—this can affect `overflow: visible` children and `z-index` stacking.
- In CSS Modules or Tailwind-v4 CSS-first configs, class names are scoped; the `@container card` name is global, so keep container names unique across the design system.
- Cloudflare Pages serves static assets (CSS, JS) from the CDN with long `Cache-Control` headers by default; after a deploy, hashed file names ensure visitors get fresh assets.

## Verification

```bash
# Build and inspect output CSS for @container rules
npm run build && grep -n '@container' dist/assets/*.css

# Serve locally and resize the sidebar:
npm run preview

# In Chrome DevTools: open the "Elements" panel,
# select .card-wrapper, and drag its width in the box model
# — the card should reflow at 360 px and 560 px.

# Check Pages deployment
npx wrangler pages deploy dist --project-name=my-design-system
curl -I https://my-design-system.pages.dev | grep cache-control
```

## Related

- `qwik-cloudflare-pages-resumability.md`
- `nextjs-app-router-cloudflare-pages-adapter.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries
- https://developers.cloudflare.com/pages/
- https://lightningcss.dev/transpilation.html
- https://caniuse.com/css-container-queries
