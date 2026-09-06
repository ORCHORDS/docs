# NIST SP 800-82 Rev. 3 ICS/OT Cybersecurity Governance

## Purpose

NIST Special Publication 800-82 Revision 3 (September 2023) provides guidance on securing Industrial Control Systems (ICS) and Operational Technology (OT). Governance ensures the ORCHORDS sites that host ICS/OT assets apply a documented OT cybersecurity program that is compatible with — but distinct from — the IT cybersecurity program, with explicit risk-tolerance lines, network segmentation, patch posture, and incident handling.

## Current context and source status

SP 800-82 Rev. 3 supersedes Rev. 2 and aligns with NIST Cybersecurity Framework 2.0 and SP 800-53 Rev. 5 control overlays. The revision introduces a dedicated OT overlay and treats safety, availability, and operational continuity as primary risks alongside cybersecurity. Treat the revision as the canonical reference for OT cybersecurity architecture and lifecycle.

## Governance workflow and controls

### 1. OT/ICS scope and asset inventory

- Maintain a register of every ICS/OT asset including PLC, RTU, SCADA server, HMI, engineering workstation, and historian.
- Map assets to safety instrumented systems and to physical processes; record the safety integrity level (SIL) and any hazardous-process relationship.
- Maintain an OT network topology diagram under change control; re-baseline on every architecture change.

### 2. Risk management and safety interaction

- Treat OT cybersecurity risk alongside process-safety risk; integrate with the site process hazard analysis (PHA) and HAZOP cycles.
- Apply an OT-specific overlay of NIST CSF 2.0 GOVERN, IDENTIFY, PROTECT, DETECT, RESPOND, RECOVER functions.
- Document risk acceptance for any compensating control; review risk acceptance at least annually.

### 3. Network segmentation and architecture

- Implement a defense-in-depth architecture with explicit zones and conduits (IEC 62443 terminology is acceptable as the implementation language).
- Segregate OT from IT with a unidirectional gateway or a documented industrial DMZ; never connect OT directly to the IT network.
- Use OT-aware firewalls and intrusion detection; place monitoring taps that do not perturb the OT network.

### 4. Identity, access, and remote access

- Apply least privilege to every ICS account; remove or disable vendor default accounts.
- Enforce multi-factor authentication for every remote access session to OT, with brokered jump-host architecture.
- Use managed temporary credentials; never share long-lived credentials with vendors.

### 5. Patch and vulnerability management

- Apply vendor patches under a documented patch-and-test cycle that does not interrupt operations.
- Maintain a formal risk-acceptance register for any patch that is deferred for safety, availability, or vendor stability reasons.
- Subscribe to vendor and ICS-CERT advisories; triage and act within documented SLAs.

### 6. Detection and response

- Deploy OT-aware continuous monitoring with passive sensors and anomaly detection tuned to the OT baseline.
- Maintain an OT-specific incident response plan that accounts for safety implications and for the coordination with IT, engineering, and operations.
- Rehearse OT incident scenarios at least annually, including loss-of-view, loss-of-control, and ransomware.

### 7. Lifecycle, decommissioning, and training

- Treat the OT system lifecycle from design through decommission; sanitize media before disposal.
- Train OT personnel on OT-specific threats (e.g., TRITON, Industroyer, Pipedream) and on the OT cybersecurity policy.
- Maintain a process for hand-off between OT and IT during M&A and divestiture events.

## Validation and evidence

- Maintain a current OT asset inventory and topology diagram under change control.
- Record the most recent OT risk assessment and the risk-acceptance register.
- Capture incident-after-action reports for any OT event, including near-miss events.
- Capture evidence of segmentation testing, identity review, patch deferral, and IR rehearsal.

References: NIST SP 800-82 Rev. 3 (September 2023); NIST CSF 2.0; IEC 62443 series; NIST SP 800-53 Rev. 5 OT overlay.
