# Locale-Aware Markdown Typography in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Blog content written in Markdown uses straight ASCII quotes (`"text"`, `'text'`) and
double hyphens (`--`), but French readers expect guillemets (`« texte »`), German readers
expect lower-opening quotes (`„text"`), and all readers deserve real em-dashes (`—`) and
ellipses (`…`).

## Context
A Cloudflare Worker processes Markdown from D1 or R2 and returns HTML. After converting
Markdown to HTML it uses HTMLRewriter to apply locale-specific typographic transforms in
a streaming pass — replacing straight quotes with the correct locale quotation marks,
double hyphens with em-dashes, and triple dots with the ellipsis character. No
client-side JavaScript is required; the transformation is purely server-side.

---

## Locale Typographic Rule Tables

```typescript
// src/lib/typography-rules.ts

export interface QuotePair {
  outerOpen: string;   // primary opening quotation mark
  outerClose: string;  // primary closing quotation mark
  innerOpen: string;   // secondary (nested) opening
  innerClose: string;  // secondary (nested) closing
  spacedGuillemets: boolean; // French/Spanish use thin space inside guillemets
}

/**
 * Locale-keyed quotation mark conventions.
 * Source: Unicode CLDR main/{locale}/delimiters.json
 */
export const QUOTE_RULES: Record<string, QuotePair> = {
  // English
  en:    { outerOpen: "“", outerClose: "”", innerOpen: "‘", innerClose: "’", spacedGuillemets: false },
  // German
  de:    { outerOpen: "„", outerClose: "“", innerOpen: "‚", innerClose: "‘", spacedGuillemets: false },
  // French — guillemets with narrow no-break space
  fr:    { outerOpen: "« ", outerClose: " »", innerOpen: "‹ ", innerClose: " ›", spacedGuillemets: true },
  // Spanish — guillemets, no space
  es:    { outerOpen: "«", outerClose: "»", innerOpen: "“", innerClose: "”", spacedGuillemets: false },
  // Polish
  pl:    { outerOpen: "„", outerClose: "”", innerOpen: "«", innerClose: "»", spacedGuillemets: false },
  // Russian
  ru:    { outerOpen: "«", outerClose: "»", innerOpen: "„", innerClose: "“", spacedGuillemets: false },
  // Japanese (corner brackets — only applied to CJK text segments)
  ja:    { outerOpen: "「", outerClose: "」", innerOpen: "『", innerClose: "』", spacedGuillemets: false },
  // Chinese (Simplified)
  "zh-Hans": { outerOpen: "“", outerClose: "”", innerOpen: "‘", innerClose: "’", spacedGuillemets: false },
  // Swedish
  sv:    { outerOpen: "”", outerClose: "”", innerOpen: "’", innerClose: "’", spacedGuillemets: false },
  // Finnish
  fi:    { outerOpen: "”", outerClose: "”", innerOpen: "’", innerClose: "’", spacedGuillemets: false },
  // Portuguese
  pt:    { outerOpen: "“", outerClose: "”", innerOpen: "‘", innerClose: "’", spacedGuillemets: false },
  // Dutch
  nl:    { outerOpen: "“", outerClose: "”", innerOpen: "‘", innerClose: "’", spacedGuillemets: false },
};

export function getQuoteRules(locale: string): QuotePair {
  const lang = locale.split("-")[0];
  return QUOTE_RULES[locale] ?? QUOTE_RULES[lang] ?? QUOTE_RULES["en"];
}
```

---

## Text-Level Typographic Transforms

```typescript
// src/lib/typograph.ts

import { getQuoteRules } from "./typography-rules";

/**
 * Apply locale-aware typographic transforms to a plain-text node value.
 * Only call on text nodes inside prose elements (p, li, blockquote, h1–h6).
 * Do NOT call on <code>, <pre>, or <script> content.
 */
export function applyTypography(text: string, locale: string): string {
  const rules = getQuoteRules(locale);

  // 1. Ellipsis: three or more dots → …
  text = text.replace(/\.{3,}/g, "…");

  // 2. Em dash: double or triple hyphen surrounded by optional spaces
  text = text.replace(/\s?---?\s?/g, "—");

  // 3. En dash: between numbers (range)
  text = text.replace(/(\d)\s?--\s?(\d)/g, `$1–$2`);

  // 4. Paired double quotes: naive but effective for most prose
  //    Regex: opening quote = preceded by whitespace/start or punctuation
  //           closing quote = followed by punctuation, whitespace, or end
  text = text.replace(/"([^"]+)"/g, `${rules.outerOpen}$1${rules.outerClose}`);

  // 5. Paired single quotes (after double-quote pass to avoid conflicts)
  text = text.replace(/'([^']+)'/g, `${rules.innerOpen}$1${rules.innerClose}`);

  // 6. Apostrophe in contractions and possessives (en, fr only — others rarely use it)
  if (locale.startsWith("en") || locale.startsWith("fr")) {
    text = text.replace(/(\w)'(\w)/g, `$1’$2`);
  }

  return text;
}
```

---

## HTMLRewriter Streaming Pass

```typescript
// src/worker.ts

import { applyTypography } from "./lib/typograph";

// Prose elements where typography transforms are safe to apply
const PROSE_TAGS = new Set(["p", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "figcaption"]);

// Elements whose text content must never be transformed
const CODE_TAGS = new Set(["code", "pre", "script", "style", "kbd", "samp", "var"]);

export default {
  async fetch(request: Request, env: any): Promise<Response> {
    const url = new URL(request.url);
    const locale = url.searchParams.get("locale") ?? "en";

    // Fetch upstream HTML (your Markdown→HTML pipeline, R2, or D1)
    const upstream = await fetch(`https://content.internal${url.pathname}`);

    if (!upstream.ok || !upstream.headers.get("Content-Type")?.includes("text/html")) {
      return upstream;
    }

    // Track whether we are inside a code/pre context
    let insideCode = 0;

    const transformed = new HTMLRewriter()
      .on("code, pre, script, style, kbd, samp, var", {
        element() { insideCode++; },
      })
      .on("code, pre, script, style, kbd, samp, var", {
        element(el) {
          // Use onEndTag via element handler to decrement
          el.onEndTag(() => { insideCode = Math.max(0, insideCode - 1); });
        },
      })
      .on(Array.from(PROSE_TAGS).join(", "), {
        text(chunk) {
          if (insideCode > 0) return; // skip code contexts
          if (!chunk.text) return;
          chunk.replace(applyTypography(chunk.text, locale), { html: false });
        },
      })
      .transform(upstream);

    return new Response(transformed.body, {
      status: upstream.status,
      headers: {
        ...Object.fromEntries(upstream.headers),
        "Content-Language": locale,
      },
    });
  },
};
```

---

## Anti-patterns

- **Running regex over the entire HTML body** — this risks corrupting attribute values,
  URLs in `href`, and code blocks; always transform at the text-node level via HTMLRewriter.
- **Applying smart-quote transforms to all text nodes without a code-context guard** —
  code samples with ASCII quotes must be preserved verbatim.
- **Using a single global quote style** — French guillemets on English text confuse readers
  and fail accessibility audits; always derive style from the content locale, not the UI locale.
- **Double-transforming** — if Markdown is pre-processed by a smartypants library and the
  Worker also applies transforms, quotes will be doubled or nested incorrectly; pick one layer.

---

## Gotchas

- HTMLRewriter may split a text node at arbitrary byte boundaries; a quote that opens in
  one chunk and closes in another will not be matched by the paired-quote regex. Process
  longer texts as complete strings by buffering `chunk.last === false` chunks, or accept
  the limitation and only transform definite patterns like `---` and `...`.
- Swedish and Finnish use closing-style quotes for both opening and closing (`"text"` →
  `"text"`); this is correct per CLDR but may look wrong to readers of other locales — add
  a comment in the rule table.
- The French narrow no-break space (`U+202F`) inside guillemets is correct but renders as
  a blank in some email clients; for email output, use a regular space instead.
- `HTMLRewriter` is a streaming transform; it does not have DOM access and cannot look
  backward in the document to determine nesting depth of quotes.

---

## Verification

```bash
# English: straight quotes become curly, double-dash becomes em-dash
echo '<p>"Hello -- world"</p>' | curl -s http://localhost:8787/?locale=en \
  -H "Content-Type: text/html" --data-binary @- | grep -o '.\{1,40\}'
# Expect: <p>“Hello—world”</p>

# French: guillemets with narrow no-break space
curl "http://localhost:8787/article/1?locale=fr" | grep -P '[«»]'

# German: lower-opening quotes
curl "http://localhost:8787/article/1?locale=de" | grep -P '[„“]'

# Code block content must be unchanged
curl "http://localhost:8787/article/with-code?locale=fr" | grep '<code>'
# Must not contain « or »
```

---

## Related

- `markdown-bidi-isolation-htmlrewriter-workers.md`
- `markdown-in-translations.md`
- `cldr-locale-quotation-marks.md`
- `unicode-normalization-nfc-nfd.md`
- `rtl-text-detection-workers-htmlrewriter.md`

---

## Sources

- <https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/>
- <https://unicode.org/cldr/charts/latest/by_type/misc.delimiters.html>
- <https://practicaltypography.com/straight-and-curly-quotes.html>
- <https://www.unicode.org/charts/PDF/U2000.pdf> (General Punctuation block)
- <https://en.wikipedia.org/wiki/Quotation_marks_in_other_languages>
