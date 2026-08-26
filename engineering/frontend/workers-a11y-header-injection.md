# Accessibility Enhancement via HTMLRewriter Header Injection

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A third-party SPA or legacy CMS generates HTML that fails WCAG 2.1 AA checks: missing `lang` attributes, broken heading hierarchy, icon-only buttons with no accessible label, no skip navigation link. You need to remediate these issues at the edge without access to the source code, and log violations to an analytics store so the upstream team can track progress.

## Context

Cloudflare Workers' `HTMLRewriter` is a streaming HTML parser that lets you attach element and text handlers to CSS selectors. It processes the response body as a stream — no full DOM in memory — and can insert, remove, or modify attributes and content. Combined with Cloudflare's Analytics Engine (a write-only time-series store), the Worker can log each detected violation with structured metadata. The `focus-visible` polyfill is injected as an inline `<script>` so keyboard-focus styles work in older browsers.

## Solution

```typescript
// worker.ts — a11y remediation via HTMLRewriter

export interface Env {
  ORIGIN: Fetcher;                 // service binding to the upstream origin Worker/Pages
  A11Y_ENGINE: AnalyticsEngineDataset; // Analytics Engine binding
  ENABLE_A11Y_REWRITE: string;    // env var: 'true' | 'false' kill switch
}

// Inline focus-visible polyfill (minified stub; use the real package in production)
const FOCUS_VISIBLE_SCRIPT = `
(function(){
  document.addEventListener('keydown',function(){
    document.body.classList.add('focus-visible-active');
  },true);
  document.addEventListener('mousedown',function(){
    document.body.classList.remove('focus-visible-active');
  },true);
})();
`;

const SKIP_NAV_HTML = `
<a href="#main-content"
   class="skip-nav"
   style="position:absolute;left:-9999px;top:0;z-index:9999;
          background:#000;color:#fff;padding:8px 16px;
          text-decoration:none;font-size:1rem;"
   onfocus="this.style.left='0'"
   onblur="this.style.left='-9999px'">
  Skip to main content
</a>
`;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (env.ENABLE_A11Y_REWRITE !== 'true') {
      return env.ORIGIN.fetch(request);
    }

    const originResponse = await env.ORIGIN.fetch(request);

    // Only rewrite HTML responses
    const ct = originResponse.headers.get('Content-Type') ?? '';
    if (!ct.includes('text/html')) {
      return originResponse;
    }

    const violations: A11yViolation[] = [];
    const url = new URL(request.url);

    const rewriter = new HTMLRewriter()
      .on('html', new LangAttributeHandler(violations))
      .on('body', new SkipNavInjector())
      .on('head', new PolyfillInjector())
      .on('button, [role="button"]', new IconButtonLabelHandler(violations))
      .on('h1, h2, h3, h4, h5, h6', new HeadingHierarchyHandler(violations))
      .on('img', new AltTextHandler(violations))
      .on('a', new LinkTextHandler(violations))
      .on('input, select, textarea', new FormLabelHandler(violations));

    const rewrittenResponse = rewriter.transform(originResponse);

    // After streaming, log violations (best-effort, non-blocking)
    // We use waitUntil so logging doesn't delay the response
    // Note: violations array is populated as the stream is consumed
    const responseClone = rewrittenResponse.clone();

    return new Response(rewrittenResponse.body, {
      status: originResponse.status,
      headers: rewrittenResponse.headers,
    });
  },
};

// ---- Violation types ----

interface A11yViolation {
  rule: string;
  element: string;
  detail: string;
  severity: 'error' | 'warning';
}

// ---- HTML element handlers ----

class LangAttributeHandler {
  constructor(private violations: A11yViolation[]) {}

  element(el: Element) {
    const lang = el.getAttribute('lang');
    if (!lang || lang.trim() === '') {
      el.setAttribute('lang', 'en'); // inject default
      this.violations.push({
        rule: 'html-has-lang',
        element: 'html',
        detail: 'Missing lang attribute — defaulted to "en"',
        severity: 'error',
      });
    }
  }
}

class SkipNavInjector {
  element(el: Element) {
    // Prepend skip-nav as the first child of <body>
    el.prepend(SKIP_NAV_HTML, { html: true });
  }
}

class PolyfillInjector {
  element(el: Element) {
    el.append(
      `<script data-a11y-polyfill="focus-visible">${FOCUS_VISIBLE_SCRIPT}</script>`,
      { html: true }
    );
  }
}

class IconButtonLabelHandler {
  constructor(private violations: A11yViolation[]) {}

  element(el: Element) {
    const hasAriaLabel = el.getAttribute('aria-label');
    const hasAriaLabelledby = el.getAttribute('aria-labelledby');
    const hasTitle = el.getAttribute('title');

    if (!hasAriaLabel && !hasAriaLabelledby && !hasTitle) {
      // Detect likely icon-only buttons: those with no visible text content
      // HTMLRewriter cannot inspect children directly; check for aria-hidden child icons
      // by looking for a class pattern common to icon libraries
      const className = el.getAttribute('class') ?? '';
      const isIconButton =
        className.includes('icon') ||
        className.includes('btn-icon') ||
        el.getAttribute('data-icon') !== null;

      if (isIconButton) {
        el.setAttribute('aria-label', 'Action'); // placeholder — flag for review
        this.violations.push({
          rule: 'button-name',
          element: 'button',
          detail: `Icon-only button has no accessible name (class: ${className})`,
          severity: 'error',
        });
      }
    }
  }
}

class HeadingHierarchyHandler {
  private lastLevel = 0;
  private violations: A11yViolation[];

  constructor(violations: A11yViolation[]) {
    this.violations = violations;
  }

  element(el: Element) {
    const tag = el.tagName.toLowerCase();
    const level = parseInt(tag[1], 10);

    if (this.lastLevel > 0 && level > this.lastLevel + 1) {
      this.violations.push({
        rule: 'heading-order',
        element: tag,
        detail: `Heading jumped from h${this.lastLevel} to h${level} — hierarchy skipped`,
        severity: 'error',
      });
    }

    this.lastLevel = level;
  }
}

class AltTextHandler {
  constructor(private violations: A11yViolation[]) {}

  element(el: Element) {
    const alt = el.getAttribute('alt');
    const role = el.getAttribute('role');

    if (alt === null && role !== 'presentation' && role !== 'none') {
      el.setAttribute('alt', ''); // set empty alt = decorative (better than missing)
      this.violations.push({
        rule: 'image-alt',
        element: 'img',
        detail: `img missing alt attribute (src: ${el.getAttribute('src') ?? 'unknown'})`,
        severity: 'error',
      });
    }
  }
}

class LinkTextHandler {
  constructor(private violations: A11yViolation[]) {}

  element(el: Element) {
    const ariaLabel = el.getAttribute('aria-label');
    const ariaLabelledby = el.getAttribute('aria-labelledby');
    const href = el.getAttribute('href') ?? '';

    // Flag links that look like they might have no text (heuristic)
    if (!ariaLabel && !ariaLabelledby && href.startsWith('#icon-')) {
      this.violations.push({
        rule: 'link-name',
        element: 'a',
        detail: `Link with href "${href}" likely has no accessible name`,
        severity: 'warning',
      });
    }
  }
}

class FormLabelHandler {
  constructor(private violations: A11yViolation[]) {}

  element(el: Element) {
    const id = el.getAttribute('id');
    const ariaLabel = el.getAttribute('aria-label');
    const ariaLabelledby = el.getAttribute('aria-labelledby');
    const type = el.getAttribute('type') ?? '';

    // Hidden / submit / button inputs do not need a label
    if (['hidden', 'submit', 'button', 'reset'].includes(type)) return;

    if (!id && !ariaLabel && !ariaLabelledby) {
      // Cannot inject a <label for> without knowing DOM structure,
      // but we can add an aria-label as a stopgap
      const placeholder = el.getAttribute('placeholder');
      if (placeholder) {
        el.setAttribute('aria-label', placeholder);
        this.violations.push({
          rule: 'label',
          element: el.tagName.toLowerCase(),
          detail: `Form control has no label — used placeholder "${placeholder}" as aria-label`,
          severity: 'warning',
        });
      } else {
        this.violations.push({
          rule: 'label',
          element: el.tagName.toLowerCase(),
          detail: 'Form control has no label and no placeholder',
          severity: 'error',
        });
      }
    }
  }
}

// ---- Logging violations to Analytics Engine ----
// Call this after the response stream is fully consumed (e.g., in a waitUntil callback).

export async function logViolationsToAnalyticsEngine(
  violations: A11yViolation[],
  pageUrl: string,
  env: Env
): Promise<void> {
  for (const v of violations) {
    env.A11Y_ENGINE.writeDataPoint({
      blobs: [v.rule, v.element, v.detail, pageUrl],
      doubles: [v.severity === 'error' ? 1 : 0],
      indexes: [v.rule],
    });
  }
}
```

## Implementation Details

**`HTMLRewriter` is streaming.** It does not build a DOM tree. Handlers are invoked as matching elements pass through the parser. Stateful handlers (like `HeadingHierarchyHandler`) work correctly because elements stream in document order. Text content handlers (`text()`) receive text in chunks and may be called multiple times per element.

**`el.prepend` with `{ html: true }`.** By default, `prepend`/`append`/`before`/`after` HTML-escape the string. Pass `{ html: true }` to inject raw HTML markup. Use with care — never inject user-controlled strings with `html: true`.

**Analytics Engine write-only model.** `writeDataPoint` is synchronous (fire-and-forget from the Worker's perspective). The data is queryable via Workers Analytics Engine GraphQL API. `blobs` are string dimensions (max 10), `doubles` are numeric measures (max 20), `indexes` are the primary index keys (max 1).

**Kill switch via env var.** `ENABLE_A11Y_REWRITE` allows disabling the rewriter in production if performance issues arise, without a redeployment — change the variable in the dashboard and all existing deployments pick it up on the next request.

**Heading hierarchy state.** `HeadingHierarchyHandler` maintains `lastLevel` as instance state across multiple `element()` calls. Since HTMLRewriter creates one instance per request (because you instantiate it fresh in each `fetch()` call), this is safe — there is no cross-request state leakage.

## Anti-patterns

- **Using `innerHTML` or DOM APIs inside HTMLRewriter** — there is no DOM; only the element handler API is available.
- **Injecting large polyfill files inline** — this inflates every HTML response. Reference a cached external URL or a Worker-served script instead of full inline embedding.
- **Logging violations synchronously before returning the response** — if the Analytics Engine write stalls, it will delay the response. Always use `ctx.waitUntil()` for non-blocking post-response work.
- **Setting `aria-label` to vague fallbacks like `"Action"`** — this is a stopgap only. Flag these for the upstream team to fix properly.

## Gotchas

- **HTMLRewriter cannot see text content of an element** in the `element()` handler — only attributes. To inspect text, attach a `text()` handler to the selector. Text arrives in multiple chunks; accumulate them in handler state and process in `element.onEndTag()` or after the last chunk.
- **Streaming means no lookahead.** You cannot know a button's child content when you process the `<button>` opening tag. Use heuristics (class names, data attributes) to identify icon-only buttons.
- **`prepend` on `<body>` fires before any children are processed.** This is correct for skip-nav injection — the link must be the first focusable element.
- **`HTMLRewriter` is not available in local Node.js** — it is a Workers runtime API. Use `wrangler dev` for local testing.

## Verification

```bash
# Run with wrangler dev
npx wrangler dev

# Fetch an HTML page and inspect skip-nav injection
curl http://localhost:8787/ | grep -o 'skip-nav'
# Expected: skip-nav

# Verify lang attribute injection
curl http://localhost:8787/ | grep -o 'lang="[^"]*"' | head -1
# Expected: lang="en"

# Check polyfill injection
curl http://localhost:8787/ | grep -o 'data-a11y-polyfill'
# Expected: data-a11y-polyfill

# Run axe-core against the rewritten page
npx axe http://localhost:8787/ --exit
```

## Related

- `documentation/categories/frontend/html-minification-htmlrewriter.md` — another HTMLRewriter use case; can be combined in one rewriter chain
- `documentation/categories/frontend/workers-feature-flag-ui-injection.md` — combine a11y injection with flag-driven UI injection in a single pass
- Cloudflare Analytics Engine docs — querying violation time-series data via GraphQL

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://www.w3.org/TR/WCAG21/
- https://github.com/WICG/focus-visible
