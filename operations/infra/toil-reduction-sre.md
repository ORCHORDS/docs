# toil-reduction-sre

**Issue:** Identifying and eliminating repetitive operational toil to free SRE capacity for engineering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SRE team spending > 50% of time on manual, repetitive operational tasks that scale with traffic. No time for reliability improvements or automation projects.

## Pattern / Solution
Toil definition (Google SRE):
```
Toil = manual + repetitive + automatable + tactical (no enduring value) + scales with service growth

NOT toil:
- Novel incident response (judgment required)
- Design and architecture work
- Project planning
```

Toil audit process:
```bash
# Track every on-call action for 4 weeks
# Ask for each task:
# 1. Could this be automated? Y/N
# 2. Does it recur? Y/N
# 3. Does it require human judgment? Y/N

# Classify:
# Automate now:    Y/Y/N  (automatable, recurring, no judgment)
# Automate later:  Y/N/N  (automatable, rare, no judgment)
# Improve process: Y/Y/Y  (improve to reduce judgment needed)
# Accept:          N/*/Y  (cannot automate, needs judgment)
```

Example toil → automation:
```python
# TOIL: Manually restart dead Celery workers weekly
# AUTOMATION: Kubernetes liveness probe + auto-restart

# k8s deployment
livenessProbe:
  exec:
    command:
    - sh
    - -c
    - celery -A app inspect ping -d celery@$HOSTNAME
  initialDelaySeconds: 30
  periodSeconds: 30
  failureThreshold: 3

# TOIL: Manually rotate expired TLS certs
# AUTOMATION: cert-manager with Let's Encrypt auto-renewal
```

Toil budget tracking:
```
SRE team capacity allocation:
  Target: < 50% on toil/ops (Google SRE recommendation)
  Remainder: engineering, reliability projects, oncall improvement

Monthly review: track toil hours by category → prioritize automation
```

## Gotchas
- Some toil is irreducible — don't automate judgment-heavy incident response prematurely
- Automating broken processes produces automated broken outcomes — fix the process first
- Track toil reduction over time — without measurement, automation projects lose stakeholder support
- Toil elimination creates capacity; ensure that capacity is protected for reliability work (not absorbed by feature requests)

## Related
- `runbook-automation.md`
- `sre-error-budget-policy.md`
- `chaos-engineering-gameday.md`
