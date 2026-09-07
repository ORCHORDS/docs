# NIST SP 800-94 (2007) Guide to Intrusion Detection and Prevention Systems Governance

## 1. Scope

This card establishes governance requirements for the design, deployment, tuning, and operation of Intrusion Detection and Prevention Systems (IDPS) in alignment with NIST SP 800-94. It applies to all Network-based IDS (NIDS), Host-based IDS (HIDS), and Intrusion Prevention System (IPS) assets, including Endpoint Detection and Response (EDR) telemetry feeds, within the production estate. The document defines detection methodology selection, sensor placement, baselining, SOAR integration, log retention, and audit evidence obligations.

## 2. Normative references

The following documents are normative for this card:

- NIST SP 800-94, Guide to Intrusion Detection and Prevention Systems (IDPS)
- NIST SP 800-61 Rev. 2, Computer Security Incident Handling Guide
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations
- PCI DSS v4.0, Requirements 10 and 11
- ISO/IEC 27001:2022, Annex A 8.16 Monitoring activities
- HIPAA Security Rule, 45 CFR § 164.312(b)
- FISMA, 44 USC § 3554 and NIST SP 800-53 AU family

## 3. Terms and definitions

NIDS: Network-based IDS. A sensor that inspects packets on a network segment to detect malicious activity against defined policy.

HIDS: Host-based IDS. Software resident on an endpoint that inspects local system calls, file integrity events, and operating-system log records.

IPS: Intrusion Prevention System. A control that, upon detection, blocks or modifies the offending traffic or process state in-line rather than merely alerting.

SOAR: Security Orchestration Automation and Response. A platform that ingests security alerts, enriches them with threat intelligence and asset context, and executes playbooks to contain, remediate, or escalate incidents.

SIEM: Security Information and Event Management. A system that aggregates, normalizes, correlates, and retains security event data across heterogeneous sources.

## 4. Background

NIST SP 800-94 was issued in 2007 to consolidate practitioner guidance on intrusion detection and prevention. The contemporary threat landscape includes ransomware, supply-chain compromise, and cloud-native workloads, which require that the original guidance be complemented by EDR telemetry, behavioural analytics, and SOAR-driven response. This card preserves the SP 800-94 structural model while codifying operational practice for current hybrid environments.

## 5. IDPS detection methodologies

Four methodologies are recognised for IDPS design.

Signature-based detection compares observed events against a curated catalogue of known patterns such as Snort rules or YARA files. The trade-off is a low false-positive rate and predictable performance, offset by blindness to zero-day attacks and dependence on rule freshness.

Anomaly-based detection profiles expected behaviour and flags statistical deviations from that profile. The trade-off is the ability to detect novel attacks, offset by susceptibility to false positives during legitimate change windows and a requirement for sustained baselining.

Stateful protocol analysis tracks protocol state machines to identify deviations from RFC-defined behaviour. The trade-off is high fidelity for protocol misuse in protocols such as DNS, HTTP, and SMB, offset by bounded coverage limited to the protocols implemented.

Hybrid detection combines signature, anomaly, and stateful analysis, frequently augmented by machine-learning scoring. The trade-off is broader detection coverage and reduced blind spots, offset by increased tuning burden and more demanding observability requirements. Hybrid is the recommended default for tier-1 environments. Refer to `NIST_SP_800_94_IDS_GOVERNANCE.md:23` for the methodology selection rationale.

## 6. Network-based IDPS architectures and placement

Network sensors shall be deployed at network ingress and egress points, between trust zones, and adjacent to critical application tiers. Inline IPS sensors shall operate in a documented fail-open or fail-closed mode recorded in the architecture register. Tap or SPAN port sources shall be inventoried in the network diagram. Sensor placement shall be validated by an annual traffic-sampling exercise referenced in the asset register.

## 7. Host-based IDPS, EDR, and runtime detection

HIDS and EDR agents shall be deployed on all servers, workstations, and managed cloud workloads. Detection scope shall include file-integrity monitoring, process ancestry, kernel events, and credential usage. Agents shall report to the central collector over authenticated channels. Coverage gaps shall be reported weekly and tracked via the security risk register.

## 8. Sensor tuning, false-positive reduction, and baselining

Each sensor shall enter a baselining period of not less than 14 days before production alerting is enabled. Rules generating more than five false positives per week shall be reviewed and either suppressed, scoped, or escalated to the detection engineering queue. Anomaly thresholds shall be recalibrated quarterly. All tuning actions shall be recorded with operator identity, justification, and a documented rollback path.

## 9. SOAR (Security Orchestration Automation and Response) integration and alert enrichment

Alerts from NIDS, HIDS, IPS, and EDR shall be forwarded to a SOAR platform via authenticated webhooks or syslog relay. Enrichment playbooks shall attach asset criticality, identity context, geolocation, threat-intelligence reputation, and prior incident history to every ingested alert. Automated response actions may include host isolation, account disablement, firewall block, and forensic snapshot capture; each action shall be gated by an approval policy with a documented exception list. Manual override and a complete audit trail of every playbook execution are mandatory. Cross-reference: `NIST_SP_800_94_IDS_GOVERNANCE.md:43` for the related risk entry R-IDPS-03.

## 10. Log management, retention, and SIEM (Security Information and Event Management) integration

IDPS events shall be forwarded to the SIEM within five minutes of generation. Retention shall meet or exceed the following regulatory minima:

- PCI DSS Requirement 10.7: 12 months online with the most recent three months immediately available.
- HIPAA 45 CFR § 164.312(b): six years of audit record retention.
- FISMA per NIST SP 800-53 AU-11: minimum three years online for federal information systems.

The SIEM tier shall provide hot storage for 30 days, warm storage for six months, and cold archive for the applicable regulatory maximum. Integrity protection in the form of write-once, hash-chained records shall be enforced for all retained logs.

## 11. Compliance evidence (PCI DSS, NIST CSF, ISO 27001)

Evidence packages shall map IDPS controls to PCI DSS Requirement 11.5, NIST CSF DE.CM and RS.AN categories, and ISO 27001 Annex A 8.16. Quarterly evidence shall include the sensor inventory, the tuning change log, alert volume trends, mean time to detect (MTTD), mean time to respond (MTTR), and SOAR playbook execution reports.

## 12. Risk register

| Risk ID | Description | Likelihood | Impact | Treatment |
|---------|-------------|------------|--------|-----------|
| R-IDPS-01 | Signature coverage gap for novel malware | Medium | High | Hybrid detection; threat-intelligence feed |
| R-IDPS-02 | Sensor blind spot from improper tap placement | Medium | High | Quarterly placement audit |
| R-IDPS-03 | SOAR playbook misfire causing service outage | Low | High | Staging gate; dual-approval workflow |
| R-IDPS-04 | Log retention shortfall during external audit | Low | Medium | Automated retention verification |
| R-IDPS-05 | EDR agent tampering by adversary | Medium | High | Tamper protection; kernel-mode agent |

## 13. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.