# mt-quality-evaluation-2026

**Issue:** A team picks a machine translation engine. They use BLEU score from a vendor deck. The German enterprise customer complains that the translations are "fluent but wrong." The team has no idea how to evaluate MT quality on their own content.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

BLEU is dead for LLM translation. The 2026 stack is COMET (neural reference-based) + LLM-as-judge rubric + post-edit distance as the production signal. BLEU survives only as a cheap regression test.

## Root cause

BLEU measures n-gram overlap with a reference translation. It ignores meaning, penalizes valid paraphrase, and is unreliable per sentence. For LLM-based MT (GPT-4, Claude, Gemini), fluent hallucinations are the dominant risk — BLEU can't see them.

## The 5 metrics in 2026

| Metric | What it measures | Use case | Limitations |
|---|---|---|---|
| BLEU | word n-gram overlap with reference | cheap regression test | ignores meaning, penalizes paraphrase, saturates on strong systems |
| chrF / chrF++ | character n-gram F-score | simple metric of choice, morphologically rich languages | still surface-based, no semantic understanding |
| COMET | learned quality score (source + output + reference) | ranking engines, primary automatic metric | black box, GPU helps, weaker out of news domain |
| BLEURT | learned quality score (output + reference) | alternative / complement to COMET | black-box, doesn't see source |
| COMET-Kiwi (QE) | learned quality score (source + output, no reference) | production monitoring, routing, scoring at scale | less accurate than reference-based, fooled by fluent hallucinations |

The 2026 default: COMET-22 (reference-based) for offline scoring, COMET-Kiwi (reference-free) for production, chrF as cheap cross-check, BLEU only for regression.

## The 3 human evaluation protocols

Automatic metrics approximate human judgment. The 2026 gold standard is structured human evaluation.

| Protocol | What it measures | Use case |
|---|---|---|
| Adequacy / fluency rating | annotators score 1-5 on two scales | gold standard for offline benchmark |
| MQM (Multidimensional Quality Metrics) | error typology with severity (minor/major/critical) | enterprise-scale audits |
| Ranking / direct assessment | annotators rank alternatives or slide 0-100 | best for system comparison |

For per-engine benchmarking: 50-100 segments, blind, two reviewers, simplified MQM card (accuracy/terminology/fluency × minor/major/critical). Where COMET and human disagree, investigate.

## The LLM-as-judge layer

COMET can't separate 5 quality dimensions: adequacy, fluency, idiom transfer, cultural register, domain term consistency. The 2026 stack adds an LLM-as-judge rubric.

```python
# Judge prompt template
judge_prompt = f"""
You are a professional translator evaluating translation quality.

Score the following translation on 5 dimensions, 1-5 each:
1. Adequacy: Does the translation preserve the source meaning?
2. Fluency: Is the target text natural in the target language?
3. Idiom transfer: Are idioms localized, not translated literally?
4. Cultural register: Is the formality level appropriate?
5. Domain term consistency: Are technical terms consistent with the glossary?

Source: {source}
Translation: {candidate}
Reference: {reference}

Output JSON: {{"adequacy": N, "fluency": N, "idiom": N, "register": N, "terms": N, "reasoning": "..."}}
"""
```

Calibrate the judge quarterly against native-speaker labels. Target Cohen's kappa of 0.6+ on the dimensions your product cares about.

## The 7-step bake-off

Run an MT engine bake-off on your own content.

1. **Build a test set** — 300-500 segments sampled from your real document types; hold it secret
2. **Create references** (optional) — have a professional translate or carefully post-edit
3. **Translate with every candidate engine** — same day, same glossary/settings
4. **Score automatically** — COMET as headline, chrF as cross-check
5. **Human-check the disagreements** — 50-100 segments, blind, two reviewers, simplified MQM
6. **Slice by content type and language pair** — one engine rarely wins everywhere
7. **Re-run quarterly** — engines update silently

The actionable output is a routing table (which engine for which pair × content type), not a single champion.

## The 2026 engine landscape

| Engine | Strength | Weakness |
|---|---|---|
| Gemini 2.5 Pro | WMT25 winner, 14/16 language pairs | cost |
| GPT-4.1 | close second, WMT24 strong | cost |
| Claude 3.5 Sonnet | strong on human ESA | cost |
| DeepL | European language BLEU leader (62-65) | narrower language coverage |
| TOWER-v2-70B | top COMET score (metric gaming) | loses on human evaluation |
| Fine-tuned NLLB-200 3.3B | beats LLMs on low-resource and domain-specific | needs fine-tuning |

The default for high-resource, general content: Gemini 2.5 Pro or GPT-4.1. For European: DeepL. For low-resource or domain-specific: fine-tuned NLLB.

## The 5 anti-patterns

1. **Trusting vendor BLEU scores.** Vendor benchmarks use vendor's own test data. Benchmark on yours.
2. **No slice analysis.** An engine can be best overall but worst for a specific language pair or content type. Slice the results.
3. **No human validation.** Metrics miss fluent hallucinations. Human-check 50+ segments.
4. **Single-engine dependency.** Multi-provider setup is the 2026 default (47.4% per Crowdin survey). Use different engines per language pair or content type.
5. **No quarterly re-test.** Engines update silently. The leaderboard changes.

## The WMT leaderboard

The annual Conference on Machine Translation (WMT) shared task is the de facto benchmark.

- WMT24: Claude 3.5 Sonnet won on human ESA in 9/11 pairs
- WMT25: Gemini 2.5 Pro won on human evaluation in 14/16 pairs
- TOWER-v2-70B gamed COMET (won all 11 on COMET) but lost on human evaluation
- The 2025-2026 lesson: COMET is a great regression signal, not the truth

The 2026 stack: COMET for offline scoring + LLM-as-judge rubric for dimensions + human spot-check for fluency hallucinations.

## The CALIBRATION-LOOP

Quarterly calibration of the LLM-as-judge.

1. **Sample 50 source-target pairs** per language pair from production
2. **Two native speakers** score each pair on all 5 dimensions (1-5 Likert + 1-sentence reasoning)
3. **Resolve disagreements** by discussion or 3rd annotator
4. **Run the judge prompt** against the same set, same temperature as production
5. **Compute Cohen's kappa** per dimension per pair
6. **Tune the prompt** if kappa < 0.6

A judge with kappa < 0.6 is not reliable. Tune or replace.

## The production monitoring layer

In production, score every translation in real time.

- **COMET-Kiwi** (reference-free) for every translation
- **Alert** if score drops below threshold
- **Route** to human review if score is borderline
- **Dashboard** by language pair × content type

The 2026 pattern: every translation scored, suspicious ones flagged, weekly digest of trends.

## Verification

The tell that MT quality evaluation is real:

- COMET (with reference) is the headline metric; chrF is the cross-check
- LLM-as-judge rubric on 5 dimensions is calibrated quarterly
- A bake-off on own content is run at least annually
- Multi-provider setup is the default
- Production monitoring via COMET-Kiwi catches regressions

The tell it isn't:

- BLEU is the only metric
- "The vendor's BLEU score is 65" is the answer
- No human evaluation
- Single engine for everything
- No production monitoring

## Gotchas

- **COMET is gamed.** TOWER-v2-70B won all of WMT24 on COMET but lost on human evaluation. Always pair with human spot-check.
- **COMET-Kiwi is fooled by fluent hallucinations.** Use for production monitoring, not for final quality decisions.
- **BLEU >40 on news is "strong"** but BLEU >60 may not be better than BLEU >50 for your content. The metric saturates.
- **Language pair matters.** A single engine rarely wins everywhere. Slice by pair.
- **Calibration drift.** LLMs change behavior over time. Re-calibrate quarterly.

## Related

- `i18n/translation-memory-2026.md` — TM and post-edit
- `i18n/icu-message-format.md` — message format for MT context
- `i18n/cldr-data-2026.md` — locale data backing MT
- `i18n/localization-vendor-management-2026.md` — vendor decisions

## Source URLs (verified 2026-08-10)

- https://awesomeagents.ai/leaderboards/translation-benchmarks-leaderboard/
- https://futureagi.com/blog/evaluating-llm-translation-quality-2026/
- https://www.multisensorproject.eu/machine-translation-quality-evaluation/
- https://blog.pangeanic.com/evaluating-enterprise-mt-why-bleu-is-not-enough-and-how-comet-improves-quality-assessment
- https://aclanthology.org/2023.eamt-1.6/ — BLEU Meets COMET paper
- https://www.emergentmind.com/topics/wmt25-evaluation-shared-task
- https://unbabel.com/comet/ — COMET docs
- https://www.statmt.org/wmt25/ — WMT25 shared task
