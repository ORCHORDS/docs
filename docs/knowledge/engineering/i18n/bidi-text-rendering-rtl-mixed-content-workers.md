# Bidirectional (BiDi) Text Handling in Cloudflare Workers and Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

User-generated content in Arabic, Hebrew, Persian, or Urdu is stored and returned from a Cloudflare Worker as plain JSON strings. The browser renders the text with a default LTR direction, causing characters to appear jumbled or punctuation to land on the wrong side. API consumers that render the text in a `<div>` without an explicit `dir` attribute produce broken layouts for RTL users. You need to detect script directionality at the edge and return `dir` metadata alongside text fields.

## Context

Unicode's Bidirectional Algorithm (UBA, UAX #9) defines how mixed-direction text is rendered, but it requires the browser to know the base direction of each paragraph. HTML provides the `dir` attribute (`ltr`, `rtl`, `auto`) and the CSS property `unicode-bidi` to control this. Server-side detection is more reliable than `dir="auto"` because the browser's heuristic can be fooled by punctuation-leading strings. RTL scripts occupy well-defined Unicode block ranges: Arabic (U+0600–U+06FF), Hebrew (U+0590–U+05FF), Persian characters overlap with Arabic, and Urdu also uses the Arabic script. Cloudflare Workers can inspect stored text in D1, detect the dominant script, and annotate API responses with `dir` metadata so any rendering client behaves correctly.

## Detecting RTL Script with Unicode Block Ranges

```typescript
// utils/bidi.ts

/**
 * RTL script Unicode ranges.
 * Each entry: [start codepoint, end codepoint]
 */
const RTL_RANGES: [number, number][] = [
  [0x0590, 0x05FF], // Hebrew
  [0x0600, 0x06FF], // Arabic (includes Farsi/Urdu)
  [0x0700, 0x074F], // Syriac
  [0x0750, 0x077F], // Arabic Supplement
  [0x0870, 0x089F], // Arabic Extended-B
  [0x08A0, 0x08FF], // Arabic Extended-A
  [0xFB1D, 0xFB4F], // Hebrew Presentation Forms
  [0xFB50, 0xFDFF], // Arabic Presentation Forms-A
  [0xFE70, 0xFEFF], // Arabic Presentation Forms-B
];

function isRtlCodepoint(cp: number): boolean {
  return RTL_RANGES.some(([start, end]) => cp >= start && cp <= end);
}

/**
 * Counts RTL and LTR alphabetic codepoints in a string.
 * Returns 'rtl' if RTL characters dominate, 'ltr' otherwise.
 */
export function detectDirection(text: string): 'ltr' | 'rtl' {
  let rtlCount = 0;
  let ltrCount = 0;

  for (const char of text) {
    const cp = char.codePointAt(0)!;
    if (isRtlCodepoint(cp)) {
      rtlCount++;
    } else if (
      (cp >= 0x0041 && cp <= 0x005A) || // A-Z
      (cp >= 0x0061 && cp <= 0x007A) || // a-z
      (cp >= 0x00C0 && cp <= 0x024F)    // Latin Extended
    ) {
      ltrCount++;
    }
  }

  return rtlCount > ltrCount ? 'rtl' : 'ltr';
}

/**
 * Annotates a plain-text string with direction metadata.
 */
export interface DirectedText {
  text: string;
  dir: 'ltr' | 'rtl';
}

export function annotateDirection(text: string): DirectedText {
  return { text, dir: detectDirection(text) };
}
```

## Injecting `dir` on API JSON Responses

```typescript
// worker.ts
import { annotateDirection } from './utils/bidi';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const id = url.searchParams.get('id');
    if (!id) return Response.json({ error: 'Missing id' }, { status: 400 });

    const row = await env.DB
      .prepare('SELECT id, title, body, dir FROM posts WHERE id = ?')
      .bind(id)
      .first<{ id: number; title: string; body: string; dir: string | null }>();

    if (!row) return Response.json({ error: 'Not found' }, { status: 404 });

    // Use stored dir if available, otherwise detect on the fly
    const titleDir = row.dir ?? annotateDirection(row.title).dir;
    const bodyDir  = row.dir ?? annotateDirection(row.body).dir;

    return Response.json({
      id: row.id,
      title: { text: row.title, dir: titleDir },
      body:  { text: row.body,  dir: bodyDir },
    });
  },
};
```

## D1 Schema with `dir` Metadata

```sql
CREATE TABLE IF NOT EXISTS posts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT    NOT NULL,
  body       TEXT    NOT NULL,
  dir        TEXT    CHECK(dir IN ('ltr','rtl')) DEFAULT 'ltr',
  locale     TEXT,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_posts_dir ON posts(dir);
```

When inserting user-generated content, detect and store `dir`:

```typescript
import { detectDirection } from './utils/bidi';

async function insertPost(env: Env, title: string, body: string, locale: string) {
  const dir = detectDirection(title + ' ' + body);
  await env.DB
    .prepare('INSERT INTO posts (title, body, dir, locale) VALUES (?, ?, ?, ?)')
    .bind(title, body, dir, locale)
    .run();
}
```

## CSS for Mixed LTR/RTL Inline Content

When rendering mixed-direction content in HTML (e.g., a Cloudflare Pages site), use `unicode-bidi: isolate` to prevent one run from bleeding into adjacent runs:

```css
/* Isolate each text span so BiDi algorithm treats them independently */
.bidi-isolate {
  unicode-bidi: isolate;
  /* Do NOT set direction here — let the dir attribute on the element control it */
}

/* Applied via JS after receiving the JSON from the Worker */
.post-title[dir="rtl"] {
  text-align: right;
  font-family: 'Noto Naskh Arabic', 'Arial', sans-serif;
}

.post-title[dir="ltr"] {
  text-align: left;
}
```

In the HTML template:

```html
<h1 class="post-title bidi-isolate"
    dir="{{ post.title.dir }}"
    lang="{{ post.locale }}">
  {{ post.title.text }}
</h1>
```

## `Intl.Segmenter` for Grapheme Boundary Detection in RTL Strings

When truncating RTL strings (e.g., for card titles), never slice by byte or code-unit — use `Intl.Segmenter` to cut on grapheme boundaries:

```typescript
export function truncateRtl(text: string, maxGraphemes: number): string {
  const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
  const segments = [...segmenter.segment(text)];
  if (segments.length <= maxGraphemes) return text;
  // For RTL, we keep the first N graphemes (visually the right side)
  return segments.slice(0, maxGraphemes).map(s => s.segment).join('') + '…'; // …
}
```

## Anti-patterns

- **Using `dir="auto"` everywhere** — browsers heuristics work 95% of the time but fail on strings that start with a number or punctuation (e.g., `"42 مرحبا"` may render LTR).
- **Storing only the text without `dir`** — forces the consumer to re-detect on every read, and detection logic may diverge across clients.
- **Slicing RTL strings with `str.slice(n)`** — code-unit slicing splits surrogate pairs and combining diacritics; always use `Intl.Segmenter`.
- **Setting `text-align: right` instead of using `dir`** — text alignment is a presentation decision; directionality is semantic and affects more than alignment (parentheses, brackets, punctuation mirroring).

## Gotchas

- Arabic diacritics (harakat, U+064B–U+0652) are in the Arabic block but are combining marks — they increase RTL count without adding visible characters; this is usually fine but be aware.
- Persian (Farsi) uses the Arabic script but its locale tag is `fa-IR` or `fa`; Hebrew is `he` or `he-IL`. The script range detection does not distinguish them, which is correct for directionality purposes.
- `Intl.Segmenter` is available in Workers runtime (V8 ≥ 10.0); verify your `wrangler.toml` compatibility date is 2022-10-31 or later.
- Mixed-script user names (e.g., `"Ahmad أحمد Smith"`) will be classified as RTL if Arabic characters outnumber Latin ones — store and display with `dir="auto"` for genuine mixed-identity cases.

## Verification

```bash
# Insert an Arabic post
curl -X POST https://my-worker.example.workers.dev/posts \
  -H 'Content-Type: application/json' \
  -d '{"title":"مرحبا بالعالم","body":"هذا نص تجريبي","locale":"ar-SA"}'

# Read it back — should include dir: "rtl"
curl 'https://my-worker.example.workers.dev/posts?id=1'
# Expected: {"title":{"text":"مرحبا بالعالم","dir":"rtl"}, ...}

# Verify D1 row
npx wrangler d1 execute MY_DB \
  --command 'SELECT id, dir, locale FROM posts ORDER BY id DESC LIMIT 1'
```

## Related

- `locale-aware-number-parsing-validation-workers.md`
- `intl-relativetimeformat-edge-localization-workers.md`
- `locale-aware-sorting-d1-sqlite-icu.md`

## Sources

- Unicode Bidirectional Algorithm (UAX #9) — https://unicode.org/reports/tr9/
- MDN unicode-bidi CSS property — https://developer.mozilla.org/en-US/docs/Web/CSS/unicode-bidi
- MDN Intl.Segmenter — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Segmenter
- Cloudflare D1 — https://developers.cloudflare.com/d1/
