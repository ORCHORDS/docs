# team-health-check-retrospective

**Issue:** Retrospectives surface the same issues every sprint without any change
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Retro format is "what went well / what didn't / actions." The actions are the same six items for three months running. Nobody follows up. The retro becomes a complaint session with no improvement trajectory.

## Pattern / Solution
Augment the standard sprint retro with a quarterly team health check that measures dimensions beyond sprint execution.

**Spotify Health Check model (adapted):**
Each team member rates these dimensions: 1 (poor) / 2 (okay) / 3 (great)

```
1. Delivering value   — We ship things that matter to users
2. Easy to release    — Deployment is low-friction and low-risk
3. Fun                — This is an enjoyable place to work
4. Health of codebase — The code is something we're proud of
5. Learning           — We're growing our skills
6. Mission            — We understand why our work matters
7. Pawns or players   — We influence our own process and priorities
8. Speed              — We move at a pace that feels sustainable
9. Support            — We get help when we need it
10. Teamwork          — We collaborate well with each other
```

**Facilitation:**
1. Everyone submits ratings anonymously (Google Form or Miro vote)
2. Display aggregated results as a heat map (green/yellow/red per dimension)
3. Team discusses: "Which yellow/red surprises us? Which has changed since last quarter?"
4. Pick one dimension to focus on for the next quarter; create one concrete action

**Connecting to retrospectives:**
- Monthly sprint retros: focus on delivery and process (what went well / didn't / change)
- Quarterly health check: focus on team and culture dimensions
- Annual: review health trend over time; escalate persistent reds to management

**Action template:**
```
Dimension: [Name]
Current rating: 🔴 / 🟡 / 🟢
Root cause: [What's driving this rating?]
Action: [Specific, ownable action]
Owner: @name
Review date: [+3 months]
```

## Gotchas
- Anonymous ratings are critical — attributed ratings inflate everything toward "good"
- One action per quarter is better than five that don't get done
- Persistent reds that don't improve after two quarters are a signal for management escalation

## Related
- `working-agreement-template.md`
- `blameless-culture-implementation.md`
- `space-framework-developer-experience.md`
