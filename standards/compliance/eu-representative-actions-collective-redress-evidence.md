# EU representative-actions collective-redress evidence

**Issue:** Directive (EU) 2020/1828 enables qualified entities to seek injunctive and redress measures for covered consumer-law infringements. A defect affecting many consumers can therefore become a cross-border evidence and remediation problem, even when no individual support case appears material.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Applicability and controls

- Map products, trader entities, consumer locations, channels, and practices to the Union laws listed in Annex I and their national implementation.
- Preserve the exact terms, disclosures, consent flows, prices, ranking or targeting rules, cancellation paths, and software versions shown to each affected cohort.
- Give legal-hold instructions priority over routine retention and deletion while minimizing access and keeping personal data appropriately protected.
- Correlate complaints, refunds, chargebacks, regulator notices, experiment variants, and incident reports to detect a collective issue early.
- Maintain a reproducible cohort query with versioned logic, input provenance, exclusions, counts, and review approval.
- Design remediation that can stop the practice, identify affected consumers, calculate redress consistently, prevent duplicates, and evidence delivery.
- Keep communications accurate and non-retaliatory; do not obstruct qualified entities or consumer rights.

## Implementation and tests

Run a dry exercise from a policy or interface defect through scope determination, legal hold, evidence export, cohort calculation, injunction-style stop control, refund computation, customer communication, and reconciliation. Test missing historical UI assets, migrated identifiers, deceased or unreachable consumers, multiple currencies, partial prior refunds, reseller channels, and cross-border cohorts.

Have an independent reviewer reproduce cohort counts and monetary calculations from the retained inputs. Record data-quality limitations rather than silently excluding uncertain cases.

## Gotchas and legal caveat

The Directive establishes a framework for representative actions by qualified entities, but Member States’ standing, procedure, funding, limitation, opt-in or opt-out, evidence, and remedy rules can differ. Its Annex I scope and national transposition must be checked for the specific claim.

A compliance evidence store is not a reason to retain all consumer data indefinitely. Apply necessity, proportionality, legal hold, and security together. This is not legal advice.

## Official sources

- [EUR-Lex: Directive (EU) 2020/1828](https://eur-lex.europa.eu/eli/dir/2020/1828/oj)
- [European Commission: Representative actions directive](https://commission.europa.eu/law/law-topic/consumer-protection-law/representative-actions-directive_en)
