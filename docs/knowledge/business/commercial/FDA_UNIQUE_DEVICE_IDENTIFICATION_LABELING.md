# FDA Unique Device Identification (UDI) Labeling

## Devices and packages within UDI scope

The Unique Device Identification system requires medical device labelers to mark devices with a Device Identifier (DI) that identifies the labeler and the specific version or model, and a Production Identifier (PI) that captures the lot, serial, expiration, or manufacture date. The FDA established the rule under 21 CFR part 801 subpart B, with technical specifications published by the FDA-recognized issuing agencies (GS1, HIBCC, ICCBBA). Labelers of devices in commercial distribution must also submit DI data to the FDA's Global Unique Device Identification Database (GUDID). This article covers label assignment, marking, GUDID submission, and labeler status updates. It does not cover 21 CFR part 803 Medical Device Reporting, nor does it cover 510(k) or premarket approval determinations.

## DI assignment, labeling, and GUDID sequence

1. **Determine the device class and compliance date.** Class III devices, devices licensed under the Public Health Service Act, and implantable, life-supporting, or life-sustaining devices had earlier compliance dates; Class II devices followed; non-class-II-exempt Class I devices followed per the FDA's published schedule. The current compliance status is verified against the FDA UDI Helpdesk and recorded.
2. **Choose an issuing agency.** GS1, HIBCC, and ICCBBA are recognized. Each agency assigns its own prefix and identifiers; the labeler commits to one system and uses it across the product line.
3. **Assign the Device Identifier.** The DI is a fixed segment of the UDI that identifies the labeler and the specific device model; it is created by combining the agency-issued labeler identification with a model identifier assigned by the labeler.
4. **Assign the Production Identifier.** The PI is the variable segment of the UDI that identifies the unit of production (lot/batch, serial, expiration date, or manufacture date). Some combination is acceptable; for example, an implantable hip stem may use a serial number only, while an orthopedic plate may use both a lot number and an expiration date.
5. **Apply the UDI to the label and to multiple packaging levels.** The UDI must appear on the device label, on each level of packaging, and on sterile packaging where the device is intended to remain sterile until use. Certain Class I devices that are exempt from individual labeling requirements are still subject to the UDI rule if they are intended to be used more than once and are reprocessed between uses.
6. **Submit the DI record to GUDID.** The DI portion of the UDI is submitted to the GUDID using either the FDA's GUDID Web Interface or the HL7 SPL submission channel. The PI is not submitted because it is variable data; GUDID holds only the static DI and the device characteristics.
7. **Maintain on material change.** New versions, new packaging configurations, or changes to the brand name require either a new DI or a controlled update to the existing DI; the FDA UDI Helpdesk documentation describes the GUDID record update path.

## Device identifier and production identifier data

A GUDID record carries the DI, the company name, the brand name, the version or model number, the device description, the GMDN (Global Medical Device Nomenclature) code or equivalent, the FDA premarket submission number (510(k), PMA, HDE, or "exempt"), the FDA product code, the device class, the size and unit of measure, the storage and handling conditions, the latex and DEHP indicators, the MRI safety status, the country of origin, and the publicly available label URL where consumers can access the labeling. The structured product label submitted via HL7 SPL must include the same fields, with the assign-authority namespace set to the issuing agency's identifier.

## Label-to-GUDID verification evidence

Validation has four components. First, the issuer-provided barcode is scanned at the label line and decoded to confirm a valid DI segment. Second, a GUDID record search returns the DI as published and shows a publication date. Third, the SPL submission returns a GUDID ID, and the record is fully viewable in the public AccessGUDID database. Fourth, periodic GUDID audits compare the internal DI register against AccessGUDID and against the device label, and any divergence triggers a correction before the next shipment.

## UDI discrepancy correction

- **DI error in published record.** The labeler uploaded the wrong device description. The operator opens the GUDID record, edits the controlled fields, and resubmits the SPL; the correction is reflected in AccessGUDID without a new DI assignment.
- **Wrong issuing-agency code.** A DI built under HIBCC was submitted with a GS1 prefix; GUDID rejected the submission. The operator rebuilds the DI under the correct prefix, registers a new labeler identification, and re-uploads; the mismatched DI is never used on a printed label.
- **Missing sterile packaging UDI.** The unit-of-use packaging bears a UDI but the outer carton does not. The label design is corrected so every packaging layer above the device itself carries a UDI including the appropriate non-sterile indicator.
- **PI omitted on variable data.** A lot-controlled device ships without a visible lot number or expiration date. The received shipment is held at the dock, the supplier is notified, and a corrected label is requested before the goods are released into inventory; an internal CAPA is logged because the labeling deviation is a citable FDA finding.
- **Compliance date missed.** A new device is launched before its GUDID entry is published. The launch is paused, the GUDID record is published, and the launch resumes only when AccessGUDID returns the DI; releasing a non-compliant device without a published DI is an FDA enforcement trigger.

## Exceptions and transition limits

A published UDI record does not establish device clearance, approval, safety, or conformity with other labeling rules. Exceptions and compliance policies vary by device and date; labelers must verify the current FDA rule, issuing-agency specification, and enforcement guidance for the exact product.

## Canonical sources

- **Primary authority 1:** U.S. Food and Drug Administration, *Unique Device Identification System (UDI System)* — https://www.fda.gov/medical-devices/unique-device-identification-system-udi-system
- **Primary authority 2:** Code of Federal Regulations, *21 CFR Part 801 Subpart B — Labeling Requirements for Unique Device Identification* — https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-801/subpart-B
