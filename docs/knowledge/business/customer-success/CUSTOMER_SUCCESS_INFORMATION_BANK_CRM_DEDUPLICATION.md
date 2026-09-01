# Customer Success Information Bank CRM Deduplication

When a support information bank — the accumulated case histories, escalation notes, and resolution narratives — is joined to CRM records to build a customer view, duplicate and near-duplicate records corrupt the result. One customer appearing as three CRM accounts splits their history across identities; two customers merged under one record leak each other's context. This article defines deterministic deduplication rules for that join: matching keys, survivorship of conflicting attributes, and the review path for ambiguous cases.

## Scope

Covers the matching and deduplication performed when joining support information banks with CRM account and contact records for customer-success analysis, health scoring, and reporting. Applies to batch joins and to incremental updates from ongoing case creation. Does not cover CRM duplicate prevention at data-entry time (a distinct intake control), cross-organization identity resolution for marketing attribution, or the deletion of records under erasure requests, which follows privacy disposition procedure. Where the join output feeds contractual reporting, the contract's account-definition controls and this article's output must be reconciled explicitly.

## Workflow or implementation guidance

1. **Normalize before matching, never after.** Establish canonical forms for the join keys: case-insensitive domain stripping for email domains, legal-suffix removal for company names, whitespace and punctuation normalization, and Unicode normalization of identifiers. Normalization rules are versioned; changing them invalidates prior match decisions and requires a documented re-run.
2. **Match on a key hierarchy, strongest first.** Prefer system-generated identifiers shared across systems (account identifier present in both the support bank and CRM), then verified email domains of administrative contacts, then exact normalized company identifier plus region, then fuzzy organization-name matching only as a candidate generator — never as an automatic merge trigger.
3. **Set match thresholds with asymmetric caution.** A false merge contaminates two customers' records and is hard to unwind; a missed match merely duplicates. Default configuration therefore requires high confidence to merge and routes everything else to human review queues sized and staffed to a defined service level.
4. **Apply survivorship rules per attribute, not per record.** When merged records disagree, each attribute resolves by a declared rule: contractual data from the entitlement system, contact details by most-recent-verified, industry classification by the enriched master, and free-text notes concatenated with origin labels rather than overwritten. "Most recently edited" is an acceptable survivorship rule only where no better authority exists, and its use is recorded.
5. **Preserve the merge genealogy.** Every merge records which source records combined, on what keys, at what confidence, by which rule or reviewer, and when. Unmerge must be executable from this genealogy alone.
6. **Handle the support-bank side too.** Duplicate cases for the same customer issue are linked, not merged, when each case carries its own service-level commitments; merging case records destroys SLA evidence. Linking preserves both narratives under one customer identity.
7. **Run incremental matching with a look-back window.** New CRM records match against recent and high-signal prior records; a periodic full re-pass catches slow-forming duplicates that incremental windows miss.
8. **Publish deduplication run metrics.** Each run reports match counts by rule, review-queue depth, merge and unmerge counts, and confidence distribution, so drift in data quality is visible over time.

## Controls

- Automatic merges are permitted only above the high-confidence threshold using the two strongest key tiers; all fuzzy matches require human confirmation.
- Reviewers confirming or rejecting candidate pairs see the evidence basis (matching keys, shared identifiers, conflicting attributes) — never just a similarity score.
- Join outputs containing personal information inherit the more restrictive retention of the two source systems; deduplication does not extend retention.
- Attribute survivorship rules are configuration, not code — reviewed and versioned like any other control artifact.
- Emergency unmerge capability is tested on a schedule, because an untested recovery path is indistinguishable from none.

## Validation evidence

A deduplicated join is evidenced by: the normalization rule version in force; the run report with matches by tier, review dispositions, and confidence distributions; a sample of ten merges traced through genealogy back to source records with their original attributes; a sample of five rejected candidates showing why matching failed; and a successfully executed test unmerge restoring the pre-merge state. For analytics use, additionally show that per-customer case counts after the join reconcile to the support system's own totals within a defined tolerance.

## Failure modes and correction

- **Mass false merge** (a normalization change collapses distinct customers, such as stripping too much from similar names): halt the run, unmerge via genealogy, correct the rule, and re-run from the pre-run snapshot; notify consumers of the affected reports.
- **Silent duplicate growth** (review queue backlogged, no one notices): the queue-depth metric triggers escalation before backlog becomes structural, and automatic tier confidence is reviewed for being set too conservatively for workload.
- **Survivorship regression** (a configuration edit quietly changes which value wins): configuration change control with before-and-after attribute samples on a fixed test corpus catches this before production.
- **Cross-contamination discovery after the fact** (one customer's case notes visible under another's view): treat as a privacy incident, execute unmerge, and review access logs for exposure during the merged interval.

## Limitations

Deduplication quality is bounded by source data quality; inconsistent self-identification by customers defeats even careful rules. Organizational complexity — subsidiaries, franchises, holding structures — creates genuinely ambiguous identity questions that no threshold resolves, and these remain human decisions. The join reflects a point in time; continuous data entry means deduplication is a maintained state, not a completed project.

## Canonical sources

- [ISO/IEC 8000-110 Master data](https://www.iso.org/standard/78941.html) — exchange of master data and attribute-level quality management for record matching and survivorship.
- [NIST SP 800-61 Rev. 2](https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final) — incident-handling discipline applied to merge-failure response and evidence preservation.

Confirm the ISO standard's currency on iso.org before local adoption; local procedures should track the edition in force.
