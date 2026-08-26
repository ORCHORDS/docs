# interchange-fee-optimization

**Issue:** Interchange is the largest single component of card acceptance cost, paid to the issuing bank on every transaction, and unlike the processor's markup it is not negotiable by contract: it is earned (or lost) based on how each transaction is coded, what data accompanies it, and which network and product it qualifies under. A merchant sending bare-minimum authorization data systematically downgrades to more expensive interchange categories, silently paying tens of basis points more than identical transactions with richer data. The problem intensified in 2025 when Visa replaced its legacy Level 2/Level 3 commercial interchange programs with the Commercial Enhanced Data Program (CEDP), introducing stricter validation so that incomplete or invalid enhanced data no longer qualifies for reduced rates. Engineering owns this: interchange qualification is determined by fields your systems send at authorization time.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Qualification mechanics

1. **Understand the fee stack before optimizing it.** A card transaction carries interchange (to the issuer, typically 1-2%+ for credit, capped for regulated US debit), scheme fees/assessments (to Visa/Mastercard), and the processor margin. Interchange optimization only moves the first bucket; processor negotiation moves the third; nothing you do moves the second.
2. **Interchange is a qualification program, not a rate card.** Each interchange category has registration and per-transaction requirements (card product, merchant category code, acceptance method, data elements, settlement timing). Falling short on any requirement downgrades the transaction to a worse category, and the downgrade is invisible unless you pull qualification reports.
3. **Know the regulated debit landscape.** US Reg II (Durbin) caps interchange on debit from banks above the asset threshold at roughly 21 cents plus 0.05% plus a fraud adjustment, with exempt issuers uncapped; debit-routing rules (two unaffiliated networks) are a compliance requirement, not an optimization. Exemption thresholds are inflation-adjusted periodically, so re-derive BIN-level routing tables rather than hardcoding them.

## Enhanced data submission

1. **Submit Level 3 line-item detail on commercial transactions.** B2B, purchasing, and government cards qualify for significantly lower interchange when the authorization and settlement carry line-item data: item SKU/description, quantity, unit of measure, commodity code, freight and duty amounts, and tax. Industry estimates put the savings at 0.5-1.5% of transaction value on commercial-card volume.
2. **Re-qualify for Visa CEDP, not legacy Level 2/3.** Visa's 2025 Commercial Enhanced Data Program replaced the legacy Level 2/3 interchange structure for commercial transactions and tightened validation: bad or incomplete enhanced data now disqualifies the discount entirely instead of partially qualifying. Audit every field your order pipeline emits (tax amount zero-vs-null, missing commodity codes, free-text descriptions) against CEDP rules, and add pre-submission validation so downstream systems cannot emit unqualified payloads.
3. **Preserve enhanced data through settlement.** Interchange qualification is assessed on settlement/clearing data, not the authorization alone. Captures, partial captures, and adjustments must carry the same enhanced data set or the qualification is lost at the moment of capture.

## BIN-level detection and routing

1. **Detect commercial cards at checkout.** Use BIN metadata (via your PSP or a BIN service) to identify corporate, purchasing, and government cards in real time, then dynamically collect the extra fields (po number, tax id, line items) only from those customers instead of burdening every consumer checkout.
2. **Route exempt-issuer debit deliberately.** Debit from exempt (sub-threshold) issuers carries uncapped interchange, which can exceed credit rates; dual-routing rules make network choice material. Maintain a BIN-to-network preference table and re-evaluate it as the Fed adjusts the exemption threshold and network pricing changes.
3. **Get MCC classification right.** The merchant category code assigned to your account determines entire interchange program tables. Misclassification (for example, a SaaS business coded as general retail instead of its eligible category) is one of the most common and least visible overpayment sources.

## Monitoring downgrades

1. **Pull interchange qualification reports monthly.** Processors expose reports showing each transaction's qualified interchange category versus the best possible category. Build a job that diffs the two, aggregates downgrade reasons, and prices the gap: this single number usually justifies or kills optimization work.
2. **Alert on downgrade-rate shifts.** A pipeline change (new checkout flow dropping the tax field, a capture service losing line items) shows up as a step change in downgrades. Alerting on the downgrade rate, not just totals, catches regressions within days instead of at annual statement review.
3. **Reconcile billed interchange against expected interchange.** On interchange-plus pricing you can compute expected fees from qualification data; variances indicate processor mis-billing or qualification data you are not seeing.

## Commercial structure

1. **Prefer interchange-plus over blended pricing at scale.** Blended rates hide downgrades and scheme fees inside one number; interchange-plus (IC++) itemizes interchange, scheme fees, and margin, which is a precondition for any of the monitoring above. Blended pricing is reasonable only at low volume where audit cost exceeds savings.
2. **Verify PCI validity and CPS-style registrations with your acquirer.** Whether Visa CPS programs or equivalent registrations, qualification often requires acquirer-side setup (data capture formats, registration of your merchant profile). Engineering cannot fix what the acquirer never enabled; verify registrations annually because program requirements change on scheme schedules.
