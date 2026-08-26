# engineering-principles-document

**Issue:** Engineers make inconsistent technical choices because there are no shared guiding principles
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
One team builds a custom caching layer. Another uses Redis. A third avoids caching entirely. None of these decisions are wrong in isolation, but without shared principles, every team reinvents the wheel and the architecture becomes a patchwork.

## Pattern / Solution
An engineering principles document articulates the beliefs and heuristics that guide technical decision-making across the organization.

**What principles are (and aren't):**
- Principles are opinionated heuristics, not rules
- They help resolve trade-offs, not eliminate them
- They should be contestable — if everyone already agrees, it's obvious and doesn't need writing down

**Example principles document structure:**
```markdown
# Engineering Principles — [Company Name]

**Last updated:** YYYY-MM-DD
**Process for updating:** PR to this file, requires two principal engineer sign-offs

## 1. Boring technology by default
We prefer proven, well-understood tools over novel ones. The cost of something new is ongoing maintenance and expertise acquisition. We innovate where it creates competitive advantage, not in our observability stack.

## 2. Simple over clever
Code is read ten times for every time it is written. Prefer the solution a new engineer can understand over the one that's technically optimal.

## 3. Explicit over implicit
Configuration, dependencies, and behavior should be obvious from reading the code. Magic is a short-term convenience and a long-term tax.

## 4. Build for operability
Features aren't done until they're monitorable. Every significant code path should emit observable signals (metrics, logs, traces). Design for the 2am engineer.

## 5. Prefer reversibility
When in doubt, choose the option that's easier to change. Avoid designs that require coordinated multi-team rollbacks to undo.

## 6. Own your services
Teams are responsible for their services in production. We don't throw things over the wall to SRE or platform. "You build it, you run it."
```

## Gotchas
- Principles not referenced in code reviews or design discussions are wall art, not principles
- Don't write principles that are already obvious ("write tests") — focus on the genuinely contested trade-offs
- Revisit principles annually — a principle that no longer generates disagreement might no longer be needed

## Related
- `adr-architecture-decision-records.md`
- `tech-debt-tracking-process.md`
- `design-doc-template.md`
