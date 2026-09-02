# ISO/IEC 30134-4 Data Centre Inventory Template Governance

## Purpose
Establish the governance pattern for templating data centre inventory and asset records per ISO/IEC 30134-4 (Information technology — Data centres — Key performance indicators — Part 4: IT Equipment Energy Efficiency for Servers).

## Scope
Applies to every data centre inventory record maintained by the studio, including servers, storage devices, network equipment, and auxiliary infrastructure.

## Workflow
1. Use a templated data centre inventory record with mandatory fields per ISO/IEC 30134-4: asset identifier, asset type, manufacturer, model, serial number, location (data centre, room, rack, U-position), installation date, and decommissioning date.
3. For each server asset, capture the IT energy efficiency metrics: rated power, average utilization, PUE contribution, and operating hours; link these metrics to the asset identifier.
5. Maintain a power and cooling capacity record per rack, including breaker capacity, PDU capacity, and cooling capacity; reconcile the rack-level record with the asset records quarterly.
7. Track asset lifecycle events (installation, relocation, decommissioning) in an event log keyed to the asset identifier; capture operator identity, timestamp, and rationale.
9. Establish a decommissioning workflow that includes data sanitization (per NIST SP 800-88 R2), chain-of-custody documentation, and final disposal or recycling record.

## Controls and evidence
- Asset inventory record per data centre asset with type, manufacturer, model, location, and lifecycle status.
- Power and cooling capacity record per rack with breaker capacity, PDU capacity, and cooling capacity.
- Lifecycle event log per asset with operator identity, timestamp, and rationale.
- Decommissioning record with data sanitization evidence, chain-of-custody documentation, and disposal or recycling outcome.

## Validation
- Reconcile the asset inventory with the physical inventory for a sample of 10 racks and confirm zero unrecorded assets.
- Verify that each decommissioned asset has a data sanitization record and a chain-of-custody record.
- Confirm that rack-level power and cooling capacity records are consistent with the asset-level records.

## Failure correction
- **Unrecorded asset discovered during reconciliation** → open an inventory record, document the gap, and tighten the inventory refresh cadence.
- **Decommissioning record missing data sanitization evidence** → suspend the decommissioning, document the gap, and remediate before completing the disposal.
- **Rack capacity exceeded by asset installation** → halt further installations, document the over-commitment, and remediate the capacity.

## Limitations
- ISO/IEC 30134-4 is part of a larger series; refer to ISO/IEC 30134-2 for power usage effectiveness (PUE) and ISO/IEC 30134-3 for renewable energy factor (REF).
- Inventory reconciliation is a snapshot in time; continuous monitoring tools are recommended for high-change environments.
- Decommissioning data sanitization must be appropriate to the storage media type (e.g., SSD vs HDD); refer to NIST SP 800-88 R2 for guidance.

## Scope note
This article is part of the templates leaf. Cross-reference: NIST_SP_800_88_R2_MEDIA_SANITIZATION_TEMPLATE_GOVERNANCE.md, ISO_9001_2015_QUALITY_MANAGEMENT_SYSTEM_TEMPLATE_GOVERNANCE.md, ISO_27018_CLOUD_PII_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- ISO/IEC 30134-4:2017 — Information technology — Data centres — Key performance indicators — Part 4: IT Equipment Energy Efficiency for Servers: https://www.iso.org/obp/ui/#iso:std:iso-iec:30134:-4
- ISO/IEC 30134-2:2016 — Information technology — Data centres — Key performance indicators — Part 2: Power usage effectiveness (PUE): https://www.iso.org/standard/63561.html
- ISO/IEC 30134-3:2016 — Information technology — Data centres — Key performance indicators — Part 3: Renewable energy factor (REF): https://www.iso.org/obp/ui/#iso:std:iso-iec:30134:-3
- NIST SP 800-88 Rev 2 — Guidelines for Media Sanitization: https://csrc.nist.gov/publications/detail/sp/800-88/rev-2/final
- ANSI/TIA-942 — Telecommunications Infrastructure Standard for Data Centers: https://www.tiaonline.org/standards/