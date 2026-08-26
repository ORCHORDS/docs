# Machine Translation Quality Gates in CI with DeepL and Google Translate APIs

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your localization pipeline now generates MT output for new source strings automatically,
but you have no way to know whether the MT quality is acceptable before it ships to
production. A mistranslation in a payment flow or legal notice can cause real harm. You
need a CI gate that measures MT quality per-locale and per-domain and blocks the release
if quality drops below a configurable threshold — without requiring a human reviewer for
every string.

## Context

Machine translation quality can be measured in two complementary ways:

1. **Reference-based metrics** (BLEU, chrF, TER) — compare MT output to a human-validated
   reference translation. Require a reference corpus; great for regression testing when
   you have approved translations for a subset of strings.
2. **Reference-free metrics / Quality Estimation (QE)** — predict quality from the source
   and MT output alone, with no reference required. The state-of-the-art open-source
   model is **COMET-QE** (Unbabel). DeepL exposes a confidence score natively. Google's
   Advanced Translation API does not expose per-segment confidence, but you can post-
   process with COMETinho (lightweight COMET variant).

The pipeline described here works for both DeepL and Google Translate, uses reference-
free scoring for unseen strings, and reference-based BLEU for regression on the existing
TM corpus.

## Architecture Overview

```
Source strings (en.json)
        │
        ▼
┌───────────────────┐
│  MT Provider API  │  ← DeepL or Google Translate
│  (per locale)     │
└────────┬──────────┘
         │ MT output
         ▼
┌───────────────────┐
│  Quality Scorer   │  ← COMET-QE (reference-free)
│                   │     or sacrebleu (reference-based)
└────────┬──────────┘
         │ scores per segment
         ▼
┌───────────────────┐
│  Gate Evaluator   │  ← compare to thresholds per locale/domain
└────────┬──────────┘
         │ PASS / FAIL
         ▼
CI step exits 0 or 1
```

## DeepL API Integration

### Authentication and basic translation

```typescript
// lib/mt/deepl.ts
import DeepL from 'deepl-node';

const translator = new DeepL.Translator(process.env.DEEPL_API_KEY!);

export interface TranslationResult {
  source: string;
  target: string;
  detectedSourceLang?: string;
  billedCharacters: number;
}

export async function translateStrings(
  strings: string[],
  targetLang: DeepL.TargetLanguageCode,
  sourceLang: DeepL.SourceLanguageCode = 'en',
  glossaryId?: string,
): Promise<TranslationResult[]> {
  const results = await translator.translateText(strings, sourceLang, targetLang, {
    glossary: glossaryId,
    tagHandling: 'html',          // preserve <b>, <i>, {placeholders} inside HTML tags
    ignoreTags: ['ignore'],       // <ignore>brand names</ignore>
    formality: 'prefer_more',    // formal register (supported: de, fr, it, es, nl, pl, pt, ru)
  });

  return results.map((r, i) => ({
    source: strings[i],
    target: r.text,
    detectedSourceLang: r.detectedSourceLang ?? undefined,
    billedCharacters: r.billedCharacters,
  }));
}
```

### DeepL glossary for domain-specific terms

```typescript
export async function ensureGlossary(
  name: string,
  entries: Record<string, string>,
  targetLang: DeepL.TargetLanguageCode,
): Promise<string> {
  const existing = await translator.listGlossaries();
  const found = existing.find(g => g.name === name && g.targetLang === targetLang);
  if (found) return found.glossaryId;

  const glossary = await translator.createGlossary(name, 'en', targetLang,
    new DeepL.GlossaryEntries({ entries })
  );
  return glossary.glossaryId;
}
```

## Google Cloud Translation API Integration

```typescript
// lib/mt/google.ts
import { TranslationServiceClient } from '@google-cloud/translate';

const client = new TranslationServiceClient();
const PROJECT = process.env.GOOGLE_CLOUD_PROJECT!;
const LOCATION = 'global';
const PARENT = `projects/${PROJECT}/locations/${LOCATION}`;

export async function translateStringsGoogle(
  strings: string[],
  targetLang: string,
  sourceLang = 'en',
  glossaryId?: string,
): Promise<string[]> {
  const [response] = await client.translateText({
    parent: PARENT,
    contents: strings,
    mimeType: 'text/html',        // preserves HTML tags
    sourceLanguageCode: sourceLang,
    targetLanguageCode: targetLang,
    ...(glossaryId && {
      glossaryConfig: {
        glossary: `${PARENT}/glossaries/${glossaryId}`,
      },
    }),
  });

  return (response.translations ?? []).map(t => t.translatedText ?? '');
}
```

## Reference-Free Quality Scoring with COMET-QE

COMET-QE (`Unbabel/wmt22-cometkiwi-da`) is a reference-free quality estimation model
that returns a score in [0, 1] for each (source, MT) pair. Run it in a sidecar Python
script from your Node CI step:

```python
# scripts/score_comet_qe.py
import sys, json
from comet import download_model, load_from_checkpoint

model_path = download_model("Unbabel/wmt22-cometkiwi-da")
model = load_from_checkpoint(model_path)

data = json.load(sys.stdin)   # list of {"src": "...", "mt": "..."}
scores = model.predict(data, batch_size=8, gpus=0).scores

for i, score in enumerate(scores):
    print(json.dumps({"index": i, "score": score}))
```

Invoke from Node:

```typescript
// lib/mt/comet-qe.ts
import { spawnSync } from 'child_process';

export interface SegmentScore {
  index: number;
  score: number;
}

export function scoreCOMET(pairs: { src: string; mt: string }[]): SegmentScore[] {
  const result = spawnSync(
    'python3', ['scripts/score_comet_qe.py'],
    { input: JSON.stringify(pairs), encoding: 'utf8' }
  );
  if (result.status !== 0) throw new Error(result.stderr);

  return result.stdout.trim().split('\n').map(l => JSON.parse(l));
}
```

## Reference-Based BLEU for TM Regression

When you have human-approved reference translations stored in TM, compute BLEU to detect
regression caused by MT provider changes or glossary updates:

```typescript
// lib/mt/bleu.ts — uses sacrebleu via subprocess
import { spawnSync } from 'child_process';

export function computeBLEU(hypotheses: string[], references: string[]): number {
  const input = hypotheses.map((h, i) => `${h}\t${references[i]}`).join('\n');
  const result = spawnSync('sacrebleu', ['--input', '-', '--tok', 'intl', '-m', 'bleu'],
    { input, encoding: 'utf8' }
  );
  const match = result.stdout.match(/"score":\s*([\d.]+)/);
  return match ? parseFloat(match[1]) : 0;
}
```

Install: `pip install sacrebleu`.

## CI Gate Script

```typescript
// scripts/mt-quality-gate.ts
import { translateStrings } from '../lib/mt/deepl.js';
import { scoreCOMET } from '../lib/mt/comet-qe.js';
import { computeBLEU } from '../lib/mt/bleu.js';
import { readFileSync, existsSync } from 'fs';

interface GateConfig {
  locales: string[];
  cometQeThreshold: number;   // e.g. 0.72
  bleuThreshold?: number;     // e.g. 35 — only if reference corpus exists
  sampleSize: number;         // number of strings to sample per locale
}

const CONFIG: GateConfig = JSON.parse(readFileSync('mt-gate-config.json', 'utf8'));
const SOURCE_STRINGS: string[] = Object.values(
  JSON.parse(readFileSync('src/locales/en.json', 'utf8'))
);

// Sample deterministically by hash for reproducibility
function sample(strings: string[], n: number): string[] {
  return strings.filter((_, i) => i % Math.ceil(strings.length / n) === 0).slice(0, n);
}

let exitCode = 0;

for (const locale of CONFIG.locales) {
  const sampled = sample(SOURCE_STRINGS, CONFIG.sampleSize);

  // Translate
  const results = await translateStrings(sampled, locale as any);
  const pairs = results.map(r => ({ src: r.source, mt: r.target }));

  // COMET-QE
  const scores = scoreCOMET(pairs);
  const avgComet = scores.reduce((s, r) => s + r.score, 0) / scores.length;

  console.log(`[${locale}] COMET-QE avg: ${avgComet.toFixed(4)}`);

  if (avgComet < CONFIG.cometQeThreshold) {
    console.error(`  FAIL: ${avgComet.toFixed(4)} < threshold ${CONFIG.cometQeThreshold}`);
    exitCode = 1;
  }

  // BLEU (only if reference file exists)
  const refPath = `src/locales/reference/${locale}.json`;
  if (CONFIG.bleuThreshold && existsSync(refPath)) {
    const refs = Object.values(JSON.parse(readFileSync(refPath, 'utf8'))) as string[];
    const hyps = results.map(r => r.target);
    const bleu = computeBLEU(hyps, refs);
    console.log(`[${locale}] BLEU: ${bleu.toFixed(1)}`);
    if (bleu < CONFIG.bleuThreshold!) {
      console.error(`  FAIL BLEU: ${bleu.toFixed(1)} < threshold ${CONFIG.bleuThreshold}`);
      exitCode = 1;
    }
  }
}

process.exit(exitCode);
```

```json
// mt-gate-config.json
{
  "locales": ["de", "fr", "ja", "ar", "zh-CN"],
  "cometQeThreshold": 0.72,
  "bleuThreshold": 30,
  "sampleSize": 200
}
```

## GitHub Actions Integration

```yaml
# .github/workflows/mt-quality-gate.yml
name: MT Quality Gate

on:
  pull_request:
    paths: ['src/locales/en.json']
  push:
    branches: [main]

jobs:
  mt-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: '22' }

      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }

      - run: npm ci
      - run: pip install unbabel-comet sacrebleu deepl

      - name: Run MT quality gate
        run: npx tsx scripts/mt-quality-gate.ts
        env:
          DEEPL_API_KEY: ${{ secrets.DEEPL_API_KEY }}

      - name: Upload COMET scores as artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: mt-quality-scores-${{ github.sha }}
          path: mt-scores.json
          retention-days: 30
```

## Threshold Calibration

COMET-QE scores are not absolute quality labels — they must be calibrated against your
domain and acceptable quality bar:

| COMET-QE Score | Indicative Quality |
|---|---|
| > 0.80 | Near-human, ready for post-edit |
| 0.70–0.80 | Good, review recommended for sensitive content |
| 0.60–0.70 | Acceptable for low-stakes UI strings |
| < 0.60 | Reject — full human translation required |

Start with a conservative threshold (0.65) and tighten it over time as you build
confidence in your domain's translation patterns.

## Anti-patterns

- **Running COMET on the entire locale file every CI run** — model inference is slow; use
  sampling (200–500 strings) and cache the model weights between runs.
- **Using BLEU alone** — BLEU is a poor proxy for translation quality on short strings
  (typical UI copy); it was designed for paragraphs. Combine with COMET-QE.
- **Treating DeepL confidence as a COMET-QE equivalent** — DeepL's internal confidence
  score (available via `billedCharacters` proportion heuristic) is not publicly documented
  as a quality metric; use COMET-QE for cross-provider comparison.
- **Blocking on a single bad segment** — average scores mask outliers; log the bottom-5
  segments by score and alert on them separately rather than failing the whole locale.
- **Not splitting by domain** — marketing copy, legal text, and UI strings have very
  different acceptable quality bars. Configure per-domain thresholds.

## Gotchas

- COMET models require ~1.5 GB of disk space per model and take 30–90 seconds to load.
  Cache them in a Docker layer or GitHub Actions cache keyed by model version.
- Google Translate Advanced (v3) requires a VPC Service Controls–compatible project for
  enterprise PII compliance; the Basic (v2) API is simpler but lacks glossary support.
- DeepL glossaries are language-pair-specific; a `en→de` glossary does not apply to
  `en→de-AT` (Austrian German) — create separate glossaries per target locale.
- sacrebleu tokenization must match for comparisons to be meaningful; always use
  `--tok intl` (language-agnostic) for multilingual BLEU across locales.

## Verification

```bash
# Dry-run with a small set of known strings
echo '["Hello world","Save changes","Cancel"]' | \
  node -e "
    const { translateStrings } = require('./lib/mt/deepl.js');
    translateStrings(JSON.parse(require('fs').readFileSync('/dev/stdin','utf8')), 'de')
      .then(r => r.forEach(t => console.log(t.target)));
  "
```

## Related

- `mt-quality-evaluation-2026.md`
- `machine-translation-quality-estimation.md`
- `machine-translation-post-editing-mtpe.md`
- `continuous-localization-cicd.md`
- `i18n-glossary-management-2026.md`
- `crowdin-phrase-translation-pipeline-automation.md`

## Sources

- DeepL Node.js SDK: https://github.com/DeepLcom/deepl-node
- Google Cloud Translation v3: https://cloud.google.com/translate/docs/advanced/translating-text-v3
- Unbabel COMET: https://github.com/Unbabel/COMET
- sacrebleu: https://github.com/mjpost/sacrebleu
- WMT22 Quality Estimation Shared Task results
- Kocmi et al. (2021) "To Ship or Not to Ship: An Extensive Evaluation of Automatic Metrics for MT"
