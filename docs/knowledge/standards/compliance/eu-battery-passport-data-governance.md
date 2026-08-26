# EU Battery Passport Data Governance

**Issue:** Regulation (EU) 2023/1542 requires an electronic battery passport from 18 February 2027 for specified LMT, industrial, and electric-vehicle batteries, with accuracy, access, interoperability, and lifecycle obligations.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Determine passport scope by battery category and capacity, and assign the economic operator accountable for accuracy, completeness, and currency.
- Bind the QR code to a unique identifier and a versioned, individual-battery record.
- Map every Annex XIII field to its source, owner, update trigger, access class, and validation rule.
- Publish machine-readable, structured data through open interoperable formats without vendor lock-in.
- Enforce the differentiated access rights in Article 78 rather than exposing the whole record publicly.
- Preserve links when a battery is reused, repurposed, or remanufactured, and transfer stewardship when the Regulation assigns responsibility to another operator.
- Define end-of-life handling for the passport after recycling.

## Verification

- Reconcile passport fields to manufacturing, due-diligence, repair, state-of-health, and lifecycle source systems.
- Test QR resolution, unique-identifier stability, role-based access, portability, and update propagation.
- Simulate responsibility transfer and verify the new passport links to the original passport chain.
- Recheck the consolidated Regulation and delegated acts before production.

## Gotchas

A static QR landing page is not a compliant passport. Some information is public while other fields are restricted to legitimate actors, and responsibility can move during the battery lifecycle.

## Official sources

- [Regulation (EU) 2023/1542, consolidated text](https://eur-lex.europa.eu/eli/reg/2023/1542/2025-07-31/eng/)
