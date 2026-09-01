# PCI DSS 4.0 Cardholder Data Environment Scoping

## Account-data environment boundary

The Payment Card Industry Data Security Standard (PCI DSS) version 4.0, published by the PCI Security Standards Council (PCI SSC), sets the security requirements for entities that store, process, or transmit cardholder data or that can otherwise impact the security of that data. The standard applies to merchants, processors, acquirers, issuers, and service providers as defined in the standard's glossary. This article covers the operational workflow for scoping the cardholder data environment (CDE), defining the boundaries, and capturing validation evidence. It does not cover the brand-specific reporting obligations (e.g., Visa's Report on Compliance submission deadlines) which are layered on top of the standard.

## Data-flow discovery and scope confirmation

1. **Confirm the entity's role and applicable merchant level.** The entity determines whether it is a merchant, a service provider, or both, and computes its merchant level based on transaction volume. The applicable Report on Compliance or Self-Assessment Questionnaire (SAQ) is selected accordingly.
2. **Inventory every system that handles cardholder data.** The inventory includes every component that stores, processes, or transmits the Primary Account Number (PAN), the cardholder name, the expiration date, the service code, or the full magnetic-stripe data. The inventory also includes any system that can otherwise impact the security of the CDE, even if it does not directly handle cardholder data.
3. **Define the CDE boundary.** The boundary is established by enumerating all in-scope systems and the connections between them, including shared infrastructure (network segments, virtual hosts, cloud resources). The boundary decision must consider both "connected to" and "shared services" relationships.
4. **Segment the CDE.** If segmentation is in use to reduce scope, the segmentation implementation is documented and tested at least annually and after any significant change per requirement 11.4.5. The segmentation controls (VLANs, internal firewalls, network access controls) are validated as effective.
5. **Map the 12 principal requirements.** The 12 principal requirements (install and maintain network security controls, apply secure configurations, protect stored account data, protect with strong cryptography during transmission, protect from malicious software, develop and maintain secure systems, restrict access by business need, identify users and authenticate access, restrict physical access, log and monitor, test security of systems and networks, and support information security with organizational policies) are mapped to the scoped systems with implementation evidence.
6. **Select the assessment instrument.** The entity selects the appropriate ROC, SAQ, or service-provider report. The selection considers merchant level, transaction channel, and whether the entity is a service provider.
7. **Maintain on material change.** Any change in cardholder data flows, infrastructure, or service providers triggers a re-assessment of the scope and the controls.

## Component, connection, and segmentation data

The CDE inventory record must carry the system name, function, owner, location, the type of cardholder data processed, the connection points to other in-scope systems, the segmentation status (in-scope, segmented, or shared), and the validation evidence reference (configuration screenshot, network diagram, firewall rule export). The network diagram carries the CDE boundary, the segmentation control points, the out-of-scope systems with documented justification, and the connection points to third parties.

## Scoping and segmentation evidence

Validation evidence includes a current network diagram, a current data flow diagram for cardholder data, segmentation test results, configuration screenshots for each control, the most recent vulnerability scan and penetration test results, audit log samples showing required events are captured, the policies and procedures documented for each principal requirement, and the quarterly attestation of compliance with the assigned SAQ or ROC. Validation is performed by a Qualified Security Assessor (QSA) for ROC engagements or by the entity itself for SAQ engagements, with the resulting documentation archived.

## Scope escape remediation

- **Incomplete segmentation test.** A segmentation control was in place but the test that demonstrates its effectiveness was not conducted within the past year. A new segmentation test is performed with documented methodology, results, and remediation; the next periodic test is added to the compliance calendar.
- **Out-of-scope system connected without segmentation.** A system not handling cardholder data was placed on the same network segment as the CDE without segmentation. The system is either moved out of scope via proper segmentation or included in the CDE inventory; either path requires a documented control change.
- **Vulnerability scan with critical findings.** The quarterly scan returned a critical vulnerability that had not been remediated within the required timeframe. The finding is added to the compliance tracker, remediated, rescanned, and documented.
- **Service provider not listed.** A service provider that can affect the security of the CDE was not listed in the inventory. The service provider is added, a written agreement is reviewed for compliance with PCI DSS requirement 12.8, and monitoring is established.
- **Tested version drift.** A control that passed in the prior period was updated, and the new version has not been re-tested. The control is re-tested in the current period, and the change-management policy is updated to require a re-test after any material change.

## Assessment and applicability limits

PCI DSS obligations arise through payment-brand and acquiring relationships and do not replace law, contract terms, or brand programs. Validation status does not guarantee security. Entities must confirm the current standard version, transition dates, assessment instrument, and acquirer instructions.

## Canonical sources

- **Primary authority 1:** PCI Security Standards Council, *PCI DSS v4.0 — Document Library* — https://www.pcisecuritystandards.org/document_library
- **Primary authority 2:** PCI Security Standards Council, *Information Supplement: Guidance for PCI DSS Scoping and Network Segmentation* — https://www.pcisecuritystandards.org/documents/Information_Supplement_-_Guidance_for_PCI_DSS_Scoping_and_Network_Segmentation.pdf
