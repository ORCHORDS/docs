# business-continuity-plan

**Issue:** Developing a Business Continuity Plan (BCP) that meets ISO 27001 A.5.29–5.30, SOC 2 A1.2–A1.3, and DORA ICT continuity requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A BCP defines how a business continues operating during and after a disruptive event (major cloud outage, key person loss, office unavailability, supply chain failure). It is distinct from the Disaster Recovery Plan (DRP), which focuses on restoring technology systems. Auditors require both a documented BCP and evidence of annual testing. Many SaaS companies have a DRP but no BCP — this creates a gap in ISO 27001 and SOC 2 audits.

## Pattern / Solution
**BCP structure:**

**1. Business Impact Analysis (BIA)**

For each critical business function, define:
```
Function: Customer support
Owner: Head of Support
Maximum Tolerable Downtime (MTD): 4 hours
Recovery Time Objective (RTO): 2 hours
Recovery Point Objective (RPO): 0 (no data loss acceptable)
Dependencies: Zendesk, Intercom, Slack, VPN
Alternate procedure: Phone bridge + shared Google Doc queue
```

**2. Threat scenarios to cover:**

| Scenario | Likelihood | Impact | Control |
|---|---|---|---|
| Primary cloud region (eu-west-1) outage | Low | Critical | Multi-region failover |
| Key engineer unavailable (bus factor) | Medium | High | Documentation + cross-training |
| SaaS vendor outage (Stripe, Auth0) | Medium | High | Fallback procedures + status page |
| Ransomware / data encryption | Low | Critical | Immutable backups + DR plan |
| Office / HQ unavailable | Low | Medium | Remote-first capability (already in place) |
| Key person departure | Medium | Medium | Knowledge transfer process |

**3. Continuity procedures per scenario:**

```markdown
## Scenario: Primary Cloud Region Outage

Activation trigger: AWS eu-west-1 Service Health Dashboard P1 event
  OR application health check failure > 5 minutes

Immediate actions (0–15 min):
1. Incident commander activates war room
2. Verify outage is regional (not application bug)
3. Post status page update: "Investigating service degradation"

Short-term (15–60 min):
4. Trigger DNS failover to eu-central-1 (standby region)
5. Validate data replication lag at point of failover
6. Verify customer-facing functionality in failover region
7. Post status page update with estimated recovery time

Communication:
- Customers: Status page + email within 30 minutes for P1
- Internal: Slack #incidents
- Leadership: SMS bridge
```

**4. BCP testing requirements:**

| Test type | Frequency | Participants | Evidence |
|---|---|---|---|
| Table-top exercise | Annual | All leads | Meeting minutes + action items |
| Partial failover test | Semi-annual | Engineering | Failover report with RTO achieved |
| Full failover test | Annual | All teams | Full DR test report |
| Communication tree test | Annual | All staff | Confirmation log |

**5. Plan maintenance:**
- Review BCP after: significant architecture change, personnel change in key roles, major incident, annual review cycle.
- Version control BCP in the same repository as runbooks; tag each tested version.

## Gotchas
- BCP and DRP are complementary but distinct — BCP covers business processes; DRP covers technical recovery. Both are required for ISO 27001 A.5.29-5.30.
- MTD > RTO always; if your recovery takes longer than the business can tolerate, the plan is invalid.
- "Remote-first" is not a continuity plan — remote access itself can fail; document alternative access methods.
- Supply chain continuity: if a critical vendor fails, what is the workaround? Document this per vendor tier.
- DORA (for financial entities in EU) requires continuity plans to be tested and reported to the regulator — standard BCP testing evidence is not sufficient without DORA-specific reporting.

## Related
- `disaster-recovery-rto-rpo.md`
- `security-incident-response-plan.md`
- `iso-27001-annex-a-controls.md`
- `dora-regulation.md`
