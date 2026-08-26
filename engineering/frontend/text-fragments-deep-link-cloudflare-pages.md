# Text Fragment URLs — Precise Deep Linking on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Documentation, blog posts, or knowledge-base pages hosted on Cloudflare Pages need
shareable links that scroll to and highlight a specific sentence — not just a named
anchor. Adding `id` attributes to every linkable paragraph requires authors to
instrument every piece of content in advance. Users sharing a quoted passage expect
the recipient's browser to land at exactly the right text, the way Google Search
result snippets do when users click "More results from this page."

## Context

Text Fragment URLs append `#:~:text=` to any URL. The browser locates the matching
text range in the DOM, scrolls it into view, and applies a UA highlight (yellow in
Chrome, blue in Safari). No JavaScript is required to consume them and no changes
are needed to the page's HTML. The page is served from Cloudflare Pages unchanged;
the entire mechanism is parsed and acted on by the browser before any script runs.

JavaScript can read the active fragment via `location.hash`, style the highlight
with `::target-text`, and generate fragment URLs from text selections. Workers are
useful only for server-side analytics when users land on fragment URLs.

Browser support: Chrome 80+, Edge 80+, Safari 16.1+. Firefox does not implement
text fragments as of 2025. Feature-detect with `'fragmentDirective' in document`.

---

## 1. Fragment Syntax Reference

```typescript
// Exact match — simplest form
const exact = '#:~:text=Hello%20World';

// Context pair — prevents matching the wrong occurrence
// Structure: [prefix-,]textStart[,textEnd][,-suffix]
const withContext = '#:~:text=the%20quick-,brown%20fox,-jumps%20over';

// Range match — highlights from textStart to textEnd (inclusive)
const range = '#:~:text=In%20the%20beginning,the%20end.';

// Multiple highlights separated by & between text= directives
const multi = '#:~:text=first%20phrase&text=second%20phrase';

function buildTextFragment(options: {
  textStart: string;
  textEnd?: string;
  prefix?: string;
  suffix?: string;
}): string {
  const { textStart, textEnd, prefix, suffix } = options;
  const parts: string[] = [];

  if (prefix) parts.push(`${encodeURIComponent(prefix)}-,`);
  parts.push(encodeURIComponent(textStart));
  if (textEnd)  parts.push(`,${encodeURIComponent(textEnd)}`);
  if (suffix)   parts.push(`,-${encodeURIComponent(suffix)}`);

  return `#:~:text=${parts.join('')}`;
}
```

The `:~:` separator is never percent-encoded — only the text values inside are. The
browser strips the directive from the URL sent to the server; the fragment never
reaches Cloudflare.

---

## 2. Generating Share Links from Text Selections

```typescript
function getSelectionFragment(): string | null {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) return null;

  const text = selection.toString().trim();
  if (text.length < 3) return null;

  // Short selections: exact match
  if (text.length <= 100) {
    return buildTextFragment({ textStart: text });
  }

  // Long selections: anchor on first 40 and last 40 chars (range form)
  return buildTextFragment({
    textStart: text.slice(0, 40).trim(),
    textEnd:   text.slice(-40).trim(),
  });
}

async function copyShareLink(): Promise<void> {
  const fragment = getSelectionFragment();
  if (!fragment) {
    // Surface a UI message instead of a silent no-op
    throw new Error('Select some text first');
  }

  const url = `${location.origin}${location.pathname}${fragment}`;
  await navigator.clipboard.writeText(url);
}
```

---

## 3. Styling the Highlight

```css
/* Override UA default highlight with brand colors */
::target-text {
  background-color: hsl(var(--accent-h) var(--accent-s) 88%);
  color: hsl(var(--text-h) var(--text-s) 10%);
  border-radius: 2px;
  padding-inline: 0.15em;
}

/* Dark theme variant via token swap */
:root[data-theme="dark"] {
  --accent-highlight-bg: hsl(var(--accent-h) var(--accent-s) 20%);
  --accent-highlight-fg: hsl(var(--text-h) var(--text-s) 90%);
}
```

```typescript
// Gate the CSS feature in JS if needed
const supportsTargetTextSelector: boolean =
  typeof CSS !== 'undefined' && CSS.supports('selector(::target-text)');
```

`::target-text` is supported in Chrome 89+, Edge 89+, and Safari 16.1+. The UA
renders a default highlight even without the override; your CSS is progressive
enhancement only.

---

## 4. Reading Active Fragments in JavaScript

```typescript
function getActiveTextFragments(): string[] {
  // The spec defines document.fragmentDirective but items() is not yet widely stable.
  // Parse the hash directly instead.
  const hash = location.hash;
  const directiveIdx = hash.indexOf(':~:');
  if (directiveIdx === -1) return [];

  return hash
    .slice(directiveIdx + 3)   // skip ":~:"
    .split('&')
    .filter(p => p.startsWith('text='))
    .map(p => decodeURIComponent(p.slice(5)));
}

// Example: annotate the page with a "You were sent here" banner
function showFragmentBanner(): void {
  const fragments = getActiveTextFragments();
  if (fragments.length === 0) return;

  const quote = fragments[0].split(',')[0]; // textStart portion
  const banner = document.createElement('div');
  banner.setAttribute('role', 'status');
  banner.textContent = `Shared snippet: "${quote}"`;
  document.body.prepend(banner);
}
```

---

## 5. Workers: Fragment Landing Analytics

The server never sees `#:~:text=` — Cloudflare Workers receive only the path and
query string. Capture fragment data client-side and forward to a Worker.

```typescript
// Client-side: fire-and-forget beacon
function reportFragmentLanding(): void {
  const fragments = getActiveTextFragments();
  if (fragments.length === 0) return;

  navigator.sendBeacon(
    '/api/analytics/fragment-landing',
    JSON.stringify({
      path:      location.pathname,
      fragments: fragments.slice(0, 5),   // cap payload
      referrer:  document.referrer || null,
    })
  );
}

// workers/fragment-analytics.ts
interface FragmentLanding {
  path: string;
  fragments: string[];
  referrer: string | null;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response(null, { status: 405 });

    const event = await request.json<FragmentLanding>();
    const batch = event.fragments.slice(0, 5).map(f =>
      env.DB.prepare(
        'INSERT INTO fragment_landings (path, fragment, referrer, country, ts) VALUES (?,?,?,?,?)'
      ).bind(
        event.path.slice(0, 500),
        f.slice(0, 200),
        event.referrer?.slice(0, 300) ?? null,
        (request.cf as Record<string, string>)?.country ?? 'XX',
        Date.now()
      )
    );
    await env.DB.batch(batch);

    return new Response(null, { status: 204 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- Including `:~:text=` in server-side routing or redirect rules. The browser strips
  the directive before sending the HTTP request; the server never receives it.
- URL-encoding the `:~:` separator. Only the text values inside `text=` should be
  percent-encoded; encoding the structural punctuation breaks the spec parser.
- Using text fragments as a substitute for `id` anchors in navigable headings. Text
  fragments are for quoting and sharing; heading IDs are for persistent navigation.
  Both serve different audiences and should coexist.
- Relying on `hashchange` to detect fragment activation. Some browsers fire it, some
  do not; it is not a reliable activation signal.

## Gotchas

- The browser will not match text inside `<script>`, `<style>`, `display:none`
  elements, `<details>` (when closed), or content with `visibility:hidden`.
- Cloudflare's HTML minifier (Transform Rules → Minify) can collapse whitespace in
  text nodes, breaking fragments that rely on the original spacing.
- Long fragments may fail to match if the text spans across block boundaries in an
  unexpected way. The spec requires the matched range to be within a single
  "block-level element" in some browser implementations.
- Text fragments can expose to `document.referrer` which snippet was shared when
  navigating away, revealing user intent to the destination page.
- Safari's implementation does not yet support the context form `prefix-,text,-suffix`
  in all 16.x versions; test precision matching on that platform.

## Verification

```
# Paste in address bar on a page with the word "Introduction":
https://your-pages-site.pages.dev/docs/guide#:~:text=Introduction
# Expected: browser scrolls to "Introduction", applies highlight
```

```typescript
// Confirm parsing:
location.hash = '#:~:text=Hello%20World';
console.log(getActiveTextFragments()); // ["Hello World"]
```

Test Cloudflare Pages headers do not strip the `#` fragment — they never should,
since fragments are client-side only and are not transmitted in HTTP requests.

## Related

- `navigation-api-interception-focus-and-scroll-contract.md`
- `url-search-params-state-management.md`
- `html-performance-resource-hints.md`
- `html-search-landmark-semantics.md`

## Sources

- WICG Scroll to Text Fragment — https://wicg.github.io/scroll-to-text-fragment/
- MDN Text fragments — https://developer.mozilla.org/en-US/docs/Web/URI/Fragment/Text_fragments
- CSS ::target-text — https://developer.mozilla.org/en-US/docs/Web/CSS/::target-text
- Chrome explainer — https://github.com/WICG/scroll-to-text-fragment/blob/main/EXPLAINER.md
