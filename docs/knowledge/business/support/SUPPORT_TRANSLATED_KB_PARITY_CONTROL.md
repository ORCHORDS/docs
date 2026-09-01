# Support Translated Knowledge Base Parity

A translated knowledge base makes a promise: what the customer reads in their language is what the source article says. Break that promise and the failure modes are serious: a German article instructs a step the product no longer supports, a Japanese article omits a safety caveat the English original carries, or a Spanish article promises a refund window the current policy withdrew. Parity control is the discipline that keeps translated articles aligned with their source in content, freshness, and availability, and honest about what to do when they are not.

## Scope

This article covers parity control between source-language knowledge-base articles and their translations: which articles must be translated, how freshness and drift are measured, how source changes propagate, and how fallback behaves when a translation lags. It applies to help-center articles, macro translations, and portal task instructions.

It does not cover translation quality review for style, localization of product interfaces, machine-translation model selection, or legal review of jurisdiction-specific terms. It assumes a defined source language and a managed set of target languages with named owners.

## Workflow or implementation guidance

Parity runs on four mechanisms:

1. Article inventory with parity class. Every source article carries a parity class: full parity (must exist, be current, and be complete in all supported languages), partial parity (specific languages by market need), or source-only (published with a declared reason, such as jurisdiction-limited content). The inventory is generated from the content system, not maintained by hand, and the class decision is reviewed when an article's traffic or topic risk changes. Safety, billing, account-security, and accessibility-critical articles are full parity by default.
2. Version binding. A translation is bound to a specific source version, not to "the article" in the abstract. The binding record holds source version identifier, translation version, translation date, and translator or pipeline (human, machine, machine-plus-review). Freshness is the gap between the current source version's publication time and the bound translation's version date; drift is any semantic difference between the bound source version and the current source version.
3. Change propagation. When a source article changes, the content system creates translation work items per target language, triaged by change severity: substantive (steps, limits, caveats, screenshots showing different UI), moderate (clarifications, added sections), and cosmetic (typography, links). Substantive changes put affected translations into a flagged state immediately; the flag is customer-visible (see fallback) and clears only when the translation republishes against the new source version. Cosmetic changes batch on a normal cycle.
4. Fallback and disclosure. When a translation is stale beyond its severity-based threshold or flagged by a substantive source change, the customer-facing behavior is defined rather than improvised: the article either displays the stale content with a dated notice that a newer source version exists and links to it, or, for safety and security content, is replaced by the source version with a translation notice. Silent staleness, where the customer believes they are reading current guidance, is the prohibited state. Untranslated articles in a partial-parity or source-only class display in the source language by design with a clear notice, never a machine guess presented as published content.

Measurement is continuous: per language, the count and share of articles within freshness threshold, the age of the oldest substantive-stale article, the backlog of open translation work items by severity, and the drift findings from sampling (below). The parity report ranks languages by exposure: how many high-traffic, high-risk articles are stale, not how many articles in total, because one stale billing article outweighs forty stale FAQ lines.

## Controls

- Version binding enforcement: a translation cannot publish without a source version reference; edits to translations that diverge from their bound source require a divergence record with a reason (for example, a jurisdictional term difference), which is re-reviewed at every source change.
- Severity-triage rule: substantive source changes flag all bound translations automatically and immediately; no human triage step may delay the flag past the next publication cycle.
- Staleness thresholds by class: full-parity languages carry maximum staleness windows by severity (for example, substantive changes translated within five business days, moderate within one cycle, cosmetic quarterly), with breaches reported to the language owner.
- Drift sampling: each period, a sample of translated articles is compared against the current source by a bilingual reviewer for semantic drift (correct version binding but meaning that slipped); drift findings feed the translation pipeline's review checklist.
- Screenshot and UI-string gate: translated articles that reference interface elements are checked against the localized product strings, because a perfectly translated step that names a menu item that is not localized in the product fails the customer anyway.

## Validation evidence

Evidence the parity system works: the parity inventory export showing class coverage per language; the freshness distribution and oldest-substantive-stale list per language with item ages; the propagation log showing time from source change to translation flag and to republish; drift sampling results with findings and fixes; the divergence register with reasons and re-review dates; and fallback audits confirming flagged articles display the correct notice or substitution rather than silent staleness. A quarterly end-to-end test changes a substantive detail in a low-traffic source article deliberately and traces it to flag, work item, translation, republish, and notice clearing, with timings recorded.

## Failure modes and correction

Silent staleness is the defining failure: propagation breaks (the webhook between content system and translation queue dies), flags never fire, and customers read outdated guidance for months. Correction: the propagation log monitored for silence, the quarterly end-to-end trace test, and the freshness report as an independent check that does not depend on the propagation pipeline's own claims.

Well-formed but wrong-content translation is second: version binding is intact, the translator skipped or softened a caveat, and the article is fresh-but-false. Correction: drift sampling weighted toward risk-class articles, and a bilingual review requirement for safety, billing, and security content rather than machine-only throughput.

Unmanaged divergence accumulation is third: each language accumulates legitimate local differences until no one can say what parity means. Correction: the divergence register with re-review at every source change, and a periodic reconciliation that either folds the difference back into the source or restates it as a documented local variant.

Fallback inversion is fourth: the stale-notice mechanism itself hides content, or the source-version substitution shows an untranslated wall of text to customers who cannot use it. Correction: fallback audits per language and, for safety content, priority translation rather than long-running substitution.

## Limitations

Parity control scales linearly with language count and article churn; each added language multiplies propagation work and requires an accountable owner, and a language without an owner should not claim full parity. Machine translation narrows the cost but shifts effort to review, and risk-class content still requires human review. Drift sampling observes a fraction; it bounds risk rather than eliminating it. Languages with low traffic tempt demotion, but traffic follows usability: a stale corpus produces low traffic, which then justifies neglect, a loop the exposure-ranked report is designed to break. Finally, parity discipline cannot compensate for a source corpus that changes faster than any pipeline can follow; source change discipline is upstream of this article.

## Canonical sources

- W3C, Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
- W3C, Internationalization Best Practices: Handling Language Declarations, https://www.w3.org/International/articles/language-tags/
- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
