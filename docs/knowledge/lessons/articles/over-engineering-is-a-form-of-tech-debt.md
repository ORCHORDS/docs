# over-engineering-is-a-form-of-tech-debt

**Issue:** Solutions more complex than the problem require more code to maintain, more time to debug, and slower iteration for every future change
**Date:** 2026-08-11
**Status:** documented

## What happened
A team built a microservices architecture for a product with 200 users. Twelve services communicated via a message bus. Each required its own deploy pipeline, database, and monitoring setup. A simple bug fix required coordinating changes across three services and two shared libraries. A two-hour fix took three days. The team spent more time on infrastructure than features, and the product was late to market.

## The lesson
Solve today's problem with today's tools. Start with the simplest architecture that could work, and evolve it when a specific pain point requires it. Microservices, event sourcing, CQRS, and distributed systems are solutions to scale and team-size problems — not starting points. A well-structured monolith beats a poorly justified microservices cluster every time.

## Why it matters
Every abstraction layer, service boundary, and design pattern must be maintained forever. Complexity borrowed against future scale problems that may never arrive is real tech debt paid with developer time every day.

## How to apply
- [ ] Before introducing an architectural pattern, name the specific current problem it solves.
- [ ] Prefer adding complexity only after experiencing the pain it resolves (database too slow → read replica; monolith too slow to deploy → extract a single service).
- [ ] Write the simplest code that passes the tests; refactor only when a second similar case appears (rule of three).
- [ ] Measure the operational overhead of every new abstraction before adopting it.
- [ ] Include "what are we not building" in technical design documents as explicitly as what you are building.

## Related
- `premature-abstraction-causes-refactors.md`
- `boring-technology-wins-long-term.md`
