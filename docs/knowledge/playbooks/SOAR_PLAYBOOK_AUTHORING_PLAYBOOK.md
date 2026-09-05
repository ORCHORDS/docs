# SOAR Playbook Authoring Playbook

## Purpose

Author, validate, and deploy SOAR (Security Orchestration, Automation, and Response) playbooks for a SOC. The playbook covers YAML/JSON authoring, validation against the SOAR platform's schema, version control, testing, and operational monitoring.

## Audience

SOAR engineers, SOC engineers, detection engineers.

## Pre-conditions

1. The reference cards are current: `SOAR_AUTOMATION_GOVERNANCE.md`, `SIEM_ARCHITECTURE_GOVERNANCE.md`, `RAVENSWORN_INDICATORS_GOVERNANCE.md`.
2. SOAR platform is wired (per `SOAR_AUTOMATION_GOVERNANCE.md`).
3. SOAR schema validation tool is installed.
4. The playbook repository exists in version control.

## Procedure

### 1. Identify the use case

1. Trigger event: SIEM alert, EDR alert, threat intel indicator, manual trigger.
2. Response actions: notify, enrich, contain, eradicate, recover, document.
3. Acceptance criteria: ≤ 5 minutes to first action, ≤ 30 minutes to containment.

### 2. Author the playbook

1. Choose the format:
   - YAML (Cortex XSOAR).
   - JSON (Tines, Splunk SOAR, n8n).
2. Use the SOAR platform's schema.
3. Define inputs (alert payload, IOC, asset context).
4. Define outputs (ticket creation, containment action, notification).
5. Define steps:
   - Trigger.
   - Enrichment (look up context).
   - Decision (manual approval, auto-approve).
   - Action (contain, notify).
   - Closure (ticket closed, audit log written).
6. Validate against the SOAR schema.

### 3. Test the playbook

1. Validate against a sandbox.
2. Test with synthetic alert data.
3. Validate: each step completes, errors are handled, audit log is written.
4. Validate: response actions are gated per the SOAR governance policy table.
5. Validate: rollback actions exist for reversible actions.

### 4. Review and approve

1. Open a PR with the playbook.
2. CI / CD validates the schema.
3. Reviewer approves.
4. Merge to main.

### 5. Deploy

1. Deploy to the SOAR staging environment.
2. Test in staging.
3. Promote to production.

### 6. Monitor

1. Playbook execution count (counter).
2. Playbook execution latency p99 (histogram).
3. Playbook failure rate (counter, by reason).
4. Manual-approval request rate (counter).

### 7. Maintain

1. Quarterly review of all playbooks.
2. Update the playbook when the trigger event schema changes.
3. Update the playbook when the response actions change.
4. Deprecate playbooks that are no longer relevant.

### 8. Authoring checklist

- [ ] Use case documented.
- [ ] Trigger event documented.
- [ ] Inputs documented.
- [ ] Outputs documented.
- [ ] Response actions gated per policy.
- [ ] Audit log captured.
- [ ] Rollback actions exist (where applicable).
- [ ] Schema validation passed.
- [ ] PR review approved.
- [ ] Staging tested.
- [ ] Production deployed.
- [ ] Monitoring wired.

## Rollback

Rollback decisions:

- Playbook failure rate > 1% → investigate; rollback if not actionable.
- Playbook causing unintended containment → immediate disable.
- Schema change in trigger event → pause playbook; update.

Rollback procedure:

1. Disable the playbook in production SOAR.
2. Open a PR to revert the playbook.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` if the playbook caused harm.

## Cross-reference

| Domain | Card |
|---|---|
| SOAR governance | `SOAR_AUTOMATION_GOVERNANCE.md` |
| Detection engineering | `DETECTION_ENGINEERING_PLAYBOOK.md` |
| CTI | `THREAT_INTEL_CONSUMPTION_PLAYBOOK.md` |
| Incident response | `ISO_IEC_27035_2016_INCIDENT_GOVERNANCE.md` |

## References

- `SOAR_AUTOMATION_GOVERNANCE.md`
- `DETECTION_ENGINEERING_PLAYBOOK.md`
- `THREAT_INTEL_CONSUMPTION_PLAYBOOK.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- Cortex XSOAR documentation: `https://docs.paloaltonetworks.com/cortex/cortex-xsoar`
- Tines documentation: `https://www.tines.com/docs/`
- Splunk SOAR documentation: `https://docs.splunk.com/Documentation/SOAR`
