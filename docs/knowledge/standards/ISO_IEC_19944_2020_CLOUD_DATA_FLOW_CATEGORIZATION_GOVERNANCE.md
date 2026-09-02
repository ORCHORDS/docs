# ISO/IEC 19944 Cloud Data Flow Categorization Governance

## Purpose

Govern the application of ISO/IEC 19944 (cloud services — cloud service and device requirements for flow of data) so that data flows between cloud services and devices are described in a standard structure: the data categories exchanged, the purposes, and the parties — enabling deliberate decisions about what data leaves which boundary, rather than implicit flows discovered during incident response.

## Scope

Applies to every cloud service the studio consumes or provides where data flows across service boundaries. Covers data flow description, categorization, and the disclosures owed to data subjects and customers about those flows. Does not cover the security of data in transit (covered by security guidance) or the underlying contract terms.

## Workflow

1. Inventory data flows per cloud service using the 19944 descriptive model: what data categories flow (per the standard's categorization), in which direction, to which party, for which stated purpose.
2. Categorize the data per the standard's framework: content created by users, activity data, device data, and derived data — because categories carry different subject expectations and obligations.
3. Record the purpose binding for each flow: the stated purpose for which the data flows, aligned with what the service discloses; flows serving purposes not disclosed are governance findings even when technically authorized.
4. Map device-originated flows explicitly where services interact with devices: device telemetry, configuration data, and user content each categorized and purpose-bound.
5. Verify flow descriptions against actual traffic on a defined cadence: observed data categories versus described categories; divergence means the description or the implementation is wrong, and both are corrected.
6. Use flow descriptions to drive downstream decisions: privacy notices, transfer assessments, and provider evaluations consume the categorized flow model as their input.
7. Version flow descriptions with the service: material changes to flows (new category, new purpose, new party) update the description before the change ships, with the update treated as a design change.

## Controls and evidence

- Data flow inventory per service using the 19944 model.
- Data categorization records per flow with category and purpose binding.
- Cadence-based verification results comparing observed vs described flows.
- Change records updating flow descriptions before shipping.
- Links from flow descriptions to privacy notices and transfer assessments.

## Validation

- Sample one service's flow description against observed traffic and confirm categories and parties match.
- Confirm every flow has a stated purpose consistent with external disclosures.
- Confirm recent flow changes updated the description before shipping.

## Failure correction

- **Observed flow not in description** → update the description, assess the undisclosed-period obligations, and fix the change gate that let it ship undescribed.
- **Purpose mismatch with disclosure** → align: change the practice or the disclosure, through review; silent divergence is prohibited.
- **Categorization errors found in verification** → re-categorize, propagate to dependent notices and assessments, and record the correction.

## Limitations

- The descriptive model's value depends on verification against real traffic; unverified inventories drift.
- Category granularity is a judgment; align granularity with the decisions the description supports.
- The standard describes flows; legal obligations per jurisdiction still require separate analysis.

## Scope note

This article is part of the standards leaf. Cross-reference: `ISO_IEC_19944_2017_CLOUD_DATA_GOVERNANCE.md` (platforms leaf), `ISO_IEC_22123_1_2023_CLOUD_OVERVIEW_GOVERNANCE.md` (platforms leaf), and `W3C_DCAT_3_DATA_CATALOG_TEMPLATE_GOVERNANCE.md` (templates leaf).

## Canonical sources

- ISO/IEC 19944-1:2020 — Cloud computing — Cloud services and devices — Data flow descriptions: https://www.iso.org/obp/ui/#iso:std:iso-iec:19944:-1
- ISO/IEC 19944 (2017 edition): https://www.iso.org/obp/ui/#iso:std:iso-iec:19944:ed-1
- ISO/IEC 22123-1:2023 — Cloud computing — Concepts and vocabulary: https://www.iso.org/standard/85747.html
- W3C DCAT 3 — Data Catalog Vocabulary: https://www.w3.org/TR/vocab-dcat-3/
- ISO/IEC 27018:2019 — Code of practice for PII in public clouds: https://www.iso.org/standard/76559.html
