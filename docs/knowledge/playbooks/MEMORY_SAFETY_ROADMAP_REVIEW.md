# Memory Safety Roadmap Review

## Trigger
Run when establishing or refreshing a memory-safety roadmap, before major new product-line language decisions, after material dependency changes, and during periodic secure-by-design review.

## Inputs
- Product/component language inventory.
- Native and memory-unsafe dependency inventory.
- Vulnerability history and exploitability/exposure context.
- Current migration roadmap, owners, milestones, and constraints.
- Interim compiler/runtime/testing mitigations.

## Procedure
1. Enumerate product areas and dependencies that use memory-unsafe languages or native interfaces.
2. Separate new-development decisions from legacy migration decisions so historical constraints do not silently determine new product choices.
3. Prioritize migration candidates using exposure, privilege, vulnerability history, maintenance horizon, dependency constraints, and engineering feasibility.
4. For new product areas, record whether a readily available memory-safe implementation approach was evaluated and why the selected approach is appropriate.
5. For legacy areas, define the planned disposition: migrate, rewrite, replace, retire, isolate, or temporarily retain with explicit interim controls.
6. Distinguish interim mitigations such as compiler hardening, fuzzing, sanitizers, control-flow protections, or targeted rewrites from the long-term migration objective.
7. Give each roadmap milestone an owner, target/review date, dependencies, and measurable completion criteria.
8. Include memory-unsafe third-party/native dependencies in upgrade, replacement, and supplier decisions rather than limiting the roadmap to first-party source.
9. Compare current evidence against previous milestones and identify stalled, completed, or newly discovered areas.
10. Record constraints that block migration with a reassessment date rather than treating them as permanent exceptions.

## Escalation
Escalate high-exposure or privileged memory-unsafe areas with repeated vulnerability history and no owned migration/disposition plan, and new product decisions that bypass the documented safety review.

## Evidence
- Language and dependency inventory.
- Prioritization rationale.
- Roadmap milestones and owners.
- Completed migration/rewrite evidence.
- Interim-control evidence.
- Constraints and reassessment dates.

## Completion criteria
Memory-unsafe product and dependency areas are inventoried, risk-prioritized, assigned an explicit disposition, and tracked through owned milestones with measurable evidence of progress.

## Source basis
- CISA and FBI, Updated Product Security Bad Practices, January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
- CISA, The Case for Memory Safe Roadmaps: https://www.cisa.gov/resources-tools/resources/case-memory-safe-roadmaps
