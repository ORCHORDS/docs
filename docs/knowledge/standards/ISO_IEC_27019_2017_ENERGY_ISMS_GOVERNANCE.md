# ISO/IEC 27019:2017 — Information Security Controls for the Energy Utility Industry Governance

## 1. Scope

This card governs how `orchords-docs` evaluates information security controls applied to
energy utility organizations — electricity, gas, oil, water, and district-heating
operators — against ISO/IEC 27019:2017. It is the reference input for any KB card that
touches process control systems, SCADA platforms, smart-grid components, advanced metering
infrastructure, or the corporate networks that operate alongside them. It binds the
knowledge base to a sector profile of ISO/IEC 27001:2022 plus ISO/IEC 27002:2022 controls,
as amended by ISO/IEC 27019:2017.

## 2. Normative references

The following documents are referred to in the text in such a way that some or all of their
content constitutes requirements of this card. For dated references, only the edition cited
applies. For undated references, the latest edition applies.

- ISO/IEC 27019:2017, Information technology — Security techniques — Information security
  controls for the energy utility industry.
- ISO/IEC 27001:2022, Information security, cybersecurity and privacy protection —
  Information security management systems — Requirements.
- ISO/IEC 27002:2022, Information security, cybersecurity and privacy protection — Information
  security controls.
- IEC 62443 (series), Industrial communication networks — Network and system security,
  in particular IEC 62443-3-3 and IEC 62443-4-2 for security requirements and system
  security capability levels.

## 3. Terms and definitions

For the purposes of this card, the following terms apply.

- 3.1 process control system — system that continuously monitors and controls the physical
  processes of an energy utility, including SCADA, distributed control systems, and
  programmable logic controllers.
- 3.2 industrial automation and control system (IACS) — collection of personnel, hardware,
  and software that influences the safe, secure, and reliable operation of an industrial
  process, as defined in the IEC 62443 series.
- 3.3 energy utility sector profile — the set of ISO/IEC 27002:2022 controls plus the
  energy-specific refinements published in ISO/IEC 27019:2017 that an organization selects
  in its Statement of Applicability.
- 3.4 safety integrity level (SIL) — IEC 61511-defined reliability target for safety
  instrumented functions; a SIL rating constrains the security controls that may be applied
  without harming safety performance.

## 4. Energy-sector ISMS profile

ISO/IEC 27019:2017 does not introduce new ISO/IEC 27002:2022 themes; it re-states each
selected control with energy-utility implementation guidance. The KB uses the following
profile structure.

- A.5 Organizational — alignment with national energy regulators and TSOs/DSOs, incident
  reporting timelines, and supply-chain treatment for IACS vendors.
- A.6 People — vetting of staff with privileged access to control rooms and to remote
  remediation paths for IACS assets.
- A.7 Physical — enhanced protection for substations, control rooms, unattended cabinets,
  and metering concentration points.
- A.8 Technological — identity, segmentation, logging, and patching guidance that respects
  the availability and integrity constraints of continuous-process plants.

## 5. Process control and SCADA/ICS controls

Where a control touches IACS equipment, the KB couples ISO/IEC 27019:2017 with the IEC 62443
family rather than treating them as competing references.

- 5.1 Account management — IEC 62443-3-3 system requirements (SR 1.1, SR 1.7) define the
  base; ISO/IEC 27019:2017 adds shared-account prohibitions and break-glass procedures for
  control rooms.
- 5.2 Segmentation — IEC 62443-4-2 system security capability levels and IEC 62443-3-3
  zones-and-conduits guidance define the target architecture; ISO/IEC 27019:2017 adds the
  practical South-to-North interface rules for exchanging telemetry with corporate IT.
- 5.3 Patching — IEC 62443-2-4 service-provider requirements fix the obligation towards
  vendors; ISO/IEC 27019:2017 sets the operator's risk-based patch deferral conditions that
  are auditable in the ISMS.
- 5.4 Telemetry and logging — IEC 62443-3-3 SR 6.1 and SR 6.2 fix what is recorded; ISO/IEC
  27019:2017 maps the recordings onto operator log retention regimes.

## 6. Sector-specific threat sources

The KB records threat sources relevant to an energy utility when authoring or reviewing
reference architecture and incident response cards.

- 6.1 Nation-state actors targeting generation, transmission, or distribution assets to
  pre-position for crisis leverage.
- 6.2 Criminal actors deploying ransomware against operations technology that shares a
  Windows stack with enterprise IT.
- 6.3 Insider actors — employees, contractors, and field engineers with authorized physical
  or remote access.
- 6.4 Supply-chain actors — IACS vendors, third-party maintenance providers, and remote
  engineering tunnels.
- 6.5 Natural and physical hazards that combine with cyber events (wildfire, flood,
  substation damage).

## 7. Compliance and certification tie-in

ISO/IEC 27019:2017 is auditable as a sector profile within an ISO/IEC 27001:2022 ISMS, and
its IACS coupling is auditable against IEC 62443 conformance. The KB requires the
following artefacts.

- 7.1 A Statement of Applicability that lists each ISO/IEC 27019:2017 control selected and
  references the IEC 62443 control(s) that the implementation relies upon.
- 7.2 A zoning-and-conduits diagram covering the entire process control estate, version
  dated and reviewed on every architecture change.
- 7.3 Certification scope that is co-extensive with the ISMS scope; mismatched scopes are
  rejected by the KB.
- 7.4 Review cadence — the KB default review cadence for this card is 180 days.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
