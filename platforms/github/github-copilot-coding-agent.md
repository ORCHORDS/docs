# github-copilot-coding-agent

**Issue:** GitHub Copilot Coding Agent — autonomous issue-to-PR
**Date:** 2026-08-09
**Status:** documented

## Symptom
You assign an issue to `@copilot`. It spins up
a sandbox, plans, edits code, opens a PR. 59
minutes later, a PR is waiting. You realize the
agent is real, not autocomplete.

## Root cause
**Coding Agent ≠ autocomplete.** Async, sandboxed.

**Source:** GitHub Docs + changelog 2026.

## The "Coding Agent" concept

Copilot Coding Agent:
- **Trigger:** `@copilot` on issue
- **Sandbox:** GitHub Actions
- **Output:** Branch + PR
- **Distinct from:** Inline autocomplete
- **Use:** Multi-file work

The agent is async.

## The "issue assignment" pattern

For trigger:
- **Mention:** `@copilot` in issue
- **Body:** Acceptance criteria
- **Repro:** Steps
- **Target:** Files if known
- **Why:** Specific = better

The issue is the input.

## The "59-min session" pattern

For limit:
- **Cap:** 59 minutes per session
- **Long:** Chain issues
- **Cost:** Per session
- **Quality:** Focus on small
- **Why:** Bounded

The session is bounded.

## The "review like human" pattern

For PR:
- **Diff:** Review all
- **CI:** Must pass
- **CODEOWNERS:** Required
- **Revert:** Allowed
- **Why:** Non-deterministic

The review is mandatory.

## The "security campaign" pattern

For alerts:
- **Code-scanning:** Assign to agent
- **Dependabot:** Auto-fix via agent
- **Status:** Tracking in issue
- **Why:** Security at scale
- **2026:** Autofix GA

The campaign is auto.

## The "session streaming" pattern

For observe:
- **Real-time:** Watch work
- **Cost:** Control
- **Quality:** Adjust
- **2026:** Public preview
- **Why:** Trust + debug

The stream is real-time.

## The "reasoning level" pattern

For cost:
- **Levels:** Configurable
- **Trade:** Quality vs cost
- **Per issue:** Set
- **Why:** Budget control
- **2026:** Customize

The level is per issue.

## The "code review agent" pattern

For review:
- **Skills:** Extensible (MCP)
- **GA:** 2026
- **Effort levels:** Configurable
- **Why:** Augment human
- **Note:** Different agent

The review is separate.

## The "use as autocomplete" anti-pattern

For nit:
- **Issue:** Wastes 59 min
- **Fix:** Inline for single-line

The scope is appropriate.

## The "auto-merge agent PR" anti-pattern

For auto-merge:
- **Issue:** Non-deterministic
- **Fix:** Human review

The merge is gated.

## The "vague issue" anti-pattern

For vague:
- **Issue:** Bad output
- **Fix:** Specific acceptance

The issue is detailed.

## The "blanket access" anti-pattern

For all repos:
- **Issue:** Seats in repos
- **Fix:** Trusted only

The access is scoped.

## The "no timeout awareness" anti-pattern

For 59-min:
- **Issue:** Big refactor fails
- **Fix:** Chain issues

The chain is used.

## The "vs Workspace" anti-pattern

For conflate:
- **Issue:** Different
- **Fix:** Coding Agent = PR

The agent is the cloud one.

## The "no CODEOWNERS" anti-pattern

For no owners:
- **Issue:** Auto-merge risk
- **Fix:** CODEOWNERS required

The owners are set.

## The "issue templates" pattern

For agent:
```yaml
# .github/ISSUE_TEMPLATE/agent-task.md
name: Agent task
body:
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      description: How do you know it's done?
  - type: textarea
    id: repro
    attributes:
      label: Steps to reproduce
  - type: input
    id: files
    attributes:
      label: Target files
```

The template is structured.

## The "branch limit" pattern

For repos:
- **Single repo:** Per session
- **Cross-repo:** Not supported
- **Why:** Sandboxed
- **Fix:** Multiple sessions

The repo is single.

## The "Business/Enterprise" pattern

For plan:
- **Public:** Free
- **Private:** Business / Enterprise
- **API:** Quota per plan
- **Why:** Cost
- **Check:** Your plan

The plan is per usage.

## The "responsible use" pattern

For guardrails:
- **IP:** Filtered
- **Code:** Suggestions OK
- **PII:** Avoided
- **Why:** Compliance
- **Doc:** Responsible use page

The use is responsible.

## The "agent checklist" pattern

For checklist:
- [ ] Issue specific
- [ ] Repro steps
- [ ] Target files
- [ ] Acceptance criteria
- [ ] CI green
- [ ] CODEOWNERS review
- [ ] Session < 59 min
- [ ] Chain if long
- [ ] Streaming observed
- [ ] Trusted repos

The checklist is 10.

## Verification
- **Test:** PR reviewed
- **Test:** CI green
- **Test:** No unrelated edits
- **Audit:** Per session

## Gotchas
- **The "autocomplete" anti-pattern.** Async agent.
- **The "auto-merge" anti-pattern.** Human review.
- **The "vague issue" anti-pattern.** Specific.

## Related
- `github/github-actions-monorepo-caching.md`
- `github/reusable-workflows-vs-composite.md`
- `github/branch-protection-and-codeowners.md`
- `github/github-fine-grained-personal-access-tokens.md`
- `lessons/when-to-ask-vs-push.md`
- GitHub Docs: https://docs.github.com/en/copilot/concepts/agents/coding-agent
- GitHub Changelog: https://github.blog/changelog/label/copilot/
- Responsible use: https://docs.github.com/en/copilot/responsible-use-of-github-copilot-features/responsible-use-of-github-copilot-coding-agent-on-githubcom
