# deployment-window-management

**Issue:** Defining and enforcing deployment windows to reduce risk and coordinate changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deployments during peak traffic or outside business hours increase incident severity and slow recovery (no one available). Deployment windows balance agility with risk management.

## Pattern / Solution
Deployment window policy (example):
```markdown
## Production Deployment Windows

### Standard Window
- Monday–Thursday 10:00–16:00 local team time
- Excludes: public holidays, code freeze periods, major events

### Emergency / Hotfix Window
- Any time with P1 incident declaration
- Requires: on-call approval, incident bridge open, rollback ready

### Restricted periods (no deploys without VP approval)
- Black Friday / Cyber Monday (Nov)
- End-of-quarter last 3 business days
- Major product launches (announced 2 weeks prior)
```

Enforce in CI (GitHub Actions):
```python
# check-deploy-window.py
from datetime import datetime, timezone
import sys, json, urllib.request

now = datetime.now(timezone.utc)
weekday = now.weekday()  # 0=Mon, 6=Sun
hour_utc = now.hour

# No weekend deploys to production
if weekday >= 5:
    print("Blocked: weekend deployment to production")
    sys.exit(1)

# Window: Mon-Thu 14:00-22:00 UTC (10:00-18:00 ET)
if weekday == 4 or not (14 <= hour_utc < 22):
    print(f"Blocked: outside deployment window (current UTC hour: {hour_utc})")
    sys.exit(1)

# Check freeze calendar API
resp = urllib.request.urlopen("https://deploy-api.internal/freeze/active")
freeze = json.loads(resp.read())
if freeze["active"]:
    print(f"Blocked: deployment freeze active — {freeze['reason']}")
    sys.exit(1)

print("OK: within deployment window")
```

Calendar API service (simple implementation):
```python
FREEZE_PERIODS = [
    {"start": "2026-11-27", "end": "2026-11-30", "reason": "Black Friday"},
    {"start": "2026-12-23", "end": "2026-12-27", "reason": "Holiday freeze"},
]

@app.get("/freeze/active")
def check_freeze():
    today = date.today().isoformat()
    for period in FREEZE_PERIODS:
        if period["start"] <= today <= period["end"]:
            return {"active": True, "reason": period["reason"]}
    return {"active": False}
```

## Gotchas
- Deployment windows must have an emergency override path; a strict block with no override forces risky workarounds
- Time zones: use UTC internally and display in the team's local time in notifications
- Deployment windows create a batch effect (many deploys at 10:00 Monday) — stagger by service to reduce blast radius
- Compliance (PCI, SOX) may require documented evidence of deployment window adherence — log all override uses

## Related
- `deployment-freeze-policy.md`
- `deployment-approval-workflow.md`
- `cab-change-management.md`
- `deployment-notification-slack.md`
