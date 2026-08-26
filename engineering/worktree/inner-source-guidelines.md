# inner-source-guidelines

**Issue:** Internal libraries are siloed by team, causing duplication and inconsistency across the organization
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Team A builds an authentication helper. Team B builds a slightly different one. Team C is about to build a third. Nobody knows the others exist. The organization ships three solutions to the same problem with three sets of bugs.

## Pattern / Solution
InnerSource applies open-source collaboration practices inside the organization. Any team can contribute to any internal codebase by following a contribution process.

**InnerSource model:**
- Every internal repository has a **Trusted Committer (TC)** — the team that owns and merges contributions
- External contributors submit PRs following the project's CONTRIBUTING.md
- The TC reviews and merges (or rejects with explanation) within an SLA

**Repository requirements for InnerSource status:**
- [ ] README explains the project's purpose, how to run it, and how to contribute
- [ ] CONTRIBUTING.md: branching, testing, PR expectations
- [ ] CODEOWNERS file designating the Trusted Committer team
- [ ] An open issue tracker for feature requests and bugs
- [ ] A `good-first-issue` label for welcoming contributions

**Trusted Committer SLA:**
| Action | SLA |
|--------|-----|
| Acknowledge new PR | 2 business days |
| First review | 5 business days |
| Merge or decline (with reason) | 10 business days |

**Discovery:**
- Maintain a central InnerSource catalog (Backstage or a simple wiki page listing all IS repos)
- Tag IS repos in GitHub/GitLab with a `innersource` topic

## Gotchas
- Without the TC SLA, contributors get ignored and give up — enforce the SLA from day one
- Don't InnerSource everything; only repos with genuine cross-team value benefit
- Duplication is better than a shared library with no clear owner

## Related
- `open-source-contribution-process.md`
- `documentation-ownership-model.md`
- `codeowners-advanced-2026.md`
