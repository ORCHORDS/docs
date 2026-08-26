# language-detection-2026

**Issue:** A team builds a multilingual chatbot. A user writes a query in Spanish; the system routes to the English NLU pipeline. The user retries in English. The team doesn't know the language until the user says so.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The 2026 production pattern is auto-detect language from text, route to the right pipeline, then confirm with the user if confidence is low. The default tools are `franc` (browser/Node), `cld3` (server, WASM), or `fasttext` (server, 300+ languages).

## Root cause

3 production tools lead the 2026 landscape.

- **franc** — most popular JS library; 400+ languages; tree-shakable
- **langdetect** — port of Google's LangDetect; 55 languages; Node.js
- **cld3** — Google's Compact Language Detector v3; 107 languages; higher accuracy; WASM

All struggle with short text (<50 chars), code snippets, and mixed-language input.

## The 5 use cases

1. **Route user input** — NLU pipeline per language
2. **Pre-classify for translation** — should we translate this content?
3. **Locale fallback** — default the Accept-Language header from text
4. **Content moderation** — language-aware safety models
5. **Analytics** — what languages are users writing in?

The 2026 default: route user input via `franc` (browser) or `cld3` (server).

## The 4 tools compared

| Tool | Lang count | Size | Speed | Accuracy | Best for |
|---|---|---|---|---|---|
| franc | 400+ | tree-shakable | <1ms | medium | browser, real-time, low resource |
| franc-min | 60 | tiny | <1ms | medium | small bundle |
| langdetect | 55 | medium | 1-5ms | medium-high | Node.js server |
| cld3 (WASM) | 107 | 5MB | 5-20ms | high | server, high accuracy |
| fasttext (lid) | 300+ | small model | 1-3ms | very high | server, comprehensive |

The 2026 default for the browser: `franc`. For server: `cld3` or `fasttext`.

## The franc pattern (browser)

```javascript
import { franc } from 'franc';

const text = "Bonjour, comment allez-vous?";
const lang = franc(text, { minLength: 10, only: ['fra', 'eng', 'deu', 'spa'] });
// lang === 'fra'

// Short text — franc returns 'und' (undetermined)
const short = "hi";
const langShort = franc(short);
// langShort === 'und' — text too short
```

`franc` requires minimum 10 characters; shorter text returns 'und'. The 2026 pattern: check length first; route to default locale if undetermined.

## The cld3 pattern (server)

```python
import cld3

# Detect single language
result = cld3.get_language("Bonjour, comment allez-vous?")
# result: LanguageResult(language='fr', probability=0.9999, is_reliable=True, proportion=1.0)

# Mixed language detection
results = cld3.get_frequent_languages("Hello world. Bonjour le monde.", num_languages=2)
# [(LanguageResult(language='en', ...), LanguageResult(language='fr', ...))]
```

`cld3` returns BCP-47 codes (en, fr, de, ja, zh, etc.). The `is_reliable` flag is the confidence signal; route only on reliable results.

## The fasttext pattern (server, 300+ languages)

```python
import fasttext

# Download lid.176.bin (126MB, 300+ languages)
model = fasttext.load_model("lid.176.bin")

result = model.predict("Bonjour, comment allez-vous?")
# (('__label__fra',), array([0.9999]))
```

fasttext is the most comprehensive (300+ languages) and fastest. The 126MB model is the trade-off.

## The 4-step pattern

1. **Detect the language** — franc, cld3, or fasttext
2. **Check confidence** — if `is_reliable` is false, fall back to default locale
3. **Route to the right pipeline** — NLU per language, MT if needed
4. **Confirm with the user if uncertain** — "Did you mean English?" with low confidence

The 4 steps cover the 2026 production pattern.

## The 5 anti-patterns

1. **Detecting on every input.** Cache per session; re-detect only on topic change.
2. **Trusting short text.** All detectors struggle with <50 chars. Use length check.
3. **Using wrong tool for context.** Browser → franc; server high accuracy → cld3; server broad → fasttext.
4. **No fallback for undetermined.** 'und' must map to a default locale (usually `en`).
5. **Assuming detection is deterministic.** The same text can return different languages on different runs; pick the top result.

## The 2026 fasttext reference numbers

fasttext's `lid.176.bin` is the 2026 standard.

- **Size:** 126MB model
- **Languages:** 176 (covers 300+ with variants)
- **Speed:** <1ms per query on CPU
- **Accuracy:** 95%+ for top-1; 99%+ for top-5
- **Output:** BCP-47-style codes (`__label__eng`, `__label__fra`, etc.)
- **License:** Apache 2.0; Facebook AI Research

The 126MB model is the trade-off; download once, cache in process.

## The 5 best practices

1. **Cache the detection per session.** Same user, same session = same language (usually).
2. **Combine with Accept-Language header.** If the user sent a header AND wrote text, both are signals.
3. **Use a confidence threshold.** Below 0.7, ask the user; above 0.9, route confidently.
4. **Detect on first message only.** Re-detect on topic change or new conversation.
5. **For mixed-language text, use cld3 with multiple-language detection.** cld3 returns per-segment probabilities.

## The 5 challenges

1. **Short text** — "hi", "ok", "?" — all return 'und'
2. **Code snippets** — `function foo() { return 42; }` — looks like English to detectors
3. **Mixed languages** — "Hello 世界" — cld3 with multi-lang detection helps
4. **Romanized text** — "konnichiwa" written in Latin script — looks like English
5. **Domain-specific jargon** — technical terms that aren't in the model's training data

The 5 challenges are why language detection should be combined with other signals (header, history, confidence).

## The 2026 production stack

A 2026 production language detection stack.

```typescript
// Web frontend: franc
import { franc } from 'franc';

function detectLanguage(text: string): string {
  if (text.length < 10) return 'und';
  const lang = franc(text, { minLength: 10, only: supportedLangs });
  if (lang === 'und') return 'und';
  return lang;
}

// Server (high accuracy): cld3 or fasttext
async function detectServer(text: string): Promise<string> {
  const result = await cld3.detect(text);
  if (result.probability < 0.7) return 'und';
  return result.language;
}
```

Browser uses franc for speed; server uses cld3 for accuracy.

## The 3 server-side alternatives

| Tool | Strength | Trade-off |
|---|---|---|
| cld3 | Google's algorithm, high accuracy | 5MB WASM, 5-20ms |
| fasttext | 300+ languages, fastest | 126MB model |
| langdetect | Node.js native, no model | lower accuracy |

The 2026 default: cld3 for accuracy, fasttext for breadth, langdetect for Node-only shops.

## The 5 GDPR / privacy considerations

Language detection is text processing; under GDPR, it may be personal data.

1. **Document the lawful basis** — usually legitimate interest for UX improvement
2. **Don't store the text** — only the detected language code
3. **Honor data subject rights** — provide the stored data, erase on request
4. **Minimize processing** — detect on first message; don't re-process
5. **Use a self-hosted model if data is sensitive** — cld3 / fasttext self-hosted, not API

For sensitive contexts, self-host the detection; don't call a cloud API.

## Verification

The tell that language detection is real:

- A library (franc, cld3, fasttext) is in the codebase
- Length check before detection; short text falls back to default
- Confidence threshold; low confidence asks the user
- Caching per session; re-detect on topic change
- Server uses cld3 or fasttext; browser uses franc

The tell it isn't:

- "We ask the user" only
- No confidence threshold
- Re-detecting on every input
- Wrong tool for context
- No fallback for 'und'

## Gotchas

- **Short text is the #1 failure mode.** Length check first.
- **Code snippets look like English.** Detect on natural language only; reject on code patterns.
- **Mixed-language text needs multi-lang detection.** cld3 with `get_frequent_languages`.
- **Romanized text is hard.** "konnichiwa" (Japanese in Latin) — detectors return English.
- **fasttext's 126MB model is the trade-off.** Download once, cache, don't ship with the app.

## Related

- `i18n/locale-negotiation.md` — locale fallback chain
- `i18n/cldr-data-2026.md` — CLDR backing data
- `i18n/icu-message-format.md` — message format
- `i18n/char-encoding-utf-8-2026.md` — text handling

## Source URLs (verified 2026-08-10)

- https://www.pkgpulse.com/guides/franc-vs-langdetect-vs-cld3-language-2026
- https://github.com/google/cld3 — cld3
- https://github.com/wooorm/franc — franc
- https://github.com/Mimino666/langdetect — langdetect
- https://fasttext.cc/docs/en/language-identification.html — fasttext language identification
- https://pypi.org/project/pycld3/ — pycld3 Python bindings
- https://docs.ropensci.org/cld3/ — R cld3 bindings
- https://github.com/jmhodges/gocld3 — Go cld3 bindings
- https://github.com/google/cld3#supported-languages — supported languages
