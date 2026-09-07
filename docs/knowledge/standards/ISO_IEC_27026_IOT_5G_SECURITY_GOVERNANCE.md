# ISO/IEC 27026 — IoT and 5G Network Security Guideline Governance

## 1. Scope

This card governs how `orchords-docs` evaluates security guidance for Internet of Things
(IoT) devices and 5G network equipment against ISO/IEC 27026 (current edition at time of
adoption). It is the reference input for any KB card that touches consumer or industrial
IoT endpoints, private 5G campuses, public 5G mobile networks, network slicing,
edge-cloud anchors, or the device identity and key-management functions that bind them.
It binds the knowledge base to a published guideline that supplements ISO/IEC 27001:2022
and ISO/IEC 27002:2022 with IoT- and 5G-specific provisions and that cross-references the
ETSI EN 303 645 consumer baseline.

## 2. Normative references

The following documents are referred to in the text in such a way that some or all of their
content constitutes requirements of this card. For dated references, only the edition cited
applies. For undated references, the latest edition of the referenced document (including
any amendments) applies.

- ISO/IEC 27026, Security techniques — Guidelines for IoT and 5G network security
  (current edition at time of adoption).
- ISO/IEC 27001:2022, Information security, cybersecurity and privacy protection —
  Information security management systems — Requirements.
- ISO/IEC 27002:2022, Information security, cybersecurity and privacy protection — Information
  security controls.
- ETSI EN 303 645 V2.1.1, Cyber Security for Consumer Internet of Things: Baseline
  Requirements — the consumer IoT baseline that ISO/IEC 27026 cross-references.
- ETSI TS 103 701, Implementation of the EN 303 645 provisions — implementation detail
  used by ISO/IEC 27026 for the consumer-IoT subset.

## 3. Terms and definitions

For the purposes of this card, the following terms apply.

- 3.1 IoT endpoint — device with sensing, actuating, or networking capability that
  communicates with a controller, gateway, or cloud service over an IP or non-IP bearer.
- 3.2 5G network element — function in a 5G system as defined by 3GPP TS 23.501, including
  AMF, SMF, UPF, UDM, AUSF, NRF, PCF, and the corresponding management functions.
- 3.3 network slice — logical 5G network that composes network functions with a specific
  set of isolation, throughput, latency, and security characteristics.
- 3.4 subscriber identity — primary authentication credential (SUPI/SUCI pair) and the
  derived session keys that authenticate a user to a 5G core.

## 4. IoT and 5G threat landscape

The KB records the threat landscape that ISO/IEC 27026 guides the operator against.
Threats are enumerated topically so that each reference card can cite the most relevant
subset.

- 4.1 Endpoint compromise — firmware tampering, default credentials, exposed debug
  interfaces, and physical attack against field-installed IoT devices.
- 4.2 Radio-path attacks — IMSI catchers, jamming, downgrade, signalling spoofing, and
  exploit of SS7 / Diameter interconnects where they remain reachable from a 5G core.
- 4.3 Core-network compromise — credential theft against a 5G management plane,
  privilege escalation across slice functions, and exposure through service-based
  interfaces.
- 4.4 Privacy erosion — tracking via persistent identifiers, replay of authentication
  tokens, and leakage of subscriber identity on radio and signalling paths.
- 4.5 Supply-chain compromise — tampered firmware, vulnerable baseband stacks, and
  counterfeit cellular modules.

## 5. Security controls catalogue for IoT/5G

The catalogue imports from ISO/IEC 27002:2022 and adds IoT/5G overlays.

- 5.1 Asset management — registration of every IoT endpoint and every SIM / IMSI / SUPI,
  including a documented decommissioning path.
- 5.2 Identity and authentication — mutual authentication at the device layer, no
  universal default credentials (cross-reference ETSI EN 303 645 provision 1), and
  separation of slice credentials from slice traffic.
- 5.3 Cryptography — hardware-backed key storage on the endpoint, mutual TLS or equivalent
  on every southbound and northbound path, and refresh of subscription keys on exposure.
- 5.4 Software and firmware integrity — signed updates, anti-rollback anchors, and a
  documented acceptance procedure for third-party firmware.
- 5.5 Network segmentation — slice isolation for 5G, separate routing domains for IoT
  control and IoT data, and explicit filtering at the IoT-to-SAS boundary.
- 5.6 Logging and detection — endpoint telemetry, radio-path anomaly feeds, and 5G core
  signalling logs into the operator SIEM.

## 6. Privacy and identity controls

The privacy and identity layer in ISO/IEC 27026 supplements ISO/IEC 27001:2022 Annex A
controls on identity, cryptography, and compliance. The KB enforces the following baseline.

- 6.1 Subscriber-identifier handling — use of SUCI (not SUPI) on the radio path; the SUPI
  is unmasked only inside the operator's secure perimeter.
- 6.2 Data minimization — IoT endpoints send only what the receiving service contract
  declares; non-essential telemetry is dropped at the gateway.
- 6.3 End-user transparency — privacy notice explicit on identifier use, slice assignment,
  and any feature that requires an additional category of processing.
- 6.4 Subject rights — procedures for identifier rotation, identifier reassignment, and
  device decommissioning that bind together the telecom identity, the IoT application,
  and the privacy rights response.

## 7. Implementation guidance

Implementation guidance is the layer the KB adopts across reference architecture and
playbook cards.

- 7.1 Adoption pathway — first map ISO/IEC 27026 controls onto the existing ISMS
  Statement of Applicability, then onto the IoT and 5G deployment evidence; gaps are
  handled under a dated change ticket.
- 7.2 Consumer-IoT hand-off — any consumer-grade endpoint in a KB reference must cite the
  ETSI EN 303 645 provisions it satisfies; gaps are flagged against ISO/IEC 27026 as
  well.
- 7.3 5G deployment hand-off — any 5G reference card must document the slice model, the
  identity model (SUPI/SUCI), and the audit-log surface that the operator exposes to the
  customer.
- 7.4 Review cadence — the KB default review cadence for this card is 180 days.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
