# i18n-glossary-management-2026

**Issue:** A team localizes to 12 languages. The brand name "FooPay" should not be translated. The team has 30 product features, each with a name. The team debates in-CMS glossaries vs TMS-managed vs per-translator. The team needs the 2026 reference for glossary management.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 glossary types

1. **Brand glossary.** Product names, trademarks. Never translate. "FooPay", "ACME", "iPhone".
2. **Product feature glossary.** Stable feature names, often kept in English. "Dashboard", "Settings", "Checkout".
3. **Industry glossary.** Domain terms with specific meaning. "PII", "GDPR", "RAG".
4. **Style glossary.** Tone, formality, voice. "Use 'you' not 'user' for direct address."
5. **Forbidden glossary.** Words to avoid. "Blacklist/whitelist", "master/slave", "guys".

## The 5-step glossary pattern

1. **Inventory existing terminology** from style guide, brand book, product docs.
2. **Categorize** into brand / product / industry / style / forbidden.
3. **Define source-language terms** with definition, do-not-translate flag, examples.
4. **Add to TMS** as glossary with per-locale approved translations.
5. **Enforce in translator UI** (TMS warns on glossary violation).

## The 5 best practices

1. **Glossary in TMS, not in translator heads.** Consistent across translators.
2. **Per-locale approved translations** for terms that need to vary.
3. **Case-sensitive matching** for brand names ("fooPay" vs "foopay").
4. **Context field** for terms with multiple meanings ("API" the noun, "API" the verb).
5. **Review quarterly** - new products, new features.

## The 5 anti-patterns

1. **No glossary** - brand name translated as "FooPago" in Spanish.
2. **Glossary in a spreadsheet** - never updated, inconsistent enforcement.
3. **Translator overrides glossary** without flag.
4. **Forbidden words not enforced** - "blacklist" still appears.
5. **Glossary not versioned** - old translations don't reflect updated terminology.

## Gotchas

- TM (Translation Memory) and glossary are different things; TMS handles both.
- Some TMS (Phrase, Lokalise) auto-suggest glossary matches; Smartling, Transifex need plugin.
- Brand legal team should approve brand glossary entries.
- Forbidden glossary is hard to enforce at scale; sample audit instead.
- Locale-specific approved translations are needed for some terms (e.g., "App Store" stays English in most languages).

## Source URLs (verified 2026-08-10)

- https://docs.lokalise.com/en/articles/1400668-glossaries
- https://support.crowdin.com/glossary/
- https://learn.microsoft.com/en-us/style-guide/brand-voice-grammar/word-choice
- https://linguahub.com/blog/translation-glossary-best-practices/
