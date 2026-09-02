# NIST IR 8011 Continuous Monitoring Automation Governance

## Purpose

Govern the application of the NIST IR 8011 series (Automation Support for Security Control Monitoring) so that continuous monitoring is implemented as an automated, data-driven discipline: defined control correlates and metrics collected by automation, analyzed against thresholds, and fed to risk decisions — replacing point-in-time assessment sampling.

## Scope

Applies to the studio's continuous monitoring program for security controls. Covers control correlate identification, metric automation, and monitoring workflow integration. Does not cover the ISCM program strategy itself (NIST SP 800-137 governs that layer) or specific SIEM tooling.

## Workflow

1. Select control correlates: for each monitored control, define the observable data elements (the correlates) that indicate the control's operation — correlates are the bridge between control intent and machine-collected data.
2. Automate collection per the IR 8011 model: metrics defined with data sources, collection frequency, and normalization rules; manual collection is the exception requiring justification.
3. Define analysis thresholds per metric: what values constitute compliant, degraded, and failed states, with the decision each state triggers — a metric without thresholds is telemetry, not monitoring.
4. Integrate with the risk decision workflow: monitoring outputs feed the ongoing authorization decisions (SP 800-37's continuous monitoring step), not a dashboard nobody owns.
5. Manage measurement validity: metrics drift when systems change; periodic validation confirms each metric still measures what it claims.
6. Respond to failed states automatically where possible: automated remediation (revoking a stale account, re-enforcing a configuration) closes the loop within the monitoring cycle.
7. Report at the program layer: aggregated control status by metric over time shows trend, not just snapshot — trend is what authorizing officials need.

## Controls and evidence

- Control correlate definitions per monitored control.
- Metric specifications with data sources, frequency, and normalization.
- Threshold definitions with state-triggered decisions.
- Automated collection execution records.
- Metric validity validation records.
- Program-layer trend reports.

## Validation

- Sample five metrics: confirm each has a defined correlate, automated source, and thresholds with decisions.
- Confirm failed-state responses execute within the defined cycle (automated or ticketed).
- Confirm trend reports reach the risk decision owner on cadence.

## Failure correction

- **Metric without threshold** → define states and decisions or retire the metric; threshold-less collection consumes storage without informing decisions.
- **Collection silently failing** → alert on collection failure itself; a monitoring metric that stops reporting is a monitoring system failure, not quiet compliance.
- **Metric no longer measures the control** → revalidate the correlate against the current system and correct source mappings.

## Limitations

- IR 8011 addresses automation of monitoring; the program strategy — what to monitor and why — comes from SP 800-137.
- Automation coverage is incomplete for judgment-heavy controls; those remain assessed periodically rather than continuously.
- Metric sprawl is the failure mode: every metric adds maintenance; monitor the controls that matter to risk decisions.

## Scope note

This article is part of the security leaf. Cross-reference: `MITRE_ATTACK_ENTERPRISE_DETECTION_AND_ENGINEERING_GOVERNANCE.md`, `ITIL_4_MONITORING_AND_EVENT_MANAGEMENT_PRACTICE_GOVERNANCE.md` (operations leaf), and `NIST_SP_800_137_INFORMATION_SECURITY_CONTINUOUS_MONITORING_GOVERNANCE.md`.

## Canonical sources

- NIST IR 8011 Vol 1 — Automation Support for Security Control Monitoring: https://csrc.nist.gov/pubs/ir/8011/vol-1/final
- NIST IR 8011 Vol 2 — Identification and Authentication: https://csrc.nist.gov/pubs/ir/8011/vol-2/1/final
- NIST SP 800-137 — Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations: https://csrc.nist.gov/publications/detail/sp/800-137/final
- NIST SP 800-137A — Managing ISCM Programs (draft line): https://csrc.nist.gov/pubs/sp/800/137a/ipd
- NIST SP 800-37 Rev 2 — Risk Management Framework: https://csrc.nist.gov/pubs/sp/800-37/rev-2/final
