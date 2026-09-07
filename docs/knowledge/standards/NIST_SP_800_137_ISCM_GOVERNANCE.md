# NIST SP 800-137 (2020) Information Security Continuous Monitoring Governance

## 1. Scope

This card establishes the governance requirements for an Information Security Continuous Monitoring (ISCM) program derived from NIST SP 800-137. It applies to federal information systems and any organization adopting FISMA, FedRAMP, or RMF-aligned controls. The card defines roles, processes, telemetry pipelines, and review cadences needed to maintain ongoing situational awareness of security posture, and it aligns monitoring outputs with the DHS CISA Continuous Diagnostics and Mitigation (CDM) program capabilities. The scope covers technical, operational, and managerial activities from asset discovery through response and review, and it governs the integration of telemetry with Security Information and Event Management (SIEM) and Security Orchestration, Automation, and Response (SOAR) platforms.

## 2. Normative references

The following references are normative for this card:

- NIST SP 800-137, Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations.
- NIST SP 800-53, Security and Privacy Controls for Information Systems and Organizations.
- NIST SP 800-37, Risk Management Framework for Information Systems and Organizations (RMF).
- NIST SP 800-61, Computer Security Incident Handling Guide.
- NIST SP 800-30, Guide for Conducting Risk Assessments.
- DHS CISA Continuous Diagnostics and Mitigation (CDM) Program capability reference.
- OMB A-130, Managing Information as a Strategic Resource.
- Federal Information Security Modernization Act (FISMA) of 2014.
- FedRAMP Continuous Monitoring Strategy Guide.

## 3. Terms and definitions

- **ISCM**: Information Security Continuous Monitoring. The maintenance of ongoing situational awareness of information security, vulnerabilities, and threats to support organizational risk management decisions.
- **CDM**: Continuous Diagnostics and Mitigation. The DHS CISA program that provides federal departments and agencies with capabilities and tools to identify, prioritize, and mitigate cybersecurity risks.
- **SIEM**: Security Information and Event Management. The centralized collection, normalization, correlation, and retention of security telemetry.
- **SOAR**: Security Orchestration, Automation, and Response. The orchestration layer that automates triage, enrichment, and response actions across integrated security tools.
- **RMF**: Risk Management Framework. The seven-step process defined in NIST SP 800-37 for categorizing, selecting, implementing, assessing, authorizing, and monitoring controls.

## 4. Background

Continuous monitoring replaces point-in-time assessments with persistent visibility. NIST SP 800-137 operationalizes the "monitor" step of the RMF and supplies the evidence required by FISMA annual reporting and FedRAMP continuous monitoring deliverables. The card links the CDM capability areas (HWAM, SWAM, CSVM, IDAM, BEHAVE, GRC) to NIST control families, ensuring that operational telemetry maps to authoritative control baselines.

## 5. ISCM program structure (NIST six-step process)

The ISCM program shall implement the NIST six-step process as a closed loop:

1. **Define** the ISCM strategy, including the assets, controls, metrics, frequency, and threat model. Document the strategy in the system security plan and align it to the RMF security category.
2. **Establish** the metrics, thresholds, data sources, ownership, and tool selection. Define data schemas for assets, configurations, vulnerabilities, events, and behavioral baselines.
3. **Implement** the controls and the data collection mechanisms across endpoints, networks, identity systems, and cloud workloads. Deploy sensors and agents consistent with CDM HWAM and SWAM.
4. **Analyze and report** collected data against defined metrics and thresholds. Produce dashboards, risk indicators, and FISMA-aligned monthly and quarterly reports.
5. **Respond** to findings by initiating triage, remediation, mitigation, or acceptance actions through documented response playbooks.
6. **Review and update** the strategy, metrics, and thresholds based on findings, threat evolution, and changes to the system or environment.

## 6. Asset, configuration, and vulnerability monitoring

The program shall maintain an authoritative inventory of hardware (HWAM), software (SWAM), and cloud resources. Configuration baselines shall be derived from CIS benchmarks or DISA STIGs and continuously evaluated against live state using SCAP-validated tools. Vulnerability data from authenticated scanners, software composition analysis, and cloud posture management shall be normalized to CVE identifiers and correlated against the asset inventory. Critical findings shall be enriched with asset criticality, exposure, and exploit intelligence, and shall feed the SIEM analytics tier.

## 7. Threat and behavioral monitoring

The program shall collect authentication, network, endpoint, and cloud control-plane telemetry to support the CDM BEHAVE capability area. Behavioral analytics shall detect anomalies such as impossible travel, privilege escalation, lateral movement, and data exfiltration. Threat intelligence shall be ingested from CISA AIS, ISACs, and vendor feeds and correlated with internal telemetry. Indicators of compromise shall be expressed in STIX and shared via TAXII where applicable.

## 8. Control assessment automation

Control assessments shall be automated for all controls that can be tested through technical means. Assessment results shall be exported in OSCAL and bound to the system security plan. Manual assessment shall be reserved for operational, managerial, and physical controls. Failed assessments shall trigger tickets in the governance, risk, and compliance (GRC) platform.

## 9. CDM program alignment (DHS CISA CDM)

The ISCM strategy shall align with the CISA CDM capability areas: hardware asset management, software asset management, configuration settings management, vulnerability management, identity and access management, data protection, and behavioral monitoring. Agency reporting shall map CDM metrics to NIST SP 800-137 metrics and to the FISMA CIO metrics. Evidence packages shall be retained for a minimum of three years.

## 10. SIEM/SOAR (Security Orchestration Automation and Response) integration and data pipeline

Telemetry sources (endpoints, identity providers, network sensors, cloud APIs, vulnerability scanners, and CDM tools) shall forward events to a centralized SIEM. The SIEM shall normalize, enrich, and correlate events and shall expose case records to the SOAR platform. The SOAR platform shall execute enrichment lookups, user/asset context joins, and documented response playbooks. Data shall flow as follows: source sensors export to a collection tier, the collection tier forwards to the SIEM analytics tier, the SIEM raises cases on threshold or correlation match, the SOAR tier enriches cases and dispatches automated or human-approved actions, and outcomes are written back to the GRC system and to the ISCM dashboard. Audit logs shall be retained for the period required by NARA and by FedRAMP.

## 11. Compliance evidence (FISMA, FedRAMP, RMF)

The program shall produce evidence sufficient to satisfy FISMA annual reporting, FedRAMP continuous monitoring deliverables, and the "monitor" step of the RMF. Evidence shall include control assessment results, POA&M entries, incident response records, change tickets, and vulnerability trend data. All evidence shall be linked to the relevant control identifier and shall be exportable in OSCAL.

## 12. Risk register

Findings exceeding defined risk thresholds shall be entered into the organizational risk register as POA&M items, with inherent risk, residual risk, owner, due date, and compensating controls. The risk register shall be reviewed at each ISCM reporting cycle and shall inform the authorizing official's ongoing authorization decision.

## 13. Review cadence

The ISCM strategy shall be reviewed quarterly, while the metrics, thresholds, and tooling inventory shall be reviewed at least semi-annually. Operational dashboards shall be reviewed daily by the SOC, weekly by the ISSO, and monthly by senior management.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
