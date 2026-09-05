# Detection Engineering Playbook

## Purpose

Stand up and operate a Detection Engineering function: develop detection rules from threat hypotheses, validate against historical data, deploy to production SIEM, and continuously tune for false positives. The playbook aligns with NIST CSF 2.0 Detect Function, MITRE ATT&CK, and the Detection-as-Code practice.

## Audience

Detection engineers, SOC analysts, threat intelligence analysts, security architect.

## Pre-conditions

1. The reference cards are current: `SIEM_ARCHITECTURE_GOVERNANCE.md`, `RAVENSWORN_INDICATORS_GOVERNANCE.md`, `SOAR_AUTOMATION_GOVERNANCE.md`.
2. The SIEM is wired (per `SIEM_ARCHITECTURE_GOVERNANCE.md`).
3. ATT&CK coverage map is current.
4. Detection-as-Code repository exists.
5. The CI/CD pipeline is wired (per `SOAR_AUTOMATION_GOVERNANCE.md`).

## Procedure

### 1. Threat hypothesis

1. Identify a threat hypothesis:
   - From threat intel (STIX 2.1 indicator / attack-pattern).
   - From ATT&CK technique (e.g., `T1059.001` PowerShell).
   - From incident post-mortem (per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`).
   - From vendor advisory (CVE).
2. Document the hypothesis: attacker, motivation, technique, data source.

### 2. Data source mapping

1. Map the hypothesis to a data source:
   - Process creation: `4688` (Windows), `auditd` (Linux).
   - Network connection: `5156` (Windows firewall), `sysmon` event 3, `auditd` `NETFILTER_PKT`.
   - File creation: `4663` (Windows), `inotify` (Linux).
   - DNS query: `5156` (Windows), `dnsmasq` log, `BIND` query log.
   - Authentication: `4624`, `4625` (Windows), `auth.log` (Linux).
   - Registry: `4657` (Windows).
2. Confirm the data source is indexed in the SIEM.

### 3. Rule development

1. Develop the Sigma rule.
2. Use the schema:
   ```yaml
   title: <name>
   id: <uuid>
   status: experimental
   description: <description>
   author: <name>
   date: <YYYY-MM-DD>
   modified: <YYYY-MM-DD>
   tags:
     - attack.<tactic>
     - attack.t<id>
   logsource:
     category: <category>
     product: <product>
   detection:
     selection:
       <field>: <value>
     filter:
       <field>: <value>
     condition: selection and not filter
   falsepositives:
     - <reason>
   level: <level>
   ```
3. Translate the Sigma rule to the SIEM vendor's query language (SPL, KQL, etc.).
4. Document the rule in the DaC repository.

### 4. Validation

1. Validate the rule against historical data:
   - True positive rate.
   - False positive rate.
   - Performance (rule execution time).
2. Test against a sandbox with simulated attack behavior.
3. Validate the rule fires correctly under simulated conditions.

### 5. Tuning

1. Adjust the rule to reduce false positives.
2. Add filter conditions to exclude known-good behavior.
3. Document the tuning rationale.

### 6. Deployment

1. Open a PR with the rule.
2. CI / CD validates and tests.
3. Reviewer approves.
4. Deploy to production SIEM.
5. Monitor for false positives.

### 7. Maintenance

1. Quarterly review of all rules.
2. Deprecate rules that are no longer relevant.
3. Update rules when the underlying data source schema changes.
4. Update rules when the underlying attacker TTP changes.

### 8. ATT&CK coverage

1. Maintain the ATT&CK coverage map.
2. Identify gaps (techniques without rules).
3. Develop rules to close gaps.
4. Update the coverage map.

## Rollback

Rollback decisions:

- False positive rate > 5% in production → investigate; rollback if not actionable.
- True positive rate = 0 over 30 days → re-evaluate.
- Performance: rule execution > 1 second → optimize.

Rollback procedure:

1. Disable the rule in production SIEM.
2. Open a PR to revert the rule.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` if the rule misfired in a way that caused harm.

## References

- `SIEM_ARCHITECTURE_GOVERNANCE.md`
- `RAVENSWORN_INDICATORS_GOVERNANCE.md`
- `SOAR_AUTOMATION_GOVERNANCE.md`
- `NIST_CSF_2_2024_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- Sigma rules: `https://github.com/SigmaHQ/sigma`
- MITRE ATT&CK: `https://attack.mitre.org/`
- Elastic Detection Rules: `https://github.com/elastic/detection-rules`
- Splunk Security Content: `https://github.com/splunk/security_content`
