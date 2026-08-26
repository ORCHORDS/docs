# hackathon-organization

**Issue:** Company hackathons produce demos that never ship and leave engineers feeling like time was wasted
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hack Day arrives. Teams build cool things. There's a demo session. Everyone claps. Then nothing ships. The Jira board is untouched. The next hackathon, participation is lower because engineers remember the last one as entertainment, not impact.

## Pattern / Solution
Design hackathons for real output: working prototypes with a shipping path, not just demos.

**Pre-hackathon (2 weeks before):**
- Announce theme or open theme
- Engineers pitch ideas in a shared doc (1-paragraph format: problem, solution, team needed)
- Team formation: max 4 people; cross-functional encouraged (eng + design + PM)
- Each team nominates a "champion" who will advocate for shipping afterward

**During the hackathon:**
- Duration: 24–48 hours works better than a single afternoon
- Mid-point check-in (brief, not a demo): unblock teams that are stuck
- No meetings, no on-call for participants (arrange cover in advance)
- Provide food, headphones, uninterrupted space

**Demo format:**
- 3 minutes per team: problem → demo → "what would it take to ship this?"
- Voting: peers vote, but weight categories separately (most creative / most likely to ship / best UX)
- Winners: recognition is enough — avoid large prizes that create incentive to game the event

**Post-hackathon shipping path:**
- Within 1 week: teams that want to ship write a 1-page proposal (scope, effort, dependencies)
- Engineering leadership reviews and allocates capacity for top 1–2 proposals
- Shipped hackathon features are celebrated publicly as a direct result of the event

## Gotchas
- If nothing ever ships from hackathons, engineers stop taking them seriously — commit to the shipping path before the event
- "All ideas welcome" hackathons produce unfocused output; a loose theme helps
- Remote hackathons need more structure than in-person — shorter sprints with more check-ins

## Related
- `knowledge-sharing-sessions.md`
- `sprint-planning-engineering.md`
- `async-communication-guidelines.md`
