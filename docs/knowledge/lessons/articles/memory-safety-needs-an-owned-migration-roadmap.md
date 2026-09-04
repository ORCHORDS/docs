# Memory Safety Needs an Owned Migration Roadmap

**Issue:** Teams acknowledge memory-safety risk in legacy code but address it only through isolated rewrites, compiler flags, or vulnerability patches with no portfolio-level migration plan.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's memory-safety guidance emphasizes creating a roadmap that lets manufacturers prioritize and track movement away from memory-unsafe code, including risk introduced through dependencies. A roadmap turns memory safety from an aspirational language preference into an owned engineering program with milestones and evidence.

## Engineering rule

- Inventory memory-unsafe first-party and dependency code before claiming the risk is understood.
- Require an explicit language/safety decision for new product areas rather than inheriting historical language choices automatically.
- Prioritize legacy migration by exposure, privilege, vulnerability history, maintenance horizon, and feasibility.
- Distinguish interim mitigations from the long-term plan to eliminate or reduce memory-unsafe implementation.
- Give milestones owners, target dates, measurable completion criteria, and review points.
- Publish or communicate progress at the level appropriate to the product and risk model.

## Verification

- Sample high-risk memory-unsafe components and confirm each appears in the roadmap or has a documented disposition.
- Compare roadmap milestones with completed migrations and dependency changes.
- Verify new components have recorded memory-safety language/architecture decisions rather than silent inheritance.

## Official sources

- CISA and FBI, Updated Product Security Bad Practices, January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
- CISA, The Case for Memory Safe Roadmaps: https://www.cisa.gov/resources-tools/resources/case-memory-safe-roadmaps
