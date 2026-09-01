# Voice-of-Customer Archive Search and Privacy

A voice-of-customer archive — verbatims from surveys, support cases, calls, and forums — is most useful precisely when it is searchable, and most dangerous for the same reason. Full-text indexing of verbatims turns incidental personal details into permanently discoverable facts, and a simple query can assemble a profile of an individual across years of frustration. This article governs search over VoC archives: what is indexed, how minimization is enforced before indexing, and how legal hold intersects with search and deletion.

## Scope

Applies to search and retrieval over stored voice-of-customer content in any form: survey open-text, case narratives, transcribed interactions, community posts, and interview notes, whether accessed by customer-success staff, product teams, or analytics pipelines. Covers index construction, query governance, access logging, retention interplay, and legal-hold interfaces. Does not cover the primary collection of feedback (consent at capture follows intake policy), marketing use of testimonials (separate consent regime), or records subject to privilege, which route to legal before any indexing decision.

## Workflow or implementation guidance

1. **Classify before indexing.** Each content stream receives a classification: verbatims safe for indexing as-is, verbatims requiring redaction or pseudonymization first, and streams excluded from general indexing entirely. Classification is by stream and field, not by ad-hoc judgment at query time.
2. **Minimize at the index boundary.** Personal identifiers not needed for the analytical purpose — names, emails, phone numbers, account numbers embedded in text — are masked or replaced with stable pseudonyms before the token enters the index. Where an individual's identity is analytically necessary, access to the re-identification mapping is separately controlled.
3. **Index structure over raw noise.** Prefer indexing structured attributes (sentiment, topic tags, product area, case metadata) alongside minimized text, so many questions are answerable without full-text retrieval at all.
4. **Issue query guidance, not just access rights.** Authorized users still need rules: purpose-bound queries, no browsing by individual, no export of result sets containing personal data without a documented purpose, and reporting of inadvertent exposure of sensitive content found in results.
5. **Log every search.** Capture user, timestamp, query terms, result counts, and the records opened. Logs serve both security review and the periodic privacy audit that samples queries against their stated purpose.
6. **Define the legal-hold interface.** When legal issues a hold, the interface identifies affected custodians and content by the hold's scope; held content is preserved in place, its retention suspended, and — critically — its search treatment unchanged unless the hold directs otherwise. Holds prevent deletion; they do not silently widen access.
7. **Wire retention to disposition, not to the index.** Expiry of the retention period triggers content disposition and index entry removal in the same action, verified by a reconciliation that no index entry references purged content and no purged content remains discoverable.
8. **Review annually.** The classification, minimization rules, and query guidance are re-reviewed against current uses, with each new consumer of the archive routed through the same admission.

## Controls

- Purpose limitation: archive access requests state the business purpose; analytics and exploration operate on the minimized layer by default.
- Least privilege with role tiers — aggregate-only, minimized text, and full text with re-identification mapping — each tier separately granted and reviewed.
- Sensitive-category detection runs at intake to the index and diverts mental-health, medical, or safety-adjacent content to restricted handling rather than the general index.
- Query logs are immutable for a defined period and sampled in audit; anomalous patterns (same individual repeatedly targeted) trigger review.
- Legal-hold and disposition systems interlock so a hold blocks purge mechanically, not by email reminder.

## Validation evidence

Demonstrated compliance includes: the content-stream classification register with minimization rule per stream; an audit sampling raw source documents against index entries showing identifiers masked as configured; query log extracts with purpose statements for a review period; a test of the legal-hold interface showing held content survives an otherwise-due purge and is flagged in the hold register; and a disposition reconciliation after a purge cycle confirming zero dangling index entries. A penetration-style check — attempting to retrieve a known individual's full history with only aggregate-tier credentials — should fail by design.

## Failure modes and correction

- **Personal data leaks into the index** (a new stream onboarded without classification): quarantine the stream's entries, re-minimize, re-index, and correct the onboarding control that allowed bypass.
- **Over-broad hold** (a hold preserving the entire archive indefinitely): work with legal to narrow the custodial scope; document that over-inclusive preservation is itself a privacy harm to be cured, not a safe default.
- **Silent purge failure under hold**: the interlock alert fires; treat as a records incident with legal notified immediately.
- **Re-identification via query aggregation** (users combining minimized text with CRM lookups to identify authors): detect through log analysis, tighten join permissions, and retrain with the case as example.

## Limitations

Pseudonymization reduces but does not eliminate identifiability — verbatims are self-identifying by nature, and determined linking can defeat masking. Search governance cannot retroactively fix content collected without an adequate basis; the exposure window before classification existed remains. Finally, legal holds legitimately override some conveniences, and search scope may temporarily narrow or widen under counsel's direction in ways outside this article's control.

## Canonical sources

- [NIST Privacy Framework](https://www.nist.gov/privacy-framework) — privacy risk management, data minimization, and purpose-limitation controls.
- [NIST SP 800-88 Rev. 1, Guidelines on Media Sanitization](https://csrc.nist.gov/publications/detail/sp/800-88/rev-1/final) — disposition and sanitization discipline for purged archive content and index entries.

Local procedures should track the edition in force and be reviewed when the authority replaces it.
