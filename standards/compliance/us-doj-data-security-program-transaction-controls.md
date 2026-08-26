# US DOJ Data Security Program transaction controls

**Issue:** Cross-border vendor, employment, investment, or data-brokerage access is approved through an ordinary privacy review even though the US Data Security Program can prohibit or restrict transactions involving US Government-related data or bulk sensitive personal data.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Scope

The Department of Justice Data Security Program under 28 C.F.R. Part 202 took effect on April 8, 2025. It governs specified transactions that give a country of concern or covered person access to US Government-related data or bulk US sensitive personal data. It operates as a national-security control in addition to privacy, sanctions, export-control, procurement, and sector-specific obligations.

## Decision workflow

1. Identify the US person, counterparty, beneficial owners, operators, subprocessors, and every jurisdiction from which access is possible.
2. Classify the data: government-related data, genomic, biometric, precise geolocation, health, financial, or covered personal identifiers.
3. Calculate the applicable bulk threshold across related transactions rather than reviewing contracts in isolation.
4. Classify the transaction type and access mechanism, including remote administration, model training, support, employment, investment, and data brokerage.
5. Screen countries of concern and covered persons using the current DOJ program materials and lists.
6. Determine whether the transaction is prohibited, restricted subject to CISA security requirements, exempt, licensed, or outside scope.
7. Obtain legal approval before access begins and attach the decision, assumptions, and evidence to the contract and technical access policy.

## Controls

- Maintain a data and access-flow inventory that includes cloud regions, support paths, identities, and onward transfer.
- Put geographic, identity, device, logging, minimization, encryption, and data-level restrictions into enforceable technical controls.
- Flow restrictions and audit duties to vendors and require notice before ownership, personnel, location, or subprocessors change.
- Preserve due-diligence records, rejected-transaction reports, annual reports, audits, licenses, and advisory opinions for their required periods.
- Re-screen counterparties and reassess aggregation when the data set, purpose, access model, or corporate control changes.
- Route suspected violations through counsel and the incident-response process; do not quietly terminate access and discard evidence.

## Verification

Sample a covered data flow from source to every administrator and subprocessor. Reconcile the contract, identity provider, cloud audit logs, egress policy, data classification, and screening result. Test that a covered geography and an unapproved operator are denied, logged, and escalated.

## Gotchas

The program is not a general data-localization rule, and an exemption must be matched to the actual transaction. Government-related data can be covered without a bulk threshold. De-identification or encryption alone does not necessarily remove access risk. Guidance does not replace the regulation or case-specific legal analysis.

## Official sources

- [DOJ National Security Division: Data Security Program](https://www.justice.gov/nsd/data-security)
- [DOJ Data Security Program Compliance Guide](https://www.justice.gov/opa/media/1396356)
- [28 C.F.R. Part 202](https://www.ecfr.gov/current/title-28/chapter-I/part-202)
