# Geo-Targeting Boundary Accuracy Proof

## Scope

This control governs the production, custody, and replay of evidence that a marketing campaign that targets by geography actually conformed to the geographic boundaries the campaign was designed to respect. It applies to paid-media targeting audiences defined by country, region, metropolitan area, DMA, zip code, custom polygon, geofence, GPS radius, IP-derived country or region, mobile carrier country code, and language-derived locale. It also applies to the suppression side — places where the campaign was designed to exclude a geography (because of sanctions, embargo, regulatory restriction, language mismatch, fraud prevalence, or contractual limit).

The governing reference is the U.S. Department of Commerce Bureau of Industry and Security (BIS) export-control regime, which publishes and administers the Export Administration Regulations and related designations. While BIS-administered rules do not directly regulate consumer marketing, they are the operational baseline for handling maps, address lists, customer-locator data, and technical assistance that may be subject to U.S. export controls. The same discipline — source provenance, documented boundary, replayable evidence, controlled revision, recipient list — applies to marketing geo-targeting as to other operational decisions that depend on geographic boundaries.

## Workflow or implementation guidance

The geo-targeting accuracy workflow proceeds in six steps.

1. Name the geographic basis. Each audience in a campaign names the basis for the geography: which platform or provider supplies the boundary, which version of the boundary file or shape is in use, how often it is updated, and how the audience member is mapped to the boundary.
2. Capture the boundary at campaign launch. At the moment a campaign is launched or a significant audience change is made, a snapshot of the boundary file or shape is captured. The snapshot includes the source, version, effective date, defining attributes, and a SHA-256 hash or equivalent identifier.
3. Capture the audience-to-boundary mapping. The mapping of audience members to geography is recorded at the same moment, including the rule by which members are matched (postal code table, IP block, geofence polygon), the matching provider, and the provider version.
4. Capture the recipient list. For each marketing vendor or platform that receives the audience, the recipient list is recorded, with the boundary version handed off, the date of hand-off, and any contractual restrictions on use.
5. Test. Before and during launch, a sample of records is tested by an independent evaluator against the documented boundary: a record that should be inside is verified as inside, a record that should be outside is verified as outside, and a record whose boundary is contested (a postal code that straddles two regions, a customer record on the edge of a DMA) is escalated for review.
6. Reconcile and revise. After changes to boundaries or to audience mapping rules, the campaign is reconciled with the new boundary. The reconciliation log records what was added, what was removed, and why.

## Controls

The controls in this workflow are designed to make boundary decisions reconstructible.

- Each audience has a single named source for the boundary and a single named source for the mapping. Multiple sources without a documented reconciliation are a defect, not a choice.
- Boundary versions are immutable: once a version is used in a campaign, it is preserved with the campaign record. Future versions do not retroactively change past campaigns.
- Provider updates are monitored. A provider version change triggers a re-evaluation of active campaigns to determine whether the new boundary materially changes the included members.
- Edge cases (postal codes that span regions, addresses on postal-code boundaries) are documented. Records with contested geography are escalated rather than silently forced into one region or the other.
- Recipient lists are recorded with the boundary version handed off. A recipient that receives an old boundary while the campaign uses a new boundary is a defect.
- Sanctions and embargo lists are reconciled separately from marketing audiences and are not modified by marketing-side changes. Compliance review owns the sanctions list; marketing owns the audience list, and the two are reconciled at each campaign launch.
- Provenance (where the boundary came from, who updated it, when, and on what authority) is recorded with the audit record.

## Validation evidence

Evidence is collected at campaign launch and audited periodically.

- Boundary snapshot: file or shape, source, version, date, hash, defining attributes.
- Audience-to-boundary mapping: rule, provider, provider version, sample-match accuracy where available.
- Recipient list: each vendor, the boundary version handed off, hand-off date, contractual restriction.
- Reconciliation log: changes due to boundary updates, audience-mapper updates, or sanctions or embargo changes, with effect on the campaign.
- Periodic test result: an independent evaluator's pass on the active boundary, listing inside-matches, outside-matches, and edge cases.

## Failure modes and correction

Common failures include using an old boundary without a version check, allowing an audience provider to silently update its mapping table, mapping records by approximate rules without documenting which records are approximate, designing an "exclude" rule that accidentally uses a different boundary file from the "include" rule, and relying on language as a geography proxy without acknowledging countries where that language is minority. Another failure is failing to reconcile marketing-side geography with compliance-side sanctions and embargo controls when those controls treat the same geography differently.

Correction starts by re-evaluating the affected audience against the correct boundary: re-exporting the audience with the correct boundary, segmenting the record by what was inside the old boundary and is outside the new one (and the converse), and removing records that should no longer be in the audience. Where the failure was a system-level mapping defect, the mapping provider is re-tested before the campaign resumes. Where the failure was a recipient list issue, the recipient is asked to revert to the correct boundary and confirm the records affected. The boundary version records are updated and the audit log captures the change. Where the failure implicates sanctions or embargo, the matter is referred to compliance and counsel.

## Limitations

This control does not decide whether a particular piece of content requires an export license, whether a particular data transfer is subject to BIS regulations, or whether a particular marketing message to a particular geography is permissible under U.S. export control, foreign sanctions, or anti-boycott rules. It does not adjudicate the boundaries themselves: a DMA, a region, a country boundary, or a postal-code split is taken from a supplier and trusted only insofar as the supplier is trusted. It does not address geolocation accuracy at the device level, which is governed by separate consent and accuracy regimes.

## Canonical sources

- **Primary authority 1 — U.S. Department of Commerce, Bureau of Industry and Security, DS-EAR policy guidance portal:** [https://www.bis.doc.gov/index.php/policy-guidance/department-of-state-export-administration-regulations-ds-ear](https://www.bis.doc.gov/index.php/policy-guidance/department-of-state-export-administration-regulations-ds-ear)
- **Primary authority 2 — U.S. Department of Commerce, BIS, Export Administration Regulations (current codification, eCFR Title 15 Part 730 et seq.):** [https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C)
