# github-copilot-code-review-effort-levels

**Issue:** Configuring GitHub Copilot code review effort levels (GA in 2026) so reviews are fast on small PRs and thorough on big ones
**Date:** 2026-08-12
**Status:** documented

## Context

GitHub Copilot code review became GA for public repos in 2025 and rolled out to
Enterprise in early 2026. The "effort level" setting (announced GA mid-2026)
controls how much reasoning Copilot spends on a review. Teams that leave it on
the default get slow, noisy reviews on every PR; teams that tune it per-PR get
the right signal-to-noise ratio.

This is distinct from the Copilot **coding agent** (see
`github-copilot-coding-agent.md`) which writes code. Code review only comments
on a PR.

## Symptom

- Copilot posts 40+ comments on a 5-line typo fix (effort too high).
- Copilot posts a single "looks good" on a 2000-line architectural change
  (effort too low / default low effort on a complex diff).
- Reviews take 5+ minutes and block the "all checks pass" gate.
- Developers mark Copilot comments as "resolved" without reading them,
  defeating the purpose.

## Configuration

### 1. Repository default effort level

Settings → Copilot → Code review → **Effort level**:

- `low` — fast scan, catches obvious issues (typos, missing tests, obvious
  anti-patterns). Best for draft PRs and small fixes.
- `medium` (default) — balanced; reads the diff and surrounding context.
- `high` — deep reasoning across the whole file and related files. Best for
  security-sensitive PRs, large refactors, public-API changes.

### 2. Request a review with a specific effort level (CLI)

```bash
# Default effort (uses repo setting)
gh pr edit 42 --add-reviewer @copilot

# When creating a PR, request Copilot review immediately
gh pr create --fill --reviewer @copilot
```

As of 2026, the `gh` CLI does not yet accept a per-request `--effort` flag.
To vary effort per-PR, use the API:

```bash
# Request a review with high effort via the REST API
gh api -X POST repos/:owner/:repo/pulls/42/requested_reviewers \
  --field reviewers[]="@copilot" \
  --field copilot_review[effort]="high"
```

### 3. Automatic review on every push

Settings → Copilot → Code review → **Enable automatic code review**.

When enabled, Copilot re-reviews on every push. Pair this with `low` effort for
the repo default so you don't burn through your Copilot quota on
force-push-after-force-push.

### 4. Custom review instructions

Create `.github/copilot-instructions.md` and add a review-specific section:

```markdown
## Code review guidelines

- Do not comment on formatting; Prettier handles it.
- Flag any new `any` type in TypeScript.
- Require tests for any change to `src/payments/`.
- Ignore generated files under `packages/api-types/`.
```

Copilot reads these before reviewing, which cuts noise dramatically regardless
of effort level.

## Gotchas

- **Effort ≠ model.** The effort level controls how much context Copilot pulls
  in and how many reasoning cycles it runs. It does NOT switch the underlying
  model. If you want a stronger model for hard PRs, that's a separate
  per-seat model picker (Claude/Sonnet/etc.) in Enterprise settings.
- **High effort on a monorepo PR can pull in thousands of files of context.**
  This is slow and produces generic comments. Scope Copilot with path-based
  custom instructions or CODEOWNERS so it focuses on the right package.
- **Copilot reviews don't count as a "required review" for branch protection.**
  It posts as a bot; required-review counts still need a human. Don't try to
  use Copilot to satisfy a "1 approval" rule.
- **Re-reviewing after a force-push re-runs at the repo default effort**, not
  the effort of the original request. If you escalated a PR to high effort,
  the re-review drops back to default unless you re-request.
- **Quota.** Enterprise Copilot billing now includes per-model token breakdown
  (see `github-copilot-impact-dashboard.md`). High-effort reviews on every PR
  add up fast. Check the dashboard before turning on auto-review + high effort
  org-wide.
- **The `@copilot` reviewer is special-cased in the GitHub API.** Don't try to
  add it via `reviewers[]="copilot"` (string) — it must be the `@copilot`
  handle or the dedicated `copilot_review` envelope.
- **Draft PRs.** Copilot will review draft PRs if explicitly requested but does
  not auto-review them. Don't expect auto-review to fire on drafts.

## Diagnostic checklist

- [ ] Confirm Copilot is enabled at org/enterprise level (not just repo).
- [ ] Confirm the requesting user has a Copilot seat.
- [ ] Check `.github/copilot-instructions.md` for conflicting guidance.
- [ ] Check the Copilot impact dashboard for whether reviews are actually
      firing (sometimes quota exhaustion silently disables reviews).
- [ ] Verify the PR isn't a draft (no auto-review on drafts).

## References

- Changelog: "Copilot code review effort levels are generally available" (2026)
- Changelog: "Customize the reasoning level for Copilot cloud agent" (2026)
- Related KB: `github-copilot-coding-agent.md`, `github-copilot-workspace.md`
