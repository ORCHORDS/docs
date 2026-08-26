# Email CSS Inlining Pipeline — Workers + R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your email templates are authored with `<style>` blocks or external stylesheets for maintainability, but email clients (Outlook, Gmail Web, Apple Mail) strip `<head>` styles at render time. You need a build or runtime step that inlines every CSS rule as `style=""` attributes before sending, without checking a stylesheet into every template.

## Context

Inline CSS conversion has traditionally been a build step (e.g., `juice`, `premailer`). Running it in a Cloudflare Worker at send time lets you store versioned CSS files in R2, share a stylesheet across hundreds of templates, and guarantee the inlined output is always consistent with the current stylesheet — no stale build artefacts. The Worker fetches the CSS from R2, parses the selectors against the HTML DOM, and writes `style` attributes in specificity order.

Workers run V8; they have no native DOM. Use `HTMLRewriter` (streaming, but selector-targeting only) or ship a small WASM DOM parser. For full CSS selector support, compile `css-inline` (Rust crate) to WASM and call it from the Worker.

---

## 1. Store stylesheets in R2

```typescript
// wrangler.toml
// [[r2_buckets]]
// binding = "EMAIL_ASSETS"
// bucket_name = "email-assets"

// Upload: wrangler r2 object put email-assets/styles/base.css --file ./styles/base.css
// Key convention: styles/{name}@{semver}.css  e.g. styles/base@2.1.0.css
```

Tag each object with `customMetadata: { "content-type": "text/css", "version": "2.1.0" }` so the Worker can read version without fetching content.

## 2. Fetch stylesheet from R2 with stale-while-revalidate caching

```typescript
async function fetchStylesheet(
  r2: R2Bucket,
  cache: Cache,
  key: string
): Promise<string> {
  const cacheUrl = `https://email-assets.internal/${key}`;
  const cached = await cache.match(cacheUrl);
  if (cached) return cached.text();

  const obj = await r2.get(key);
  if (!obj) throw new Error(`Stylesheet not found: ${key}`);

  const css = await obj.text();
  // Cache for 5 minutes — short enough to pick up hotfixes
  await cache.put(
    cacheUrl,
    new Response(css, {
      headers: { "Cache-Control": "max-age=300" },
    })
  );
  return css;
}
```

## 3. Inline CSS with HTMLRewriter (simple rules only)

HTMLRewriter can apply inline styles for straightforward attribute selectors and class/element rules. It streams the HTML without a full DOM — adequate for most transactional templates.

```typescript
function buildInliner(cssRules: Record<string, string>): HTMLRewriter {
  const rewriter = new HTMLRewriter();

  for (const [selector, declarations] of Object.entries(cssRules)) {
    // Only element and class selectors work in HTMLRewriter
    rewriter.on(selector, {
      element(el) {
        const existing = el.getAttribute("style") ?? "";
        const merged = mergeDeclarations(existing, declarations);
        el.setAttribute("style", merged);
      },
    });
  }
  return rewriter;
}

function mergeDeclarations(existing: string, incoming: string): string {
  // Existing inline styles win (author specificity)
  const base = new Map(
    incoming.split(";").filter(Boolean).map((d) => {
      const [prop, ...val] = d.split(":");
      return [prop.trim(), val.join(":").trim()] as [string, string];
    })
  );
  existing.split(";").filter(Boolean).forEach((d) => {
    const [prop, ...val] = d.split(":");
    base.set(prop.trim(), val.join(":").trim());
  });
  return [...base.entries()].map(([p, v]) => `${p}: ${v}`).join("; ");
}
```

## 4. Full selector support via WASM css-inline

For pseudo-classes, descendant selectors, and specificity ordering, compile the `css-inline` Rust crate and call it from the Worker:

```typescript
import init, { inline } from "./css_inline_wasm.js"; // compiled output

let wasmReady = false;

async function ensureWasm() {
  if (!wasmReady) {
    await init(); // loads the .wasm binary embedded as a data URL in the JS bundle
    wasmReady = true;
  }
}

export async function inlineEmailCSS(
  html: string,
  css: string
): Promise<string> {
  await ensureWasm();
  return inline(html, { extra_css: css, load_remote_stylesheets: false });
}
```

Bundle the `.wasm` with `wrangler build` — it counts toward the 10 MB Worker script limit.

## 5. Worker entry point

```typescript
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext) {
    const { html, stylesheetKey } = await req.json<{
      html: string;
      stylesheetKey: string; // e.g. "styles/base@2.1.0.css"
    }>();

    const cache = caches.default;
    const css = await fetchStylesheet(env.EMAIL_ASSETS, cache, stylesheetKey);
    const inlined = await inlineEmailCSS(html, css);

    return new Response(JSON.stringify({ html: inlined }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

Call this Worker from your send pipeline before handing the HTML to MailChannels or your ESP.

---

## Anti-patterns

- **Inlining at build time into static files** — the stylesheet drifts from the inlined copy; a CSS fix requires rebuilding every template variant.
- **Using HTMLRewriter for descendant or pseudo-class selectors** — it silently skips them; switch to WASM for complex selector trees.
- **Inlining `@media` queries** — media queries must stay in a `<style>` block in `<head>` (many clients do honour `<head>` media queries). Strip them from the inline pass and re-append them as a `<style>` block at the end of `<body>`.
- **Forgetting `!important` escalation** — `@media (prefers-color-scheme: dark)` overrides need `!important` in the re-appended block, not in inline styles.

## Gotchas

- The css-inline WASM binary is ~1.2 MB; keep it warm with a scheduled ping or accept ~50 ms cold-start latency on first invocation per isolate.
- R2 `get()` returns `null` for missing keys — always handle it explicitly or the Worker will throw uncaught.
- HTMLRewriter operates on byte streams; if the HTML template is large (>1 MB), use streaming response piping instead of `await response.text()`.
- `<style>` tags already in the HTML are not automatically removed by css-inline — pass `remove_style_tags: true` if you want a clean output with no `<head>` styles at all.

## Verification

1. Send the inlined HTML through [Can I Email's CSS checker](https://caniemail.com) to confirm declarations are client-safe.
2. Compare rendered output in Litmus or Email on Acid before/after inlining to catch selector mis-matches.
3. Unit test `mergeDeclarations` with conflicting declarations — existing inline style must always win.
4. Log `stylesheetKey` and content hash in your send audit trail so you can reproduce any message exactly.

## Related

- `email-template-versioning-ab-testing-r2.md`
- `email-dark-mode-support.md`
- `email-css-support-table.md`
- `email-preview-rendering-workers-r2.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://github.com/Stranger6667/css-inline
- https://caniemail.com/features/css-style-element/
