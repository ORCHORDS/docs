# codeowners-scaling-monorepo-org

**Issue:** CODEOWNERS works beautifully in a 30-file repo and degrades sharply with scale. In a monorepo or multi-team org, the single effective CODEOWNERS file grows to thousands of lines owned by nobody in particular; teams edit it in conflicting ways; entries point at users who left or teams that were renamed; and because GitHub uses exactly one CODEOWNERS file per branch — searched only in `.github/`, then root, then `docs/`, first match wins — every scaling mistake compounds silently. Meanwhile GitHub has been moving the enforcement layer forward: rulesets gained required review by specific teams in November 2025 and the required reviewer rule went generally available in February 2026, and Dependabot's own `reviewers` option was removed in May 2025 in favor of code owners, making CODEOWNERS the single source of review truth. Getting the scaling model right matters more in 2026 than ever.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The platform constraints that shape any scaling strategy

1. **One file per branch, three search locations.** GitHub looks for CODEOWNERS in `.github/CODEOWNERS`, then the repository root, then `docs/`, and uses only the first one found. Subdirectory CODEOWNERS files are ignored — nested CODEOWNERS remains an open community feature request (community discussion #21809), not a shipped feature. Any design that assumes per-directory ownership files natively is wrong.
2. **Last matching pattern wins.** Unlike gitignore, the pattern that matches and is defined latest in the file takes precedence. Scaling a file means managing an ordering discipline: broad prefixes at the top, specific exceptions below — and this ordering is the first casualty when five teams append entries in parallel.
3. **Hard 3 MB limit.** If CODEOWNERS exceeds 3 MB it stops loading entirely — not partially, entirely. Monorepos that naively enumerate every file path hit this; consolidation with wildcards and directory globs is a requirement, not a nicety.
4. **Owners must have write access.** Users and teams that lack explicit write access are silently skipped as owners (with UI/API surfacing of the invalid line). At org scale, team renames and access reviews periodically invalidate entries, so CODEOWNERS hygiene must be coupled to access hygiene.
5. **Case-sensitive patterns, gitignore-like syntax.** Patterns follow most gitignore rules, but negation with `!`, escaped `#` comments, and character ranges do not work. Path casing errors produce entries that match nothing and protect nothing.

## Patterns that survive scale

1. **Generate the file, do not hand-edit it.** The proven monorepo pattern is Gerrit-style distributed OWNERS files (one per team directory) compiled by a CI job into the single root `.github/CODEOWNERS`. Teams edit their own OWNERS file in their own code; the generator owns ordering and deduplication. Open-source tools exist for exactly this workflow, and the generator can enforce ordering rules humans will not.
2. **Directory-prefix ownership as the default rule.** One entry per top-level package (`/services/auth/ @org/auth-team`) covers 95% of files with 5% of the lines. File-level entries are reserved for genuinely exceptional files, and a lint in the generator can reject new file-level entries that duplicate a directory rule.
3. **Multiple owners on one line.** Listing several teams on the same entry line gives each of them review rights; splitting them across duplicate lines means only the last line matches. Co-owned boundary directories (generated code, shared proto) want same-line multi-ownership.
4. **Own the CODEOWNERS file itself.** The file is an access-control artifact: protect `.github/CODEOWNERS` (and the OWNERS source files) with a required review from a platform/owner team, via branch protection or a ruleset that includes the file path in its conditions.
5. **Anchor patterns.** Unanchored patterns match at any depth, which at scale causes accidental matches. Anchor directory rules with a leading slash so `/configs/` does not capture `/services/foo/configs/` unintentionally.

## The 2025-2026 ruleset shift

1. **Required review by specific teams in rulesets (Nov 2025).** Rulesets can now require approvals from specific teams based on files and folders — a second enforcement layer alongside CODEOWNERS. Use it when the required reviewer set differs from the review-request set (e.g., security must approve `security/` even when they are not the code owners).
2. **Required reviewer rule GA (Feb 2026).** The granular required-reviewer rule is generally available, giving rulesets statuses, layering, and evaluation modes that branch protection lacks. Migrating CODEOWNERS enforcement from branch protection to rulesets is the current recommended direction for orgs (and is documented separately in this knowledge base).
3. **Dependabot reviewers option removed (May 2025).** The `reviewers` field in `dependabot.yml` was removed in favor of code owners — Dependabot now requests review from CODEOWNERS-matched owners. Any org that leaned on Dependabot's separate reviewer list has already been migrated by force; keeping CODEOWNERS accurate is now the only knob.
4. **Files changed validation (Feb 2026).** The new pull request Files changed experience includes CODEOWNERS validation, surfacing invalid lines and who will be requested at review time — use this as the pre-merge check instead of discovering silent skips after the fact.

## Operating hygiene at org scale

1. **Quarterly ownership audit.** Script a check that every owner team still exists, still has write access, and has active members; invalid entries are silently skipped by GitHub, so the failure mode is unprotected paths, not error messages.
2. **Diff-aware review requests.** In repos with generated files, add generated paths to a no-owner section or have the generator emit explicit `@org/automation` ownership so generated-code PRs do not page humans who cannot review them.
3. **Keep the file below a size budget.** Beyond the 3 MB hard limit, set an internal soft budget (tens of KB) — a CODEOWNERS that reviewers cannot skim is one nobody reviews, and it is an access-control file.
4. **Test changes like code.** A PR that edits CODEOWNERS or an OWNERS source should show, in its check run, which paths changed owners — the compile step can emit that diff into the job summary so reviewers approve ownership changes with evidence rather than faith.
