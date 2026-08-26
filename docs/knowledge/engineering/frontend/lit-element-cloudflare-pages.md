# Lit Web Components on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
You need framework-agnostic UI components — usable inside React, SvelteKit, or plain HTML — that ship as native Custom Elements and deploy to Cloudflare Pages without a Node.js runtime.

## Context
Lit provides a thin (~6 kB) reactive layer on top of native Web Components. Because Lit components compile to standard Custom Elements, they interoperate with any host framework and are statically exportable. Cloudflare Pages serves the output as a static site with zero server costs; KV can back a config or feature-flag endpoint consumed by the components at runtime. SSR for Lit's `@lit-labs/ssr` runs on Cloudflare Workers to pre-render shadow DOM.

## Setup — Vite + Lit

```bash
npm create vite@latest my-lit-app -- --template lit-ts
cd my-lit-app
npm install lit
npm install -D wrangler @cloudflare/workers-types
```

```ts
// vite.config.ts
import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    target: 'es2022',          // Cloudflare Pages serves modern browsers
    outDir: 'dist',
    rollupOptions: {
      // expose each component as its own entry for tree-shaking consumers
      input: {
        'my-button': 'src/components/my-button.ts',
        'my-card':   'src/components/my-card.ts',
      },
      output: {
        entryFileNames: '[name].js',
        format: 'es',
      },
    },
  },
})
```

```jsonc
// wrangler.toml (Pages project — no Workers runtime needed for static deploy)
// Run: npx wrangler pages deploy dist --project-name=my-lit-app
```

## Lit Component with Reactive Properties

```ts
// src/components/my-button.ts
import { LitElement, html, css, type PropertyValues } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'

@customElement('my-button')
export class MyButton extends LitElement {
  static styles = css`
    :host {
      display: inline-block;
    }
    button {
      padding: 0.5rem 1.25rem;
      border: none;
      border-radius: 6px;
      background: var(--btn-bg, #0066cc);
      color: var(--btn-color, #fff);
      font-size: 1rem;
      cursor: pointer;
      transition: opacity 0.15s;
    }
    button:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }
    button[aria-busy='true']::after {
      content: ' …';
    }
  `

  @property({ type: String }) label = 'Submit'
  @property({ type: Boolean, reflect: true }) disabled = false
  @state() private loading = false

  protected override willUpdate(changed: PropertyValues<this>) {
    if (changed.has('disabled') && this.disabled) {
      this.loading = false
    }
  }

  async #handleClick() {
    this.loading = true
    this.dispatchEvent(new CustomEvent('action', { bubbles: true, composed: true }))
    // consumers resolve the action via the event; loading resets on re-render
    await new Promise((r) => setTimeout(r, 0))
    this.loading = false
  }

  override render() {
    return html`
      <button
        ?disabled=${this.disabled || this.loading}
        aria-busy=${this.loading ? 'true' : 'false'}
        @click=${this.#handleClick}
      >
        ${this.label}
      </button>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'my-button': MyButton
  }
}
```

## KV-backed Runtime Config Component

```ts
// src/components/my-feature-flag.ts
// Fetches feature flags from a Cloudflare Pages Function / Worker KV endpoint
import { LitElement, html } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { Task } from '@lit/task'

type Flags = Record<string, boolean>

@customElement('my-feature-flag')
export class MyFeatureFlag extends LitElement {
  @property() flag = ''

  #flagsTask = new Task(this, {
    task: async ([flag]) => {
      const res = await fetch('/api/flags')
      if (!res.ok) throw new Error(`${res.status}`)
      const flags: Flags = await res.json()
      return flags[flag] ?? false
    },
    args: () => [this.flag] as const,
  })

  override render() {
    return this.#flagsTask.render({
      pending: () => html``,
      complete: (enabled) =>
        enabled ? html`<slot></slot>` : html`<slot name="fallback"></slot>`,
      error: () => html`<slot name="fallback"></slot>`,
    })
  }
}
```

```ts
// functions/api/flags.ts  (Cloudflare Pages Function)
import type { PagesFunction } from '@cloudflare/workers-types'

interface Env {
  FLAGS: KVNamespace
}

export const onRequest: PagesFunction<Env> = async ({ env }) => {
  const raw = await env.FLAGS.get('config', { type: 'json' }) ?? {}
  return Response.json(raw, {
    headers: { 'Cache-Control': 'public, max-age=60' },
  })
}
```

## Lit SSR on Cloudflare Workers

```ts
// ssr-worker/index.ts
import { render } from '@lit-labs/ssr'
import { collectResult } from '@lit-labs/ssr/lib/render-result.js'
import { html } from 'lit'
// import side-effect: registers the element definition in the SSR VM
import '../src/components/my-button.js'

export default {
  async fetch(req: Request): Promise<Response> {
    const result = render(html`
      <my-button label="Get Started"></my-button>
    `)
    const body = await collectResult(result)
    return new Response(
      `<!doctype html><html><body>${body}
       <script type="module" ></script>
       </body></html>`,
      { headers: { 'Content-Type': 'text/html;charset=UTF-8' } }
    )
  },
}
```

## Anti-patterns
- Importing Lit inside a React bundle without lazy-loading — Custom Element definitions are global and register on import; eagerly importing every component inflates initial bundle
- Using `innerHTML` or `unsafeHTML` with unvalidated user data inside a Lit template — shadow DOM does not prevent XSS from `innerHTML`
- Relying on `document.querySelector` to reach into shadow roots from outside — shadow DOM encapsulation breaks this; use events or public properties instead
- Mutating `@state()` properties directly on the element from a parent framework without calling `setAttribute` / the property setter — bypasses Lit's reactive update cycle
- Forgetting `composed: true` on CustomEvents fired from shadow roots — without it the event does not cross shadow boundaries and React/Svelte listeners never see it

## Gotchas
- Lit decorators require `experimentalDecorators: true` in `tsconfig.json` (legacy) or TypeScript 5.0+ native decorators with `"target": "ES2022"`
- `@lit/task` requires `@lit/reactive-element` ≥ 2.0; mismatched peer deps cause double-registration errors
- Cloudflare Pages Functions run on the Workers runtime — `@lit-labs/ssr` must import the Node-compatible build (`@lit-labs/ssr/node/...`) unless you patch the import map
- `reflect: true` on `@property()` writes the value back to an HTML attribute; avoid this for complex objects or arrays
- Vite's `optimizeDeps` pre-bundles Lit; add `optimizeDeps.exclude: ['lit']` if you see duplicate registration warnings in dev mode

## Verification

```bash
# Dev
npm run dev

# Build
npm run build && ls dist/

# Deploy to Cloudflare Pages
npx wrangler pages deploy dist --project-name=my-lit-app

# Check component registration (browser console)
# customElements.get('my-button') // → MyButton class

# Test SSR worker locally
npx wrangler dev ssr-worker/index.ts --port 8788
curl http://localhost:8788/ | grep 'my-button'
```

## Related
- [web-components-custom-elements.md](web-components-custom-elements.md)
- [web-components-shadow-dom-patterns.md](web-components-shadow-dom-patterns.md)
- [feature-flags-cloudflare-workers-kv-edge-config.md](feature-flags-cloudflare-workers-kv-edge-config.md)
- [islands-architecture-cloudflare-pages-partial-hydration.md](islands-architecture-cloudflare-pages-partial-hydration.md)
- [declarative-shadow-dom-serialization-and-cloning.md](declarative-shadow-dom-serialization-and-cloning.md)

## Sources
- https://lit.dev/docs/
- https://lit.dev/docs/ssr/overview/
- https://developers.cloudflare.com/pages/functions/
- https://github.com/lit/lit/tree/main/packages/labs/task
