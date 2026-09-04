# Memory Safety Roadmap Review Template

Use this record to assess whether a software product or portfolio has a credible, evidence-backed plan for reducing memory-safety risk. CISA/FBI Product Security Bad Practices is voluntary guidance; applicability and prioritization should be documented rather than assumed.

## Review metadata

- Product/portfolio scope: `<scope>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Roadmap owner: `<role or team>`
- Roadmap version/date: `<reference>`

## Language and dependency inventory

| Component/product area | Primary implementation language | Memory-safe? | New or legacy? | Security-critical exposure | External/native dependencies | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `<component>` | `<language>` | `<yes/no/mixed>` | `<new/legacy>` | `<high/medium/low + rationale>` | `<summary>` | `<reference>` |

## Roadmap review

- [ ] The roadmap identifies memory-unsafe product areas and native dependencies rather than considering only first-party source code.
- [ ] New product-line language choices document whether a readily available memory-safe alternative was evaluated.
- [ ] Legacy memory-unsafe areas are prioritized using exposure, privilege, vulnerability history, exploitability, and maintenance horizon.
- [ ] The roadmap distinguishes long-term elimination of memory-unsafe code from interim mitigations such as compiler hardening, fuzzing, control-flow protections, or targeted rewrites.
- [ ] Migration milestones have owners, target dates, dependencies, and measurable completion criteria.
- [ ] Build/toolchain/platform constraints that prevent migration are documented with review dates rather than treated as permanent assumptions.
- [ ] External/open-source dependencies with memory-unsafe code are included in dependency and upgrade decisions.
- [ ] Progress can be reported using repeatable evidence such as code share, component completion, or vulnerability-class trend metrics.

## Priority decisions

| Area | Risk driver | Planned action | Interim controls | Owner | Target/review date | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `<area>` | `<driver>` | `<rewrite/migrate/replace/retain>` | `<controls>` | `<owner>` | `<date>` | `<status>` |

## Evidence and findings

- Current memory-safety inventory: `<reference>`
- Published/internal roadmap: `<reference>`
- Migration proof or completed milestones: `<reference>`
- Exceptions/constraints: `<reference>`
- Findings and corrective actions: `<text>`

## Sources

- CISA and FBI, Updated Product Security Bad Practices, January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
- CISA, The Case for Memory Safe Roadmaps: https://www.cisa.gov/resources-tools/resources/case-memory-safe-roadmaps
