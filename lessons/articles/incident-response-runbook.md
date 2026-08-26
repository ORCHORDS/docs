# incident-response-runbook

**Issue:** Incident response — NIST-aligned runbook
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user reports a security incident. Your team
scrambles. No one knows who's in charge. The on-call
is on vacation. You spend 2 hours figuring out the
basics. You wish you had a runbook.

## Root cause
**Without a runbook, every incident is chaos.** Use
NIST SP 800-61.

**Source:** NIST SP 800-61 Rev 3:
https://csrc.nist.gov/projects/incident-response

## The "5 parts" pattern

For 5 parts (NIST-aligned):
1. **Chain of command:** Who decides, who acts, who comms
2. **Severity criteria:** SEV1-4 yardstick
3. **Runbook:** Detect → triage → mitigate → verify → communicate
4. **Detect-respond connection:** Alert points to runbook
5. **Postmortem:** Turn failure into learning

The 5 parts are pre-built.

## The "roles" pattern

For roles:
- **Incident Commander (IC):** Owns response
- **Operations Lead (Ops):** The executor
- **Communications Lead:** Internal + external
- **Forensics Lead:** Evidence + chain of custody
- **Legal Liaison:** Counsel + regulators
- **Executive Liaison:** Major decisions

Roles are assigned in advance.

## The "severity" pattern

For SEV1-4:
| SEV | Definition | Target |
|---|---|---|
| **SEV1** | Full outage / data loss / payment miss | Immediate |
| **SEV2** | Major function degraded / broad impact | Minutes |
| **SEV3** | Limited / workaround exists | Business hours |
| **SEV4** | Cosmetic / no impact | Next sprint |

The target is derived from SLO.

## The "runbook skeleton" pattern

For a runbook:
```markdown
# Runbook: <alert name / scenario>
Last updated: 2026-08-09 / Owner: <team> / SLO: <name>

## 0. Symptom
- Firing alert: <name>
- Expected severity: SEV2

## 1. Detect
- Dashboard: <URL>
- Confirmation query: <filter>

## 2. Triage
- Judge severity (SEV1-4)
- Declare IC if SEV1/2
- Open incident channel

## 3. Mitigate (stop the bleeding first)
- [ ] First move: feature flag off / rollback
- [ ] Second move: scale out / rate limit / failover
- Commands: copy-paste ready

## 4. Verify
- Recovery condition: metric < threshold for N min
- Reprocess missed work

## 5. Communicate
- Initial report template
- Update frequency (SEV1: every 30 min)
- Status page update

## 6. Postmortem
- When (SEV1/2)
- Template link
```

The skeleton is consistent.

## The "first 30 minutes" pattern

For SEV1/2 first 30 min:
1. **IC opens war room** + pages response team
2. **Isolate endpoints** (EDR network containment)
3. **Disable compromised account** + revoke sessions
4. **Snapshot VMs** + cloud instances
5. **Freeze deploys** + scheduled jobs
6. **Verify backups** isolated + immutable
7. **Engage legal** + cyber insurance
8. **Start incident log** (every action, timestamp, actor)

The first 30 min is critical.

## The "first 4 hours" pattern

For first 4 hours:
1. **Expand containment** to similar indicators
2. **Scope blast radius:** Accounts, systems, data
3. **Preserve memory + disk** from 2+ endpoints
4. **Confirm backup integrity** by test restore
5. **Initial notification** to executive leadership
6. **Coordinate with law enforcement** if applicable
7. **Build timeline** from EDR + SIEM + auth logs

The 4-hour mark is the second checkpoint.

## The "first 24 hours" pattern

For first 24 hours:
1. **Internal all-hands** with approved facts
2. **Ransom decision** in writing (default: no payment)
3. **Rebuild identities** + rotate secrets
4. **Restore from clean backup** (verified)
5. **Notify customers** (per regulation + contract)
6. **Notify regulators** (per 72h GDPR etc.)
7. **Engage outside IR firm** if needed

The 24-hour mark is the third checkpoint.

## The "ransomware" pattern

For ransomware:
1. **Isolate** affected hosts (immediate)
2. **Disable** compromised accounts
3. **Snapshot** before any remediation
4. **Verify** backups are clean
5. **Engage** legal + insurance
6. **Default:** No payment
7. **Rebuild** from clean backup

The ransomware playbook is the most critical.

## The "BEC" pattern

For business email compromise:
1. **Disable** compromised account
2. **Pull** forwarding rules + OAuth grants
3. **Freeze** pending wire transfers
4. **Alert** finance team
5. **Engage** bank if funds moved
6. **FBI IC3** if funds moved
7. **Force** password + MFA re-enrollment

The BEC playbook.

## The "insider threat" pattern

For insider threat:
1. **Coordinate** with HR + legal first
2. **Preserve** logs (don't disable account immediately)
3. **Snapshot** endpoint
4. **Forensic image** of devices
5. **Freeze** access (coordinated)
6. **Document** the signal + detection time

The insider threat playbook.

## The "supply chain" pattern

For supply chain:
1. **Identify** every instance of compromised product
2. **Isolate** hosts
3. **Block** C2 indicators
4. **Freeze** in-flight deploys
5. **Apply** patch or replace
6. **Rotate** secrets the product had access to
7. **Update** SBOM

The supply chain playbook.

## The "evidence preservation" pattern

For evidence:
- **Memory dumps** from 2+ endpoints
- **Disk images** from 2+ endpoints
- **Auth logs** for the window
- **Network logs** (firewall + DNS)
- **Chain of custody** documented
- **Hash values** recorded

The evidence is preserved.

## The "communication" pattern

For comms:
- **Internal all-hands:** Approved by legal
- **Customer notification:** Tiered by data sensitivity
- **Regulator:** On required timeline (72h GDPR)
- **Public statement:** Only if public
- **Status page:** Updated

The comms is structured.

## The "postmortem" pattern

For postmortem:
- **Within 48h:** For SEV1/2
- **Blameless:** No "you should have"
- **Timeline:** What happened when
- **Root cause:** What allowed this
- **Action items:** SMART, owned, dated

The postmortem is structured.

## The "on-call" pattern

For on-call:
- **Rotation:** Weekly
- **Primary + secondary:** Per shift
- **50% eng time:** Protected
- **25% on-call max:** For each person
- **2 per 12-hour shift:** Sustainable limit

The on-call is sustainable.

## The "alert-to-runbook" pattern

For alert linking:
```yaml
# In your monitoring
- alert: DBConnectionsExhausted
  annotations:
    runbook: https://wiki.example.com/runbooks/db-connections
    severity: SEV1
    first_action: "Scale up the connection pool"
```

Every alert has a runbook link.

## The "runbook testing" pattern

For testing:
- **Tabletop:** Annual (all-hands)
- **Game day:** Quarterly (live scenario)
- **Walk-through:** Monthly
- **Update:** After every incident

The runbook is tested.

## The "runbook anti-pattern" anti-patterns

### 1. No runbook
- **Issue:** Chaos
- **Fix:** Write a runbook

### 2. Stale runbook
- **Issue:** Wrong steps
- **Fix:** Update after every incident

### 3. No IC
- **Issue:** No decision
- **Fix:** Assign IC

### 4. No severity
- **Issue:** Wrong response
- **Fix:** SEV1-4 criteria

### 5. No postmortem
- **Issue:** Same incident
- **Fix:** Always postmortem

## Verification
- **Test:** Runbook exists
- **Test:** Alert has runbook link
- **Test:** Tabletop is done
- **Live:** MTTD + MTTR monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no runbook" anti-pattern.** Write one.
- **The "no severity" anti-pattern.** Use SEV1-4.
- **The "no postmortem" anti-pattern.** Always.

## Related
- `lessons/incident-response-runbook.md`
- `compliance/soc2-compliance.md`
- `compliance/iso-27001-compliance.md`
- `lessons/lazy-fail-discoveries.md`
- NIST: https://csrc.nist.gov/projects/incident-response
- Efros template: https://efros.com/resources/incident-response-runbook/
- Tomoda guide: https://tomodahinata.com/en/blog/incident-response-runbook-postmortem-oncall-sre-guide
