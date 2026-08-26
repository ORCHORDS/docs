# github-copilot-workspace

**Issue:** Using GitHub Copilot Workspace for AI-assisted issue-to-PR workflows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers spend significant time translating issue descriptions into implementation plans before writing a single line of code. Copilot Workspace (GA in late 2025) generates a plan, implements it, and opens a PR draft — reducing issue-to-PR time for well-specified tasks.

## Pattern / Solution
Copilot Workspace is accessed from a GitHub Issue or PR via the "Open in Workspace" button (or `gh` CLI).

**Starting a workspace from an issue:**
1. Open any issue #<number>. Click "Open in Copilot Workspace" (top-right menu)
3. Workspace generates: current behavior analysis → proposed changes → implementation plan
4. Review and edit the plan before implementation
5. Click "Implement" — Copilot writes/edits files
6. Review diffs, iterate, then "Create PR"

**Via `gh` CLI (beta):**
```bash
gh copilot workspace create --issue #<number> --repo OWNER/REPO
```

**Effective issue writing for Workspace:**
```markdown
## Problem
[clear, specific description of what's broken or missing]

## Expected behavior
[concrete, testable outcome]

## Technical context
- Affected files: `src/auth/login.ts`, `src/auth/types.ts`
- Related functions: `validateToken()`, `refreshSession()`
- Constraints: must not break existing JWT format
```

**Iterating in Workspace:**
- Edit the plan directly — add/remove steps, specify implementation approach
- After implementation, use the "Revise" feature to change specific files
- Request tests: add a plan step "Write unit tests for the new function in `__tests__/auth.test.ts`"

**Workspace for bug reports:**
Workspace reads the issue, identifies the likely faulty code path, and proposes a targeted fix. Works best when the issue includes a reproduction case or error stacktrace.

## Gotchas
- Workspace works best on self-contained, well-scoped issues — "refactor the entire codebase" produces poor results
- The generated plan must be reviewed before implementing — it can miss edge cases or propose architecturally wrong approaches
- Workspace has read access to the full repo but implementation quality drops significantly in repos >200k LOC
- PRs created by Workspace use a `copilot/` branch prefix; review diffs carefully before merging
- Workspace is included with GitHub Copilot Individual, Business, and Enterprise plans

## Related
- `github-copilot-coding-agent.md`
- `github-issue-forms-2026.md`
- `github-pr-templates-2026.md`
