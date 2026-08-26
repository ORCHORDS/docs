# machine-translation-post-editing

**Issue:** Integrating machine translation with human post-editing (MTPE) in the localization workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Raw MT output is not production-ready -- it requires professional post-editing to fix fluency, terminology, and tone.

## Pattern / Solution
Workflow:
1. Pre-process -- apply glossary protection and tag wrapping before MT
2. MT translate -- send XLIFF; receive draft
3. Post-edit -- Full PE (literary) or Light PE (accurate but not polished)
4. QA -- automated LQA checks, then human review
5. TM update -- approved segments feed back into translation memory

DeepL API with glossary:
```js
const translator = new deepl.Translator(process.env.DEEPL_API_KEY);
const result = await translator.translateText(
  sourceText, 'en', 'fr',
  { glossaryId: 'YOUR_GLOSSARY_ID', tagHandling: 'xml' }
);
```
Light PE estimate: ~20% of full human translation time per word.

## Gotchas
- MT quality varies by language pair; en-to-de is much better than en-to-th
- MT engines hallucinate proper nouns and technical terms; always use a termbase/glossary
- MTPE rates differ from full HT rates; track quality with MQM or BLEU scores

## Related
- `translation-quality-metrics.md`
- `translation-memory-tmx.md`
- `mt-quality-evaluation-2026.md`
