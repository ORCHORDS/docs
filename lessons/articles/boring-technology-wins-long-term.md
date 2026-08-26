# boring-technology-wins-long-term

**Issue:** Adopting new or trendy technology for its novelty creates operational risk, recruitment difficulty, and long-term maintenance burden
**Date:** 2026-08-11
**Status:** documented

## What happened
A team adopted a cutting-edge graph database to store a simple tree structure that a relational database would have handled trivially. The graph database had poor tooling, sparse documentation, and a small community. When the original champion left, nobody else knew the system. Debugging production issues required consulting the database vendor. Migrating away took eight months.

## The lesson
Choose technology based on fit for the problem, operational maturity, and available talent — not on novelty or hype. Postgres, Redis, and Kafka are "boring" precisely because they are reliable, well-documented, and understood by most engineers. Use boring technology for boring problems. Reserve new technology for problems that boring technology genuinely cannot solve.

## Why it matters
Technology choices have a 10-year tail. The team that adopts a technology is not always the team that maintains it. Operational simplicity, broad hiring pools, and rich documentation compound over time into a significant competitive advantage.

## How to apply
- [ ] Before adopting a new technology, ask: does a boring alternative solve the same problem within 80% of its capabilities?
- [ ] Evaluate the operational surface: monitoring, backup, failover, upgrade path.
- [ ] Check: how many of your current engineers know this technology without training?
- [ ] Require a concrete pain point from an existing technology before replacing it.
- [ ] Treat "cool" and "interesting" as warning signs in a technology decision discussion.

## Related
- `over-engineering-is-a-form-of-tech-debt.md`
- `premature-abstraction-causes-refactors.md`
