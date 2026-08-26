# legal-text-translation-review-gates

**Issue:** Product UI strings tolerate imperfection; legal text does not. Terms of service, privacy notices, cookie banners, disclaimers, and compliance disclosures carry material legal consequences when mistranslated — a wrong word in a German privacy notice or a Brazilian Portuguese arbitration clause can create obligations the English original never intended, or fail to create ones the company relies on. Engineering teams routinely push legal copy through the same continuous-localization pipeline as marketing strings, which means a translated ToS update can ship to production with only machine translation and a single linguist review. The engineering problem is to design a pipeline where legal-class strings are identified, routed through additional mandatory review gates, versioned per jurisdiction, and blocked from shipping until sign-off is recorded — without slowing the rest of the localization pipeline down.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why legal text needs a different pipeline

1. **Consequence asymmetry.** A mistranslated button label annoys users for a sprint; a mistranslated liability cap or data-retention clause is a litigation risk. Industry guidance on localization compliance (SimpleLocalize, TransPerfect legal services) consistently recommends treating privacy policies, ToS, and disclaimers as the first-priority localization items, not an afterthought trailing the UI.
2. **No fuzzy-matching tolerance.** Translation memory reuse from UI strings actively hurts legal copy. A 74 percent TM match on a legal sentence can carry over obligations with subtly different scope. Legal segments should exclude UI translation memory or use a dedicated legal-only memory per jurisdiction.
3. **Jurisdiction specificity.** A ToS is not one document translated N times; it is N documents that diverge over time as local counsel amends each one (GDPR recitals for the EU, LGPD wording for Brazil, CCPA for California). The pipeline must treat locale as a fork of the source, not a mirror.
4. **Defined-term integrity.** Legal documents define terms ("The Platform", "Affiliate", "Personal Data") that must map to the exact same translated term everywhere. The pipeline needs a termbase that blocks delivery when a defined term is translated inconsistently, not merely warns.

## Gate design for the pipeline

1. **Classification gate at string extraction.** Tag every catalog entry with a content class: ui, marketing, legal, or mixed. The extraction script assigns legal to keys under legal/ namespaces (tos, privacy, disclaimers, eula). Only the legal class triggers downstream gates; this keeps UI shipping velocity intact.
2. **Three-stage review chain.** Industry best practice for legal accuracy is a multi-stage chain: translate by a legal-domain linguist, review by a second linguist for accuracy and consistency, then sign-off by in-country counsel or a sworn/certified translator where the jurisdiction requires it. Model each stage as a required workflow state in the TMS — a PR that changes a legal key without all three states closed fails CI.
3. **Counsel sign-off as a recorded artifact.** Store sign-off (reviewer identity, timestamp, source version hash) as metadata on the translation file. When a dispute arises two years later, you can prove which version of the source the reviewer actually approved, and which translated document was live on a given date.
4. **Machine-translation exclusion.** MT post-editing pipelines that are fine for support macros are not acceptable for binding clauses unless a qualified reviewer takes full responsibility for the final text. Configure the MT engine to skip legal namespaces entirely, or route MT output through the full three-stage chain rather than a lighter post-edit tier.
5. **Effective-date coupling.** Legal text changes often have contractual effective dates. The pipeline needs scheduled publication: the translated v3 privacy notice goes live only on its effective date, in every locale simultaneously, even if some locales finished review weeks earlier.

## Versioning and traceability

1. **Per-locale document versioning.** Version each locale's legal document independently (en-GB v2.3, de-DE v2.1) with a mapping table showing which source version each translation is derived from. When counsel amends the German text beyond the English source, record the divergence as a deliberate delta, not as translation drift.
2. **Immutable publication archive.** Keep every published legal document version retrievable (the ToS a user accepted in March 2025 must be reproducible during a dispute). A content-addressed store keyed by document hash is enough; do not rely on git history of the catalog repo, because the rendered document assembled from many keys is what the user saw.
3. **Acceptance binding.** If the product records ToS acceptance, bind the acceptance event to the exact document version hash per locale, not to a global version string. This is the only way to answer "which text did this user consent to".

## Verification and CI enforcement

1. **Completeness check per locale.** CI must fail when a legal document's locale file is missing keys present in the source, and — more subtly — when it contains stale keys the source no longer has, since those may render obsolete obligations.
2. **Defined-term consistency lint.** A linter cross-references the legal termbase: if "Personal Data" appears 12 times in the German file and the mandated translation is used 11 times, the build fails. This catches the single divergent term that changes legal meaning.
3. **Placeholder and reference audit.** Legal text embeds cross-references ("see Section 4.2"), dates, and named entities. A linter verifies section references resolve in the rendered target document and that interpolated values (dates, entity names, currency amounts) survive translation with correct locale formatting.
4. **Rendered-output spot check.** Because legal documents render as pages (HTML or PDF), verify layout post-assembly: German runs 30 percent longer, Hebrew needs RTL layout, CJK needs appropriate fonts. A translated clause hidden by overflow is still a compliance failure even though the catalog says "translated".
