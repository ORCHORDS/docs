# tech-debt-tracking-process

**Issue:** Tech debt is acknowledged but never prioritized because it's invisible in the backlog
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers know which parts of the codebase are painful but those areas never get cleaned up. Velocity slows gradually. Hotfixes layer on top of each other. When someone finally touches the area, the blast radius is enormous.

## Pattern / Solution
Make tech debt a first-class artifact with its own tracking, scoring, and allocation.

**Capture:**
- Add a `tech-debt` label in your issue tracker
- Leave `TODO(owner): [debt-tag]` comments in code that link to the ticket
- During retrospectives, surface new debt discovered that sprint

**Scoring template per item:**
```
Impact:    High / Medium / Low   (how much does it slow us down?)
Scope:     Hours / Days / Weeks  (effort to fix)
Risk:      High / Medium / Low   (what breaks if we ignore it?)
Urgency:   Blocking / Soon / Later
```

**Allocation model:**
- Reserve 15–20% of sprint capacity for tech debt
- Create a rotating "debt sprint" every quarter for larger items
- Never let debt allocation fall below 10% two sprints in a row

**Triage cadence:**
1. Monthly: review and re-score open debt tickets
2. Quarterly: pick the top 3 items and schedule them in the roadmap
3. Annually: audit the codebase for uncaptured debt (use static analysis reports)

## Gotchas
- "We'll clean it up later" without a ticket is not a plan — always file the ticket immediately
- Don't mix tech debt with feature work in the same PR unless the change is trivially small
- Score debt by business impact, not engineering aesthetics
- Debt that never gets scheduled should be questioned: maybe it doesn't matter enough to fix

## Related
- `sprint-planning-engineering.md`
- `definition-of-done-checklist.md`
- `engineering-kpis-dashboard.md`
