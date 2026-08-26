# open-source-contribution-process

**Issue:** Engineers want to contribute to open source but the process, IP rules, and time allocation are unclear
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An engineer fixes a bug in an upstream library but isn't sure if they can open-source the fix. Or they contribute on company time without knowing the IP policy. Or contributions happen ad hoc with no visibility to the team.

## Pattern / Solution
Establish a clear open-source contribution policy and lightweight approval process.

**Policy framework:**
1. **Pre-approved contributions (no approval needed):**
   - Bug fixes to dependencies the company uses
   - Documentation improvements
   - Contributions to projects the company already sponsors

2. **Light approval (team lead sign-off):**
   - New features to upstream libraries relevant to company work
   - Time allocation > 4 hours in a sprint

3. **Legal review required:**
   - Releasing internal tools as open source
   - Contributing to projects with IP-sensitive overlap
   - CLA (Contributor License Agreement) with unusual terms

**Contribution workflow:**
```
1. Check the project's CONTRIBUTING.md before starting
2. Open an issue or comment on an existing one to signal intent
3. Fork, branch from main (not a stale branch)
4. Keep the PR focused: one fix per PR #<number>. Add tests if the project requires them
6. Sign the CLA if prompted (verify with legal if in doubt)
7. Respond to reviewer feedback within 5 business days
```

**Tracking:**
- Log contributions in a team "open source contributions" doc (project, PR link, status)
- Include notable merged contributions in quarterly engineering updates

## Gotchas
- CLA terms vary — some assign copyright to the foundation, others are permissive
- Don't contribute internal proprietary code disguised as a generic utility
- DCO (Developer Certificate of Origin) sign-off is required by many Linux Foundation projects: `git commit -s`

## Related
- `inner-source-guidelines.md`
- `engineering-blog-process.md`
- `documentation-ownership-model.md`
