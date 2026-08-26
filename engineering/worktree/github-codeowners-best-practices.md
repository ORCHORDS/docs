# github-codeowners-best-practices

**Issue:** CODEOWNERS — owner assignment discipline
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add `@alice` to CODEOWNERS. Alice leaves.
PRs auto-assign to a non-existent person. You
realize teams, not individuals.

## Root cause
**CODEOWNERS data, not enforcement.** Use teams + rulesets.

**Source:** GitHub Docs 2026.

## The "CODEOWNERS" concept

CODEOWNERS:
- **File:** `.github/CODEOWNERS`
- **Format:** Path + owner
- **Effect:** Auto-request review
- **Enforcement:** Ruleset
- **Use:** Ownership

The CODEOWNERS is data.

## The "team not individual" pattern

For team:
- **`@org/team-name`:** Survives
- **`@alice`:** Rots
- **Why:** Org changes
- **Fix:** Always team

The team is the unit.

## The "file location" pattern

For path:
- `.github/CODEOWNERS` (preferred)
- `docs/CODEOWNERS`
- `<root>/CODEOWNERS`
- **Priority:** First match
- **Why:** Canonical

The location is canonical.

## The "order specific" pattern

For match:
- **Most specific:** First
- **General:** Last
- **Why:** Positional
- **Fix:** Order matters

The order is specific.

## The "ruleset enforcement" pattern

For enforcement:
- **CODEOWNERS:** Auto-request
- **Ruleset:** "Require review from Code Owners"
- **Why:** CODEOWNERS alone = request
- **Fix:** Ruleset

The ruleset enforces.

## The "optional reviewer" pattern

For optional:
```
# ? for optional
/docs/ @org/tech-writers
```

The optional is per line.

## The "wildcard" pattern

For group:
```
# All TSX
**/*.tsx @org/frontend

# All JS
**/*.js @org/frontend
```

The wildcard is per pattern.

## The "fallback" pattern

For default:
```
# Last line = fallback
/* @org/triage
```

The fallback is the safety net.

## The "size limit" pattern

For file:
- **Limit:** ~3,000 entries
- **Over:** Silently not loaded
- **Why:** Worst possible failure
- **Fix:** Compact patterns

The file is bounded.

## The "individual" anti-pattern

For `@alice`:
- **Issue:** Departs
- **Fix:** `@org/team`

The team is set.

## The "expecting enforcement" anti-pattern

For alone:
- **Issue:** Doesn't block
- **Fix:** Ruleset
- **Why:** Request, not require

The ruleset enforces.

## The "monolithic fallback" anti-pattern

For `/*`:
- **Issue:** Bottleneck
- **Fix:** Per-area
- **Why:** Defeats purpose

The fallback is specific.

## The "no wildcard" anti-pattern

For verbose:
- **Issue:** 50 lines
- **Fix:** `**/*.tsx`
- **Why:** Compact

The wildcard is used.

## The "no optional" anti-pattern

For all-required:
- **Issue:** Bottleneck
- **Fix:** `?` syntax
- **Why:** Per-line control

The optional is used.

## The "no fallback" anti-pattern

For un-owned:
- **Issue:** No review
- **Fix:** `/* @org/triage`
- **Why:** Catch-all

The fallback is set.

## The "wiki duplicate" anti-pattern

For wiki:
- **Issue:** Drifts
- **Fix:** File is source
- **Why:** Version control

The source is the file.

## The "size limit" anti-pattern

For > 3000:
- **Issue:** Silent fail
- **Fix:** Compact
- **Why:** Worst case

The file is compact.

## The "size limit check" pattern

For check:
```bash
# GitHub has hard limit
# Keep < 3,000 entries
wc -l .github/CODEOWNERS
```

The check is per file.

## The "CODEOWNERS for security" anti-pattern

For security:
- **Issue:** Write-access bypass
- **Fix:** Ruleset for the file
- **Why:** Not boundary

The ruleset protects the file.

## The "CODEOWNERS checklist" pattern

For checklist:
- [ ] Teams not individuals
- [ ] Canonical location
- [ ] Most specific first
- [ ] Ruleset enforcement
- [ ] Optional per line
- [ ] Wildcards
- [ ] Fallback line
- [ ] < 3000 entries
- [ ] File protected
- [ ] Periodic audit

The checklist is 10.

## Verification
- **Test:** New file owner
- **Test:** Team persists
- **Test:** Ruleset enforces
- **Audit:** Quarterly

## Gotchas
- **The "individual" anti-pattern.** Team.
- **The "expecting enforcement" anti-pattern.** Ruleset.
- **The "size limit" anti-pattern.** Compact.

## Related
- `worktree/git-submodules-vs-subtrees.md`
- `worktree/github-merge-queue.md`
- `github/branch-protection-and-codeowners.md`
- `github/pr-template-and-issue-templates.md`
- `lessons/code-review-best-practices.md`
- GitHub: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- Rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
