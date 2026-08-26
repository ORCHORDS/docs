# AI Translation Pipelines for i18n (2026)

## Symptom

Your translation workflow is: developer adds a key -> emails a vendor ->
waits 5 days -> pays $0.15/word -> integrates XLIFF -> ships. Releases lag
behind code, minor string tweaks never get translated, and the TMS bill
grows faster than the user base.

In 2026 the alternative is an **AI translation pipeline**: LLM/MT handles
the bulk, a human reviews the high-stakes strings, and CI runs quality
checks. Done right this cuts cost 80-95% and ships translations in minutes.

## Pipeline architecture

```
source strings (en)
   |
   v
[extract] -- i18next-parser / formatjs extract / gettext
   |
   v
[pre-translate] -- DeepL API / GPT / Claude / Gemini
   |                (with glossary + context notes + TM lookup)
   v
[quality gate] -- BLEU/comet vs TM, length check, ICU validity, banned-term scan
   |
   v
[human review] -- only strings flagged low-confidence or in "marketing" namespace
   |
   v
[commit] -- PR back to repo, CI runs on merge
```

## Gotchas

- **Raw LLM translation drops ICU markup.** Prompting GPT to translate
  `"You have {count, plural, one{# message} other{# messages}}"` frequently
  mangles the `{count, plural, ...}` skeleton. Post-validate every string
  parses through `@formatjs/icu-messageformat-parser` before merge.
- **LLMs hallucinate brand names and proper nouns.** Always feed a
  glossary (canonical term -> approved translation -> do-not-translate list)
  into the prompt. Without it, "Acme" may become "Akme" or get translated
  to a local word.
- **Context is everything.** Translating `"Save"` in isolation gives the
  verb in some languages and the noun in others. Include the surrounding
  string, the component path, and a screenshot URL. Tolgee and General
  Translation do this natively; roll-your-own must pass it in the prompt.
- **Plural forms differ wildly.** Arabic has 6 plural categories (zero,
  one, two, few, many, other); English has 2. Do not let the LLM invent
  plural forms -- feed CLDR cardinal rules and validate output against
  `@formatjs/intl-pluralrules`.
- **Gendered languages (Hebrew, Arabic, French, Russian) need persona.**
  "Welcome back" may need masculine/feminine variants. Decide upfront:
  default to gender-neutral or prompt the model for both forms.
- **Machine translation drifts between runs.** The same source string may
  translate differently next sprint, causing churn. Pin model versions
  (e.g. `deepl-v2`, `gpt-4o-2024-08`) and store the model in commit metadata.
- **Quality metrics lie on short strings.** BLEU is meaningless on 2-word
  UI labels. Use COMET or chrF for evaluation, and always gate on length
  ratio (target/source between 0.5 and 3.0) -- a sudden 10x blowup means
  the model output garbage.
- **PII leakage risk.** Never send user-generated content through a public
  LLM API. Use Azure OpenAI / AWS Bedrock / GCP Vertex with data-processing
  agreements, or self-host.
- **Review queue ordering matters.** Sort by (visibility x traffic x MT
  confidence). A homepage headline with low-confidence MT beats a buried
  settings label with high-confidence MT every time.
- **Detected language != requested locale.** If a user's browser says
  `pt-PT` but you only ship `pt-BR`, route through the pipeline to generate
  the variant on demand or fall back cleanly. Don't silently serve Spanish.

## Recommended 2026 stack

- **MT engine**: DeepL Pro (best for European languages), GPT-4o-class LLM
  (best for context + non-European), Google/Azure as fallback.
- **TMS with AI built in**: Tolgee, General Translation, Locize, better-i18n.
- **Quality**: COMET (unbabel-comet), sacrebleu for legacy BLEU.
- **Glossary**: store as JSON in repo, feed to every MT call.
