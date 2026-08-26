# space-framework-developer-experience

**Issue:** DORA metrics only measure delivery speed and miss developer well-being and collaboration quality
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A team hits elite DORA numbers by sacrificing code review quality and working nights. Burnout follows. The metrics looked great until attrition hit 40%.

## Pattern / Solution
The SPACE framework (Microsoft Research, 2021) provides five dimensions for measuring developer experience holistically.

**S — Satisfaction and well-being**
- Survey: "How satisfied are you with your development environment?"
- Signal: Developer eNPS (Employee Net Promoter Score for engineering tools)
- Signal: On-call fatigue survey, burnout indicators

**P — Performance**
- Outcomes, not output: code review quality, incident rate, customer satisfaction
- Code review turnaround time
- % of features shipped that met acceptance criteria on first pass

**A — Activity**
- Volume signals (use cautiously): PRs opened, code commits, incidents resolved
- Note: activity metrics are easiest to game — always contextualize with performance

**C — Communication and collaboration**
- PR review participation rate (who reviews vs. who only gets reviewed)
- Cross-team contribution frequency
- Knowledge sharing session attendance and satisfaction

**E — Efficiency and flow**
- Flow state proxy: uninterrupted focus time (survey-based)
- Build/CI wait time
- Number of context switches per day (estimated from calendar/meeting load)
- PR cycle time from open to merge

**Quarterly survey questions (pick 5–7):**
1. "I have the tools I need to do my job effectively" (1–5)
2. "My development environment is reliable and fast" (1–5)
3. "I feel energized at work most of the time" (1–5)
4. "I rarely feel blocked by other teams or processes" (1–5)
5. "I understand how my work connects to company goals" (1–5)

## Gotchas
- SPACE is not a replacement for DORA; use both together
- Survey frequency matters — quarterly is the sweet spot; monthly creates fatigue, annually is too slow
- Activity dimension is the most misused — never rank engineers by commit volume

## Related
- `dora-metrics-implementation.md`
- `developer-productivity-metrics.md`
- `engineering-kpis-dashboard.md`
