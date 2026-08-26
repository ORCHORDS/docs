# Machine Translation Post-Editing and Quality Estimation

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The team ships MT output directly as "translations" for a new
locale. Users report awkward phrasing, incorrect gender, and
brand terms rendered in the wrong language. Alternatively,
full human translation of all UI strings costs more time and
budget than the locale rollout justifies.

## Context

Machine Translation Post-Editing (MTPE) is the workflow in
which a human editor corrects MT output rather than
translating from scratch. MTPE sits on a spectrum between
full human translation (highest quality, highest cost) and
raw MT (lowest cost, unpredictable quality). Quality
Estimation (QE) metrics help decide which segments need
light editing, which need full re-translation, and which can
ship as-is. The canonical file formats for exchanging
segments between MT engines, translation memories, and CAT
tools are XLIFF and TMX.

## 1. MTPE vs human translation economics

| Workflow         | Cost per word | Throughput      | Quality floor |
|------------------|---------------|-----------------|---------------|
| Full human (FHT) | $0.10–0.25    | 2,000 w/day     | High          |
| MTPE (light)     | $0.04–0.08    | 5,000–8,000 w/d | Medium-high   |
| MTPE (full)      | $0.06–0.12    | 3,000–5,000 w/d | High          |
| Raw MT           | ~$0.001       | Unlimited        | Low / unknown |

MTPE is cost-effective when MT cuts editing time by 30 %+
(HTER metric). Below that, editing MT is slower than
translating from scratch.

**Where MT is appropriate for product UI strings:**
- Long-tail locales with low traffic
- Marketing landing pages (review before publish)
- Help center articles (human review recommended)
- Admin panels and internal tools

**Where MT is not appropriate:**
- Legal, medical, or safety-critical text
- Brand taglines and tone-critical marketing copy
- Short, ambiguous strings (`Cancel`, `Get`) that lack
  context (MT will guess incorrectly without metadata)
- Strings containing ICU placeholders or HTML — MT engines
  routinely corrupt format markers

## 2. Quality estimation metrics

Quality estimation predicts segment quality without a
reference translation. Useful for prioritizing post-editing
effort.

**COMET** is a neural QE model that predicts a quality score
in [0, 1] from source, MT output, and an optional reference.

```bash
pip install unbabel-comet
comet-score -s sources.txt -t translations.txt \
            --model Unbabel/wmt22-comet-da
```

**BLEURT** is a BERT-based metric more robust than BLEU for
short segments.

| Metric  | Needs reference? | Short-segment accuracy | Speed   |
|---------|------------------|------------------------|---------|
| BLEU    | YES              | Low                    | Fast    |
| COMET   | Optional (QE)    | High                   | Slow    |
| BLEURT  | YES              | High                   | Medium  |
| chrF    | YES              | Medium                 | Fast    |

For UI string QE in a CI pipeline, COMET-QE (reference-free)
is the most practical: run it at PR time on changed strings
and flag segments below a threshold for human review.

## 3. XLIFF and TMX file formats

**XLIFF 2.0** is the exchange format between developers and
translation vendors (many CAT tools still support 1.2).

```xml
<!-- XLIFF 2.0 minimal example -->
<xliff version="2.0"
  xmlns="urn:oasis:names:tc:xliff:document:2.0"
  srcLang="en-US" trgLang="de-DE">
  <file id="f1">
    <unit id="save_button">
      <segment>
        <source>Save changes</source>
        <target state="translated">Änderungen speichern</target>
      </segment>
    </unit>
  </file>
</xliff>
```

**TMX (Translation Memory eXchange)** stores approved
source–target segment pairs for TM reuse.

```xml
<!-- TMX 1.4 minimal example -->
<tmx version="1.4">
  <header creationtool="our-pipeline" srclang="en-US"/>
  <body>
    <tu tuid="save_button">
      <tuv xml:lang="en-US"><seg>Save changes</seg></tuv>
      <tuv xml:lang="de-DE"><seg>Änderungen speichern</seg></tuv>
    </tu>
  </body>
</tmx>
```

## 4. Translation memory integration and glossary enforcement

A Translation Memory (TM) is a database of source–target
segment pairs. A fuzzy match above 75 % pre-fills the editor
and is counted as MTPE work. A 100 % match is reused
directly.

Glossaries (termbases) enforce brand terms and product names
regardless of MT output. Most CAT tools support TBX (TermBase
eXchange) for glossary import.

```json
// Example glossary entry (TMS-agnostic JSON)
{
  "source": "Workspace",
  "targets": {
    "de": "Arbeitsbereich",
    "fr": "Espace de travail",
    "ja": "ワークスペース"
  },
  "forbidden": {
    "de": ["Arbeitsraum", "Workspace"]
  },
  "note": "Always translate; do not use the English term."
}
```

Key rules for product UI glossaries:
- Brand names (company name, product names) — never translate
- UI primitives (`Button`, `Modal`, `Tab`) — translate with
  the approved locale-specific term
- Legal terms — translate only with legal-approved terms

## Anti-patterns

- Shipping raw MT output without any human review for
  customer-facing product strings.
- Running MT over ICU MessageFormat strings — engines will
  reorder or drop `{placeholders}` and plural branches.
- Using BLEU as the sole QE metric for short UI strings —
  BLEU is unreliable below ~50 words per segment.
- Ignoring TM leverage: segments already in the TM should
  not be re-translated — reuse them or update them.
- Storing translations without developer context notes;
  short strings like `Get` are untranslatable without
  context.

## Gotchas

- COMET requires GPU for fast inference; gate it on changed-
  files-only diffs to keep CI latency acceptable.
- XLIFF 1.2 and 2.0 are not backward compatible — confirm
  the CAT tool version before choosing a format.
- TM matches degrade as the product evolves; audit coverage
  quarterly and deprecate stale entries.

## Verification

- CI step: extract XLIFF from the i18n catalog, run COMET-QE
  on new segments, fail if any segment scores below 0.7.
- Before a locale ships: run a linguistic QA checklist
  (glossary compliance, placeholder integrity, 30 % expansion).
- Placeholder integrity: `{count}`, `{name}`, `<Link>…</Link>`
  must appear verbatim; fail the build if they are missing.

## Related

- `i18n/machine-translation-post-editing.md`
- `i18n/mt-quality-evaluation-2026.md`
- `i18n/xliff-format-handling.md`
- `i18n/translation-memory-tmx.md`
- `i18n/i18n-glossary-management-2026.md`

## Source URLs (verified 2026-08-17)

- https://docs.oasis-open.org/xliff/xliff-core/v2.0/xliff-core-v2.0.html
- https://www.gala-global.org/tmx-14b
- https://github.com/Unbabel/COMET
- https://github.com/google-research/bleurt
- https://www.taus.net/resources/reports/mtpe-rates-and-productivity
