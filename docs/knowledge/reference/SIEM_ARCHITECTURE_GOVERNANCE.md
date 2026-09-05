---
title: SIEM Architecture and Detection Engineering Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: MITRE ATT&CK (https://attack.mitre.org/); NIST SP 800-92 (Guide to Computer Security Log Management, 2006); Splunk / Elastic / Sumo Logic / Microsoft Sentinel public documentation; OCSF (Open Cybersecurity Schema Framework); ECS (Elastic Common Schema)
---

# SIEM Architecture and Detection Engineering Version Governance

## Scope

This card governs how `orchords-docs` evaluates Security Information and Event Management (SIEM) architectures and detection engineering. It is the reference input for any KB card that cites log aggregation, security analytics, or detection content.

## Why this card exists

A SIEM is a complex stack: collection layer, normalization layer, indexing layer, search layer, detection layer (correlation rules, behavioral analytics, ML-based detection), and presentation layer. Vendor ecosystems (Splunk SPL, Elastic EQL/KQL, Sentinel KQL, Sumo Logic) diverge on schema, query language, and detection format. A KB card that recommends "SIEM" without binding to schema (ECS, OCSF) and detection language produces a SOC architecture that cannot be reasoned about.

## SIEM reference architecture

| Layer | Component | Examples |
|---|---|---|
| Collection | Log shippers | Fluent Bit, Filebeat, Vector, Splunk UF, Winlogbeat |
| Normalization | Schema mapping | ECS, OCSF, CEF, LEEF |
| Ingestion | Ingestion APIs | Splunk HEC, Elastic Ingest, Sentinel Connector |
| Indexing | Storage | OpenSearch, Elasticsearch, Splunk index, BigQuery, Athena |
| Search | Query language | SPL, KQL, EQL, Lucene, SQL, Sumo Logic |
| Detection | Correlation rules | Sigma rules, vendor-specific |
| Analytics | Behavioral analytics | vendor ML / UEBA |
| Presentation | Dashboards | vendor dashboards, Grafana |
| Response | SOAR integration | Phantom, Cortex XSOAR, Tines, n8n |

References: NIST SP 800-92 (Log Management).

## Log schema standards

| Schema | Owner | Notes |
|---|---|---|
| ECS (Elastic Common Schema) | Elastic | widely adopted for Elastic stack |
| OCSF (Open Cybersecurity Schema Framework) | OASIS (under standardization, 2024) | vendor-neutral |
| CEF (Common Event Format) | ArcSight / Micro Focus | legacy |
| LEEF (Log Event Extended Format) | IBM QRadar | legacy |
| CLF (Common Log Format) | W3C | HTTP access logs |

Policy:

- New deployments use OCSF where supported; ECS is acceptable for Elastic-first deployments.
- Vendor-proprietary schema is acceptable when the data class is single-vendor.

References: `https://schema.ocsf.io/`, `https://www.elastic.co/guide/en/ecs/current/index.html`.

## Sigma rules

Sigma is the vendor-neutral detection rule format. Sigma rules translate to vendor-specific queries (Splunk SPL, Elastic KQL, Sentinel KQL) at runtime:

```
title: Suspicious PowerShell Activity
status: stable
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    Image|endswith:
      - 'powershell.exe'
      - 'pwsh.exe'
    CommandLine|contains:
      - 'Invoke-WebRequest'
      - 'DownloadString'
      - 'Net.WebClient'
  condition: selection
level: high
tags:
  - attack.execution
  - attack.t1059.001
```

References: `https://github.com/SigmaHQ/sigma`.

## Detection engineering lifecycle

1. **Threat hypothesis**: based on ATT&CK technique or threat-intel report.
2. **Data source**: identify the log source (e.g., process creation event).
3. **Rule development**: write the Sigma rule, validate against historical data.
4. **Testing**: false-positive analysis, true-positive validation.
5. **Tuning**: refine to reduce false positives.
6. **Deployment**: deploy to production SIEM.
7. **Maintenance**: periodic review, deprecation.

## MITRE ATT&CK alignment

Every detection rule maps to at least one ATT&CK technique:

- Tactic (e.g., Execution, TA0002).
- Technique (e.g., T1059 Command and Scripting Interpreter).
- Sub-technique (e.g., T1059.001 PowerShell).

The KB detection card binds the rule to the technique and to the threat intel feed (STIX 2.1).

## SOAR integration

Security Orchestration, Automation, and Response (SOAR) platforms automate response:

- Phantom / Cortex XSOAR (Palo Alto Networks).
- Tines (Tines).
- n8n (open source).
- Splunk SOAR (formerly Phantom).
- Microsoft Sentinel SOAR.

Integration patterns:

- Trigger on detection rule.
- Enrich with threat intel (STIX feed).
- Containment: isolate host, disable account, block IP.
- Notification: page on-call, ticket creation.

## Mandatory pre-flight (before adopting a new SIEM component)

1. The collection layer supports the project's log sources.
2. The normalization layer maps to ECS, OCSF, or a documented schema.
3. The detection language is supported.
4. The schema is documented in a KB reference card.
5. SOAR integration is wired.

## Observability

- Log volume per source (gauge).
- Ingestion latency p99 (histogram).
- Indexing latency p99 (histogram).
- Detection rule hit rate (counter, per rule).
- False-positive rate (per rule).
- True-positive rate (per rule).
- Mean-time-to-detect (MTTD).
- Mean-time-to-respond (MTTR).

## Sources

- NIST SP 800-92 (Log Management): `https://csrc.nist.gov/publications/detail/sp/800-92/final`
- MITRE ATT&CK: `https://attack.mitre.org/`
- Sigma rules: `https://github.com/SigmaHQ/sigma`
- OCSF: `https://schema.ocsf.io/`
- ECS: `https://www.elastic.co/guide/en/ecs/current/index.html`
- Splunk SPL: `https://docs.splunk.com/Documentation/Splunk/latest/Search/WhatsInThisManual`
- Elastic KQL / EQL: `https://www.elastic.co/guide/en/elasticsearch/reference/current/eql.html`
