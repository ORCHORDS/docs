# Locale-Sensitive Content Diff Workers Before-After Display

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A content management system needs to show translators or editors a before/after diff of a translated string when the source text changes. The naive approach — a character-level diff — splits words at byte boundaries, producing meaningless fragments for multibyte scripts like Arabic, CJK, or Devanagari. The diff must segment text at grapheme cluster or word boundaries appropriate to the locale before computing the diff, then render the result respecting the text direction and collation of that locale.

---

## Context

Cloudflare Workers run at the edge and handle locale negotiation, but full-featured diff libraries that understand Unicode word boundaries are too large for the 1 MB script limit (compressed). The correct approach combines:

- `Intl.Segmenter` with `granularity: "word"` to tokenize both versions into locale-appropriate units
- A Myers / LCS diff algorithm over the token array (not the raw string)
- `Intl.Locale` to decide text direction for wrapping the output in a `<bdi>` span
- D1 to store the diff record alongside revision history
- KV to cache rendered diffs by a content hash key

The example project platform stores translation units in D1. A revision record holds `source_hash`, `prev_target`, and `next_target`. The Worker fetches both strings, segments them, diffs the token arrays, and returns an annotated HTML fragment that the front-end injects directly into the review UI.

---

## Segmenting Text at Locale-Appropriate Word Boundaries

Use `Intl.Segmenter` with `granularity: "word"` to break each version into tokens. Non-word segments (spaces, punctuation) must be preserved in the token list so the diff output reconstructs the full text faithfully.

```typescript
// src/lib/segment.ts

export interface Token {
  segment: string;
  isWordLike: boolean;
  index: number;
}

export function tokenize(text: string, locale: string): Token[] {
  const segmenter = new Intl.Segmenter(locale, { granularity: "word" });
  const tokens: Token[] = [];
  let index = 0;
  for (const { segment, isWordLike } of segmenter.segment(text)) {
    tokens.push({ segment, isWordLike, index });
    index += segment.length;
  }
  return tokens;
}

// Produces stable cache key for a (locale, text) pair
export function contentHash(locale: string, text: string): string {
  // Workers do not have crypto.subtle sync API for hashing short strings;
  // use a cheap djb2 variant — good enough for a KV namespace key.
  let h = 5381;
  const s = locale + "\x00" + text;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h) ^ s.charCodeAt(i);
    h >>>= 0; // keep unsigned 32-bit
  }
  return h.toString(16).padStart(8, "0");
}
```

---

## Myers LCS Diff Over Token Arrays

The standard Myers diff runs over arrays. Here it operates on the `segment` strings extracted from the token list. Only word-like tokens carry semantic weight for display purposes, but the diff must include non-word tokens to preserve spacing.

```typescript
// src/lib/diff.ts

export type ChangeKind = "equal" | "insert" | "delete";

export interface Change {
  kind: ChangeKind;
  value: string;
}

export function diffTokens(prev: string[], next: string[]): Change[] {
  // Classic LCS length table — O(n*m) but acceptable for translation units
  // which rarely exceed a few hundred tokens.
  const n = prev.length;
  const m = next.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () =>
    new Array(m + 1).fill(0)
  );

  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      if (prev[i] === next[j]) {
        dp[i][j] = 1 + dp[i + 1][j + 1];
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const changes: Change[] = [];
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && prev[i] === next[j]) {
      changes.push({ kind: "equal", value: prev[i] });
      i++;
      j++;
    } else if (j < m && (i >= n || dp[i][j + 1] >= dp[i + 1][j])) {
      changes.push({ kind: "insert", value: next[j] });
      j++;
    } else {
      changes.push({ kind: "delete", value: prev[i] });
      i++;
    }
  }
  return changes;
}
```

---

## Rendering Locale-Aware HTML Diff Fragments

The HTML renderer wraps inserted tokens in `<ins>` and deleted tokens in `<del>`, both carrying `lang` and `dir` attributes so the browser's bidi algorithm renders them correctly even when embedded inside a host document with a different direction.

```typescript
// src/lib/render.ts

import { type Change } from "./diff";

function dirForLocale(locale: string): "ltr" | "rtl" {
  const rtlScripts = new Set([
    "Arab", "Hebr", "Thaa", "Cprt", "Rohg", "Syrc", "Tfng", "Adlm",
  ]);
  try {
    // Intl.Locale exposes script via maximize()
    const maximized = new Intl.Locale(locale).maximize();
    return rtlScripts.has(maximized.script ?? "") ? "rtl" : "ltr";
  } catch {
    return "ltr";
  }
}

function escape(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function renderDiffHtml(
  changes: Change[],
  locale: string,
  granularity: "word" | "grapheme" = "word"
): string {
  const dir = dirForLocale(locale);
  const lang = locale;

  const parts: string[] = [];
  for (const { kind, value } of changes) {
    const escaped = escape(value);
    if (kind === "equal") {
      parts.push(escaped);
    } else if (kind === "insert") {
      parts.push(
        `<ins lang="${lang}" dir="${dir}" class="diff-ins">${escaped}</ins>`
      );
    } else {
      parts.push(
        `<del lang="${lang}" dir="${dir}" class="diff-del">${escaped}</del>`
      );
    }
  }

  // Wrap the whole fragment in <bdi> so it isolates bidi direction
  // regardless of the host document's direction.
  return `<bdi lang="${lang}" dir="${dir}" data-diff-locale="${lang}" data-diff-granularity="${granularity}">${parts.join("")}</bdi>`;
}
```

---

## Worker Handler with KV Caching and D1 Revision Lookup

```typescript
// src/index.ts
import { tokenize, contentHash } from "./lib/segment";
import { diffTokens } from "./lib/diff";
import { renderDiffHtml } from "./lib/render";

export interface Env {
  DB: D1Database;
  DIFF_CACHE: KVNamespace;
}

interface RevisionRow {
  revision_id: string;
  locale: string;
  prev_target: string;
  next_target: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const revisionId = url.searchParams.get("revision_id");
    const locale = url.searchParams.get("locale") ?? "en";

    if (!revisionId) {
      return new Response("revision_id required", { status: 400 });
    }

    // Build a cache key from revision + locale
    const cacheKey = `diff:${revisionId}:${locale}`;
    const cached = await env.DIFF_CACHE.get(cacheKey, "text");
    if (cached) {
      return new Response(cached, {
        headers: { "Content-Type": "text/html; charset=utf-8", "X-Cache": "HIT" },
      });
    }

    // Fetch from D1
    const row = await env.DB
      .prepare(
        "SELECT revision_id, locale, prev_target, next_target FROM translation_revisions WHERE revision_id = ? AND locale = ?"
      )
      .bind(revisionId, locale)
      .first<RevisionRow>();

    if (!row) {
      return new Response("Not found", { status: 404 });
    }

    const prevTokens = tokenize(row.prev_target, locale);
    const nextTokens = tokenize(row.next_target, locale);

    const changes = diffTokens(
      prevTokens.map((t) => t.segment),
      nextTokens.map((t) => t.segment)
    );

    const html = renderDiffHtml(changes, locale);

    // Cache for 1 hour — revisions are immutable once stored
    await env.DIFF_CACHE.put(cacheKey, html, { expirationTtl: 3600 });

    return new Response(html, {
      headers: { "Content-Type": "text/html; charset=utf-8", "X-Cache": "MISS" },
    });
  },
};
```

---

## D1 Schema for Translation Revisions

```sql
-- migrations/0001_translation_revisions.sql

CREATE TABLE IF NOT EXISTS translation_revisions (
  revision_id   TEXT    NOT NULL,
  locale        TEXT    NOT NULL,
  translation_key TEXT  NOT NULL,
  prev_target   TEXT    NOT NULL,
  next_target   TEXT    NOT NULL,
  changed_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  changed_by    TEXT,
  PRIMARY KEY (revision_id, locale)
);

CREATE INDEX IF NOT EXISTS idx_revisions_key_locale
  ON translation_revisions (translation_key, locale, changed_at DESC);
```

---

## Anti-patterns

- **Character-level diff on raw strings.** A Myers diff over individual UTF-16 code units (JavaScript's default string indexing) will split multibyte characters mid-codepoint. Always segment first.
- **Ignoring text direction in the rendered fragment.** Wrapping `<ins>`/`<del>` without `dir` attributes embeds Arabic or Hebrew tokens in an LTR context, causing bidi reordering artifacts in the browser.
- **Diffing punctuation and whitespace as semantic tokens.** Mark non-word-like segments as passthrough. Rendering `<ins> </ins>` for an inserted space produces invisible, confusing markup.
- **Skipping KV caching for immutable revisions.** Recomputing a diff on every request is wasteful; revision records never change, so a long TTL or even `expirationTtl: 86400` is safe.
- **Using `String.prototype.split(" ")` for tokenization.** Fails for Thai, Japanese, Chinese, and any script that does not use spaces as word delimiters.

---

## Gotchas

- `Intl.Segmenter` with `granularity: "word"` is available in Workers (V8 10+) but is **not** available in older Node.js versions used in local tests. Pin `"node": ">=20"` in CI.
- `Intl.Locale.maximize()` can throw if the BCP 47 tag contains a private-use subtag not recognized by the ICU data bundled in the runtime. Wrap in try/catch and default to `"ltr"`.
- The LCS diff is O(n×m). Translation units longer than ~500 words can produce noticeable latency. Add a length guard and fall back to a line-level diff above a threshold.
- HTML special characters in translation strings must be escaped before insertion into `<ins>`/`<del>`. Translation strings from untrusted contributors may contain `<`, `>`, or `&`.
- D1 stores text as UTF-8. JavaScript strings are UTF-16 internally. When indexing into `prev_target` for highlighting, recalculate byte vs. codepoint offsets if you need to highlight by position rather than segment.

---

## Verification

```typescript
// tests/diff.test.ts
import { describe, it, expect } from "vitest";
import { tokenize } from "../src/lib/segment";
import { diffTokens } from "../src/lib/diff";
import { renderDiffHtml } from "../src/lib/render";

describe("locale-sensitive diff", () => {
  it("produces word-level tokens for English", () => {
    const tokens = tokenize("hello world", "en");
    expect(tokens.map((t) => t.segment)).toEqual(["hello", " ", "world"]);
  });

  it("detects insertion at word boundary", () => {
    const prev = tokenize("bonjour monde", "fr");
    const next = tokenize("bonjour beau monde", "fr");
    const changes = diffTokens(
      prev.map((t) => t.segment),
      next.map((t) => t.segment)
    );
    const inserts = changes.filter((c) => c.kind === "insert");
    expect(inserts.map((c) => c.value)).toEqual(["beau", " "]);
  });

  it("wraps RTL output in dir=rtl bdi", () => {
    const html = renderDiffHtml(
      [{ kind: "insert", value: "مرحبا" }],
      "ar"
    );
    expect(html).toContain('dir="rtl"');
    expect(html).toContain("<bdi");
  });
});
```

Run: `npx vitest run tests/diff.test.ts`

Check the KV cache hit rate in the Workers dashboard under **Analytics → KV** for the `DIFF_CACHE` namespace.

---

## Related

- `intl-segmenter-cloudflare-workers-text-processing.md`
- `bidi-algorithm-unicode.md`
- `d1-schema-locale-preferences-content-translations-2026.md`
- `translation-kv-caching-ttl-strategy.md`
- `unicode-normalization-nfc-nfd.md`

---

## Sources

- ECMA-402 `Intl.Segmenter` spec: https://tc39.es/ecma402/#sec-intl-segmenter-objects
- Myers, E.W. (1986). "An O(ND) Difference Algorithm and Its Variations." *Algorithmica* 1(1–4):251–266.
- Unicode Standard Annex #29, Unicode Text Segmentation: https://www.unicode.org/reports/tr29/
- Cloudflare Workers `Intl` support matrix: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
- MDN `<bdi>` element: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/bdi
