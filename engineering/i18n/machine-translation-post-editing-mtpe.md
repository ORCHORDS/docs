# Machine Translation Post-Editing (MTPE)

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your localization process is bottlenecked: professional human translation
is accurate but expensive and slow (weeks per release), while raw machine
translation output is fast but contains errors that damage brand voice
and user trust. You need a workflow that combines the speed of machine
translation with the quality of human review, but your current process
treats every string identically — the same effort goes into translating
a button label as a legal disclaimer.

## Context

Machine Translation Post-Editing (MTPE) is a workflow where machine
translation (MT) produces the initial draft and human linguists edit the
output to reach the required quality level. In 2026, neural MT engines
(Google Translate, DeepL, Amazon Translate, Azure AI Translator) produce
output that requires minimal editing for many language pairs and content
types. The key innovation is selective human intervention — AI quality
estimation scores each segment, routing high-confidence segments to
light review and low-confidence segments to full human editing. Teams
using MTPE report 40-60% cost reduction and 2-3x faster turnaround
compared to full human translation.

## MTPE workflow

```
1. Source preparation → Clean source text (remove ambiguity, fix typos)
2. MT processing     → Run through neural MT engine
3. Quality estimation → AI scores each segment (confidence 0-100%)
4. Routing            → High confidence → light PE; Low → full PE
5. Post-editing       → Human linguists edit MT output
6. Review             → Final quality check (spot-check or full review)
7. TM update          → Feed corrections back to translation memory
```

## Post-editing levels

### Light post-editing (LEP)

Fix only errors that affect meaning or usability. Accept stylistic
differences from the MT engine. Target: comprehensible and accurate.

| Fix | Example |
|---|---|
| Mistranslation | Wrong word that changes meaning |
| Omission | Part of the source not translated |
| Addition | MT added content not in the source |
| Critical grammar | Errors that affect meaning |

### Full post-editing (FEP)

Edit to match human translation quality — correct style, terminology,
grammar, and fluency. Output should be indistinguishable from human
translation.

| Fix | All LEP fixes, plus: |
|---|---|
| Style | Match brand voice and style guide |
| Terminology | Use approved glossary terms |
| Grammar | Fix all grammatical errors |
| Fluency | Natural-sounding target language |

### When to use each

| Content type | PE level | Rationale |
|---|---|---|
| UI strings (buttons, labels) | Light | Short, context-dependent, meaning-critical |
| Knowledge base articles | Light | High volume, informational, MT handles well |
| Marketing copy | Full | Brand voice matters, persuasive tone needed |
| Legal/compliance text | Full or human-only | Precision required, liability concerns |
| User-generated content | Light or none | Volume too high for full PE, ephemeral |
| Product descriptions | Full | Revenue-impacting, brand representation |

## Quality estimation

AI quality estimation scores each translated segment, enabling selective
routing:

```
Segment: "Click Save to apply your changes"
MT output: "Cliquez sur Enregistrer pour appliquer vos modifications"
QE score: 95% → Route to light post-editing

Segment: "The liability shall not exceed the aggregate fees paid"
MT output: "La responsabilité ne doit pas dépasser les frais agrégés payés"
QE score: 62% → Route to full post-editing
```

### QE-based routing thresholds

| QE score | Action | Typical % of segments |
|---|---|---|
| 90-100% | Auto-approve (spot-check only) | 30-50% |
| 70-89% | Light post-editing | 30-40% |
| 50-69% | Full post-editing | 15-25% |
| < 50% | Human translation from scratch | 5-10% |

## Integration with TMS platforms

Major Translation Management Systems (TMS) support MTPE workflows:

| Platform | MT integration | QE support | MTPE workflow |
|---|---|---|---|
| **Phrase** | DeepL, Google, Amazon, Azure | Built-in QE scoring | Native MTPE workflow |
| **Crowdin** | 40+ MT engines | AI quality checks | MT pre-translation + editor |
| **Smartling** | Neural MT | Quality confidence scores | Hybrid workflows |
| **Lokalise** | Google, DeepL | AI review | MT + human review |

## Feedback loop

Post-editing corrections should feed back into the translation pipeline:

```
1. Linguist corrects MT segment
2. Correction stored in Translation Memory (TM)
3. Future identical/similar segments use TM match instead of MT
4. MT engine fine-tuned periodically on correction data
5. QE model updated with correction patterns
```

This creates a virtuous cycle — the more you post-edit, the better the
MT output becomes for your specific domain and terminology.

## Anti-patterns

- **Treating all content equally** — applying the same MTPE level to
  every string regardless of content type, visibility, or risk.
  Marketing headlines need full PE; internal tool tooltips need light PE
  at most.
- **No source preparation** — feeding poorly written, ambiguous source
  text into MT produces poor output that takes longer to post-edit than
  translating from scratch. Clean source text first.
- **Skipping the feedback loop** — post-editing corrections that are
  not fed back into TM and MT training mean the same errors recur in
  every release.
- **Using MTPE for all language pairs** — MT quality varies dramatically
  by language pair. EN→DE and EN→FR are high-quality; EN→JA and EN→AR
  may need more human intervention. Measure quality per pair.

## Gotchas

- **MT engine bias** — MT engines can produce biased translations
  (gendered language, cultural assumptions). Post-editors must be
  trained to catch and correct bias, not just grammatical errors.
- **Pricing models** — MT engines charge per character/word, and TMS
  platforms charge per word for MTPE workflows. Calculate total cost
  including MT + post-editing, not just MT alone.
- **Confidentiality** — sending source content to cloud MT engines may
  violate data processing agreements. Use on-premise MT or engines with
  data processing agreements for sensitive content.
- **Post-editor fatigue** — editing MT output is cognitively different
  from translating. Post-editors may unconsciously accept MT patterns
  that sound unnatural. Rotate editors and include blind quality checks.

## Verification

- Content types are classified by required PE level.
- QE scoring routes segments to appropriate PE level.
- Post-editing corrections are stored in TM.
- MT quality is measured per language pair (edit distance, TER score).
- Cost savings are tracked against full human translation baseline.
- Turnaround time meets release schedule requirements.

## Related

- `documentation/categories/i18n/icu-message-format-plurals.md`
- `documentation/categories/i18n/locale-fallback-chain.md`
- `documentation/categories/i18n/rtl-layout-support.md`

## Source URLs (verified 2026-08-16)

- Phrase MTPE best practices — https://phrase.com/blog/posts/machine-translation-post-editing/
- Crowdin MTPE guide — https://crowdin.com/blog/mt-post-editing
- Smartling MTPE — https://www.smartling.com/blog/a-hybrid-translation-approach-machine-translation-post-editing-mtpe
- Translation workflow 2026 — https://www.argotranslation.com/blog/what-a-translation-workflow-looks-like-in-2026
