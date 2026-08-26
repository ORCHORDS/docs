# Locale-Aware Word Count and Billing — Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You bill translation or AI-generation jobs by "word count" and Japanese, Chinese, or Thai
customers dispute their invoices: your counter treats every CJK character as zero words
(split on whitespace), while Unicode-aware segmentation counts thousands of words correctly.
Conversely, agglutinative languages like Finnish or Turkish produce inflated word counts when
billed per word because a single compound word carries the meaning of a multi-word English
phrase.

## Context

Word count is not a universal concept:
- **Whitespace-delimited** (Latin, Cyrillic, Arabic, Greek): words are whitespace-separated tokens.
- **No-space scripts** (CJK): words are identified by dictionary-based segmentation; character
  count is the practical billing unit.
- **Mixed** (Japanese): kanji/kana runs need character counting; embedded Latin segments need
  word counting.
- **Agglutinative** (Finnish, Turkish, Hungarian): word count underestimates linguistic content;
  morpheme count or character count is fairer.

`Intl.Segmenter` with `granularity: 'word'` handles the whitespace-delimited case correctly
across scripts. For CJK, character count is the industry standard. Workers run the logic at
the edge, store per-job results in D1, and apply locale-specific billing coefficients from KV.

---

## 1 — Detect script family from locale

```typescript
// src/script-family.ts

type ScriptFamily = 'whitespace' | 'cjk' | 'thai' | 'agglutinative';

const CJK_LOCALES   = new Set(['zh', 'ja', 'yue']);
const THAI_LOCALES  = new Set(['th', 'lo', 'km', 'my']);
const AGGLU_LOCALES = new Set(['fi', 'et', 'hu', 'tr', 'az', 'kk', 'uz', 'ky', 'tk']);

export function scriptFamily(locale: string): ScriptFamily {
  const lang = locale.split('-')[0].toLowerCase();
  if (CJK_LOCALES.has(lang))   return 'cjk';
  if (THAI_LOCALES.has(lang))  return 'thai';
  if (AGGLU_LOCALES.has(lang)) return 'agglutinative';
  return 'whitespace';
}
```

---

## 2 — Per-family word count functions

```typescript
// src/word-count.ts
import { scriptFamily } from './script-family';

/** Count Unicode grapheme clusters (CJK / Thai billing unit). */
function graphemeCount(text: string, locale: string): number {
  const seg = new Intl.Segmenter(locale, { granularity: 'grapheme' });
  let n = 0;
  for (const _ of seg.segment(text)) n++;
  return n;
}

/** Count word segments excluding pure whitespace/punctuation tokens. */
function wordSegmentCount(text: string, locale: string): number {
  const seg = new Intl.Segmenter(locale, { granularity: 'word' });
  let n = 0;
  for (const { isWordLike } of seg.segment(text)) {
    if (isWordLike) n++;
  }
  return n;
}

export interface WordCountResult {
  rawCount: number;   // script-appropriate raw unit
  billableUnits: number;
  method: 'word' | 'grapheme';
  family: ReturnType<typeof scriptFamily>;
}

/**
 * Return billable units for `text` in `locale`.
 * CJK/Thai: graphemes ÷ 5 (industry convention: 5 chars ≈ 1 "word").
 * Agglutinative: words × 0.7 (deflation coefficient — words are longer).
 * Whitespace: straight word count.
 */
export function countBillableUnits(text: string, locale: string): WordCountResult {
  const family = scriptFamily(locale);

  if (family === 'cjk' || family === 'thai') {
    const raw = graphemeCount(text, locale);
    return { rawCount: raw, billableUnits: Math.ceil(raw / 5), method: 'grapheme', family };
  }

  const raw = wordSegmentCount(text, locale);

  if (family === 'agglutinative') {
    return { rawCount: raw, billableUnits: Math.ceil(raw * 0.7), method: 'word', family };
  }

  return { rawCount: raw, billableUnits: raw, method: 'word', family };
}
```

---

## 3 — Load billing rates from Workers KV

```typescript
// src/billing-rates.ts

interface BillingRate {
  pricePerUnit: number;  // USD
  currency: string;
  rateLabel: string;     // shown on invoice: "per word", "per 5 characters", etc.
}

const DEFAULTS: BillingRate = { pricePerUnit: 0.12, currency: 'USD', rateLabel: 'per word' };

export async function getBillingRate(kv: KVNamespace, locale: string): Promise<BillingRate> {
  const lang = locale.split('-')[0];
  const raw  = await kv.get(`billing:rate:${lang}`) ?? await kv.get('billing:rate:default');
  return raw ? (JSON.parse(raw) as BillingRate) : DEFAULTS;
}
```

KV entries (set via wrangler or API):
```bash
wrangler kv key put --binding BILLING_RATES "billing:rate:ja" \
  '{"pricePerUnit":0.025,"currency":"USD","rateLabel":"per 5 characters"}'
wrangler kv key put --binding BILLING_RATES "billing:rate:fi" \
  '{"pricePerUnit":0.09,"currency":"USD","rateLabel":"per word (0.7 coefficient)"}'
```

---

## 4 — Worker handler: count, price, and record

```typescript
// src/index.ts
import { countBillableUnits } from './word-count';
import { getBillingRate }     from './billing-rates';

interface Env {
  DB:            D1Database;
  BILLING_RATES: KVNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const { jobId, locale, text } = await req.json<{
      jobId: string; locale: string; text: string;
    }>();

    const count = countBillableUnits(text, locale);
    const rate  = await getBillingRate(env.BILLING_RATES, locale);
    const total = count.billableUnits * rate.pricePerUnit;

    // Persist for invoicing
    await env.DB.prepare(`
      INSERT INTO job_billing (job_id, locale, raw_count, billable_units, method, price_usd, ts)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).bind(jobId, locale, count.rawCount, count.billableUnits, count.method,
             total, Date.now()).run();

    return Response.json({
      jobId, locale,
      rawCount:      count.rawCount,
      billableUnits: count.billableUnits,
      method:        count.method,
      rateLabel:     rate.rateLabel,
      priceUsd:      total,
    });
  },
};
```

---

## 5 — D1 schema

```sql
CREATE TABLE job_billing (
  job_id         TEXT    PRIMARY KEY,
  locale         TEXT    NOT NULL,
  raw_count      INTEGER NOT NULL,
  billable_units INTEGER NOT NULL,
  method         TEXT    NOT NULL CHECK (method IN ('word','grapheme')),
  price_usd      REAL    NOT NULL,
  ts             INTEGER NOT NULL
);
CREATE INDEX idx_billing_locale ON job_billing (locale, ts);
```

---

## Anti-patterns

- **`text.split(' ').length`** — collapses to near-zero for CJK, Thai, and Burmese; always use
  `Intl.Segmenter`.
- **`text.length` (code unit count) for billing** — a CJK character is 1 code unit but semantically
  1 word-equivalent; emoji and supplementary characters are 2 code units but 1 grapheme.
- **Applying the same price-per-word across all locales** — Japanese novels average 2–3 syllables
  per character; billing the same as English words is commercially unsustainable.
- **Counting spaces as billable units** — `isWordLike` on `Intl.Segmenter` word segments already
  filters punctuation and whitespace.

## Gotchas

- Japanese text often interleaves CJK and Latin (e.g. product names in Roman letters). The
  `Intl.Segmenter` word granularity handles mixed scripts but you should validate with real
  product-domain text.
- The CJK "÷5" convention is not universal — translation agencies differ (÷4, ÷6). Store the
  denominator in KV so it can be adjusted per customer contract without code changes.
- `Intl.Segmenter` is available in V8 115+ (Workers compatibility date ≥ 2023-09-04). Lock
  your `compatibility_date` and test it explicitly.

## Verification

```typescript
import { countBillableUnits } from './word-count';

const en = countBillableUnits('Hello beautiful world', 'en');
console.assert(en.billableUnits === 3,  'English word count');

const ja = countBillableUnits('日本語のテスト文字', 'ja');
console.assert(ja.method === 'grapheme', 'Japanese uses grapheme billing');
console.assert(ja.billableUnits === Math.ceil(ja.rawCount / 5), 'Japanese ÷5');

const fi = countBillableUnits('Kansainvälistyminen on monimutkainen prosessi', 'fi');
console.assert(fi.billableUnits < fi.rawCount, 'Finnish deflation applied');
```

## Related

- `intl-segmenter-cloudflare-workers-text-processing.md`
- `grapheme-cluster-iteration.md`
- `locale-aware-csv-export-workers-d1.md`
- `locale-aware-invoice-receipt-generation-d1-workers.md`
- `translation-quality-metrics.md`

## Sources

- MDN `Intl.Segmenter` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Segmenter
- Unicode Text Segmentation (UAX #29) — https://unicode.org/reports/tr29/
- Translation industry word-count conventions — https://www.atanet.org/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
