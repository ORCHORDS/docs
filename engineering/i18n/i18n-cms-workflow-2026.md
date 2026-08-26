# i18n-cms-workflow-2026

**Issue:** A team needs translators to update copy without involving engineers. The team debates headless CMS, SaaS TMS (Lokalise, Crowdin, Phrase), in-repo files with PR workflow. The team needs the 2026 reference for the translator-CMS-engineer loop.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 deployment patterns

1. **In-repo files + PR workflow.** Engineers commit translations, translators don't have write access. Slow.
2. **Headless CMS (Contentful, Sanity, Strapi).** Translators edit in CMS UI, engineers consume via API. Good for marketing copy.
3. **SaaS TMS (Lokalise, Crowdin, Phrase, Smartling, Transifex).** Purpose-built, MT integration, glossary, TM, translator marketplace.
4. **Self-hosted TMS (Weblate).** Open-source, on-prem, git-sync.

## The 5-step decision rule

1. Marketing content, non-engineers update often, no code coupling → headless CMS.
2. UI strings, MT for first pass, translator review → SaaS TMS.
3. Enterprise, on-prem required, large team → Weblate or Smartling.
4. Marketing + product strings, single source of truth → SaaS TMS for both.
5. Open-source project, community translators → Weblate (most OSS projects use it).

## The 5 anti-patterns

1. Translations in a spreadsheet emailed to engineers. No version control, no review.
2. CMS without translator access control. Translators editing live production copy.
3. TMS without MT pre-translation. Wastes translator time on high-volume content.
4. No translation memory. Same sentences translated 100x.
5. No glossary. Brand terms drift.

## Gotchas

- TMS SaaS pricing per seat/per word scales poorly for high-volume.
- Weblate git-sync is powerful but can conflict with engineer edits.
- Headless CMS content model must include locale from day 1.
- MT engines have different language strengths; pick per-locale.
- Glossary must be enforced in TMS UI; otherwise translators override.

## Source URLs (verified 2026-08-10)

- https://docs.lokalise.com/
- https://support.crowdin.com/
- https://docs.phrase.com/
- https://docs.weblate.org/
- https://www.contentful.com/
- https://www.sanity.io/
