# Memory-Safety Roadmaps Turn Class Elimination Into Product Strategy

**Issue:** Memory-safety work is handled only as individual bug fixes, leaving no product-level plan for reducing the amount of security-critical code exposed to an entire vulnerability class.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's Secure by Design memory-safety guidance frames the transition toward memory-safe programming languages as a product and leadership problem, not merely a local coding preference. CISA's Memory Safe Roadmaps guidance encourages manufacturers to create and publish a roadmap showing how new development and prioritized existing code will move toward memory-safe implementations, with attention to high-risk components and external dependencies. This is secure-by-design guidance, not a universal legal requirement for every software project.

## Engineering rule

- Identify the product components where memory-unsafe code has the greatest security impact, such as network-facing, privileged, parser, or cryptographic paths.
- Prefer memory-safe languages for new components where technically feasible.
- Maintain a prioritized transition plan for high-risk existing components instead of relying only on recurring patching.
- Include important third-party and open-source dependencies in the memory-safety inventory.
- Use compiler/runtime hardening, sanitizers, fuzzing, static analysis, and code review as risk-reduction controls while unsafe code remains.
- Measure reduction of memory-unsafe exposure over time rather than reporting only vulnerability counts.

## Verification

- Inventory security-critical components by implementation language and memory-safety characteristics.
- Confirm new high-risk components have an explicit language/safety decision before implementation.
- Review the roadmap for owners, priorities, milestones, dependency coverage, and evidence of completed migration.
- Compare memory-safety defect trends against the amount of remaining memory-unsafe code so progress is not inferred from a quiet vulnerability period alone.

## Official sources

- CISA, The Case for Memory Safe Roadmaps: https://www.cisa.gov/resources-tools/resources/case-memory-safe-roadmaps
- CISA/FBI, Product Security Bad Practices update, January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
- CISA and partners, Exploring Memory Safety in Critical Open Source Projects: https://www.cisa.gov/news-events/alerts/2024/06/26/cisa-and-partners-release-guidance-exploring-memory-safety-critical-open-source-projects
