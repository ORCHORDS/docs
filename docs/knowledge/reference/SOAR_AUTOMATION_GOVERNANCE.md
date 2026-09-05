---
title: SOAR and Detection-as-Code Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-61 Rev. 2 (Computer Security Incident Handling Guide); MITRE ATT&CK; SigmaHQ; SOAR product documentation (Cortex XSOAR, Tines, Splunk SOAR, Microsoft Sentinel SOAR); OCSF schema
---

# SOAR and Detection-as-Code Version Governance

## Scope

This card governs how `orchords-docs` evaluates Security Orchestration, Automation, and Response (SOAR) platforms and the Detection-as-Code (DaC) practice. It is the reference input for any KB card that cites automated response, playbook execution, or detection lifecycle management.

## Why this card exists

SOAR platforms run playbooks that combine orchestration (input), automation (logic), and response (action). Without a DaC approach, detection content drifts: rules are edited in vendor UI, version control is informal, and rule coverage is invisible. A KB card that recommends SOAR without binding to a DaC pipeline produces a SOC that cannot be audited.

## SOAR platform matrix

| Platform | Vendor | DaC support | Notes |
|---|---|---|---|
| Cortex XSOAR | Palo Alto Networks | Marketplace content + REST API | industry-leading |
| Splunk SOAR | Splunk (formerly Phantom) | REST API + Splunkbase content | bundled with Splunk ES |
| Microsoft Sentinel SOAR | Microsoft | Logic Apps + ARM templates | Azure-native |
| Tines | Tines | "Story" export + REST API | modern, low-code |
| n8n | n8n GmbH | Workflow-as-code (JSON) | open-source |
| Shuffle | Shuffle | Workflow-as-code (JSON) | open-source |
| AWS Step Functions + Lambda | AWS | CloudFormation / CDK | custom-built |
| GCP Workflows | GCP | YAML / Terraform | custom-built |

Policy:

- For new SOC builds: Tines or Cortex XSOAR preferred.
- For Azure-native SOCs: Sentinel SOAR.
- For Splunk-native SOCs: Splunk SOAR.
- Open-source: n8n or Shuffle.

## Playbook language

Playbooks are encoded in:

- **JSON** — Tines, Splunk SOAR, n8n.
- **YAML** — Cortex XSOAR (YAML content pack).
- **Python** — Cortex XSOAR (custom integration).
- **PowerShell** — Microsoft Sentinel (Logic Apps custom action).

The KB cards bind the playbook to a specific language and version.

## Detection-as-Code (DaC)

DaC applies software-engineering practices to detection content:

- **Version control**: every rule is in a Git repository.
- **CI / CD**: rules are validated, tested, and deployed automatically.
- **Testing**: rules have unit tests (expected log → expected alert).
- **Review**: rules are reviewed via PR.
- **Coverage tracking**: rules are mapped to ATT&CK techniques.
- **Documentation**: rules have rich metadata (author, dates, MITRE ATT&CK mapping).

### DaC pipeline

```
[Repo: sigma-rules] → [CI: validate + test] → [CD: deploy to SIEM] → [Observability: hits, FPs]
```

Reference implementations:

- **SOCPrime**: `https://socprime.com/`.
- **SigmaHQ**: `https://github.com/SigmaHQ/sigma`.
- **Elastic Detection Rules**: `https://github.com/elastic/detection-rules`.
- **Splunk Security Content**: `https://github.com/splunk/security_content`.

## DaC rule schema

Sigma rules use YAML:

```yaml
title: <Human-readable name>
id: <uuid>
status: stable|test|experimental|deprecated|unsupported
description: <description>
references:
  - <URL>
author: <name>
date: <YYYY-MM-DD>
modified: <YYYY-MM-DD>
tags:
  - attack.<tactic>
  - attack.<technique_id>
logsource:
  category: <process_creation|network_connection|file_event|...>
  product: <windows|linux|macos|...>
detection:
  selection:
    <field>: <value>
  condition: selection
falsepositives:
  - <reason>
level: <informational|low|medium|high|critical>
```

Policy:

- `id` must be a UUID v4.
- `status` must be one of: stable, test, experimental, deprecated, unsupported.
- `tags` must include at least one ATT&CK technique ID.
- `level` must be one of: informational, low, medium, high, critical.

## SOAR response action policy

SOAR actions are gated by:

| Action | Required approval | Audit log | Rollback |
|---|---|---|---|
| Read-only enrichment | none | yes | n/a |
| Notify / page | none | yes | n/a |
| Quarantine email | SOC analyst | yes | yes |
| Disable user account | SOC analyst + manager | yes | yes |
| Isolate host (EDR) | SOC analyst + manager | yes | yes |
| Block IP at edge | SOC analyst + manager | yes | yes |
| Block domain at DNS | SOC analyst + manager | yes | yes |
| Revoke credentials | SOC analyst + manager | yes | yes |
| Delete data | CISO | yes | n/a |
| Modify firewall rules | CISO + platform owner | yes | yes |
| Backup/restore | platform owner | yes | yes |

## Mandatory pre-flight (before adopting a new SOAR component)

1. The SOAR platform is in the supported matrix.
2. Playbooks are encoded in version control.
3. Response actions are gated per the policy table.
4. CI / CD is wired for rules.
5. ATT&CK coverage is documented.
6. Audit logging is wired.

## Cross-reference

| Domain | Card |
|---|---|
| Threat intel | `RAVENSWORN_INDICATORS_GOVERNANCE.md` (CTI / STIX / TAXII) |
| SIEM | `SIEM_ARCHITECTURE_GOVERNANCE.md` |
| Incident response | `ISO_IEC_27035_2016_INCIDENT_GOVERNANCE.md` |
| AI security | `ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md` |

## Sources

- NIST SP 800-61 Rev. 2: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final`
- MITRE ATT&CK: `https://attack.mitre.org/`
- SigmaHQ: `https://github.com/SigmaHQ/sigma`
- OCSF: `https://schema.ocsf.io/`
- Cortex XSOAR: `https://docs.paloaltonetworks.com/cortex/cortex-xsoar`
- Tines: `https://www.tines.com/docs/`
- Splunk SOAR: `https://docs.splunk.com/Documentation/SOAR/current/User/Introduction`
