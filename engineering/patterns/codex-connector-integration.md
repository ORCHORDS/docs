# codex-connector-integration

**Issue:** Integrating the chatgpt-codex-connector bot with a self-improving agent repo
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://github.com/apps/chatgpt-codex-connector)

## Symptom

You want OpenAI's Codex to review PRs, generate code, and
self-improve its skill library in your repo. You install
`chatgpt-codex-connector[bot]` on GitHub, but it doesn't
review your PRs. You call `@codex review` in a comment;
nothing happens. You create a `codex_handoff.md`; Codex
ignores it. You try to add a Codex skill; the format
doesn't match. You end up with a half-integrated AI that
sees the repo but doesn't act on it.

## Root cause

**The connector is a GitHub App, not a CI step.** Installing
it requires a specific 3-party handshake (Codex account +
GitHub installation + Codex settings + AGENTS.md). The
bot has its own identity, its own review trigger
(`@codex review`), and its own skill format (Codex Skills,
not Claude Skills). Self-improvement via Codex is a
specific loop with a `codex_handoff.md` artifact, not a
vague "open a PR" instruction.

**Source:**
- OpenAI Codex: https://openai.com/codex/
- Codex docs: https://platform.openai.com/docs/codex
- ChatGPT Codex Connector app: https://github.com/apps/chatgpt-codex-connector
- Build skills: https://learn.chatgpt.com/docs/build-skills
- Cookbook — agent improvement loop: https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop
- Self-improving Codex skills: https://www.chatprd.ai/how-i-ai/workflows/build-a-self-improving-ai-to-generate-agent-skills-in-codex

## The "connector" concept

The `chatgpt-codex-connector[bot]` is OpenAI's official
GitHub App that links a ChatGPT/Codex account to a GitHub
repo. Once installed, you can:
- Call `@codex review` in a PR comment → Codex reviews the diff
- Have Codex open PRs from Codex Cloud tasks
- Have Codex read AGENTS.md for project-specific rules
- Install Codex Skills that work across ChatGPT and Codex
- Trigger Code mode or Ask mode from any Codex client

**Bot identity (for `Co-authored-by:` trailers and code review attribution):**
```
chatgpt-codex-connector[bot] <199175422+chatgpt-codex-connector[bot]@users.noreply.github.com>
```

The connector is a **GitHub App**, not a CI workflow. It
needs separate installation per repository owner (personal
account + each organization). It does NOT need a GitHub
Actions workflow — Codex runs in OpenAI's cloud sandbox.

## The "4-step install" pattern

Per OpenAI's setup guide:

1. **Create a Codex account** (Pro plan or higher required)
2. **Install `ChatGPT Codex Connector` on GitHub**
   - Open https://github.com/apps/chatgpt-codex-connector/installations/new
   - For multiple owners: install separately per owner (personal + each org)
   - Select repositories: `Only select repositories` is safer than `All repositories` (avoids external contributors triggering `@codex`)
3. **Enable code review in Codex settings**
   - Codex page → right → Cloud → Codex settings
   - "Connect to GitHub" → Authorize
   - "Code review" → enable for the target repo
4. **Enable auto-review on PR open**
   - "Personal auto-review settings" → "On PR open"

For multiple GitHub organizations: use the direct install
URL once per owner:
```
https://github.com/apps/chatgpt-codex-connector/installations/new
```
Keep the same browser session; do NOT use ChatGPT's
Disconnect/Connect buttons (that reconnects the same
identity, not adds a new org).

## The "AGENTS.md" pattern

The connector reads `AGENTS.md` (or `CLAUDE.md`) at the
repo root for project-specific rules. The format is the
same as Claude's:

```markdown
# AGENTS.md — Codex review guidance

## What this repo does
- Self-improving agent for 3 platforms (ZCode, Claude Code, Claude Desktop)
- One shared memory store
- 354-entry knowledge base

## What to focus on in PR review
- New KB entries must follow `documentation/TEMPLATE.md` (slug, date, status, symptom, root cause, fix, verification, gotchas, related)
- Every claim must cite a live URL
- PR title < 60 chars, no "and" (per scope-discipline)
- One concern per PR
- Branch protection: no force-push, no auto-merge

## What to skip
- Skip docs/README formatting (linter handles)
- Skip typo fixes in CHANGELOG (auto-fixable)
- Skip dependency bumps (Dependabot handles)
```

The AGENTS.md can also pass natural-language review
context:
```markdown
@codex review
Please review in Japanese. The PR adds a new KB entry on
Cloudflare MCP — focus on whether the OAuth 2.1 + PKCE
patterns are accurate.
```

## The "@codex review" trigger

The bot reacts to PR comments:
- `@codex review` — review the diff
- `@codex review for security regressions` — focus on security
- `@codex review <additional context>` — natural-language context

The bot replies with the `👀` emoji when it picks up the
task, then posts review comments. It does NOT auto-merge
or auto-push.

## The "Codex Skills" format

Codex Skills follow the same `SKILL.md` + YAML frontmatter
format as Claude Skills. Key differences:

| | Claude Skills | Codex Skills |
|---|---|---|
| **Invocation (auto)** | Description-matched trigger | Description-matched trigger |
| **Invocation (explicit)** | `/skill-name` slash command | `$skill-name` in CLI; `@skill-name` in ChatGPT |
| **Distribution** | `packages/<plugin>/skills/<name>/SKILL.md` | `.codex/plugin/` packaged as plugin |
| **Configuration** | `allowed-tools` in frontmatter | `~/.codex/config.toml` `[[skills.config]]` |
| **Skill-creator** | `github.com/anthropics/skills` (the `skill-creator` skill) | `$skill-creator` bundled skill (also `skill-installer` for adding more) |

The `name` and `description` fields are the same:
- `name`: max 64 chars, kebab-case, gerund form, no reserved words
- `description`: max 1024 chars, third person, "Use when..." prefix, specific trigger phrases, pushy

**The same `SKILL.md` body works in both ecosystems** —
author it once with neutral frontmatter, ship two plugin
manifests (Claude + Codex), and the body is shared.

## The "Codex as self-improving agent" pattern

The OpenAI cookbook's `agent_improvement_loop` notebook
demonstrates the canonical Codex self-improvement loop:

1. **Create synthetic or real task data** — start with traces
2. **Run the agent, capture traces** — every tool call, every decision
3. **Add human + LLM feedback over the traces** — annotate failures
4. **Turn feedback into Promptfoo evals** — codify "what good looks like"
5. **Run a Promptfoo validation gate** — CI check
6. **HALO optimization** — rank the next harness changes
7. **Codex handoff** — write `codex_handoff.md` with proposed changes
8. **Codex implements** — Code mode opens a PR #<number>. **Re-run evals** — close the loop

The pattern: **traces → feedback → evals → harness changes →
Code-handoff → PR → re-eval → repeat**.

The HALO step is the key insight. HALO ranks candidate
harness changes by predicted eval-score improvement.
Without HALO (or an equivalent), the team picks changes by
intuition. With HALO, the picks are data-driven.

**The connector is the "Codex implements" step.** Your
team owns steps 1-6 (trace, feedback, eval, gate, rank,
handoff); Codex owns step 8 (the PR).

## The "codex_handoff.md" pattern

When you're ready for Codex to implement, write a
`codex_handoff.md` artifact:

```markdown
# Codex handoff

## Summary
The 5 eval failures cluster around 2 root causes:
1. The router over-routes hard tasks to ollama (3 failures)
2. The review prompt is too generic (2 failures)

## Recommended harness changes (ranked by HALO)
1. **Raise the hard-keyword list in the classifier**
   - Add: "implement auth", "refactor the model", "redesign the schema"
   - Expected delta: +12% on hard-tier pass rate
2. **Sharpen the review prompt**
   - Add: "Reply with BLOCK, WARN, or OK. One word, then one sentence."
   - Expected delta: +8% on review quality
3. **Skip review for docs-only changes**
   - Add: if changedFiles is all `.md`, skip review (reviewer = OK)
   - Expected delta: +3% on CI speed, 0% on quality

## Files to change
- `packages/router/src/classify.js`
- `packages/fleet/src/reviewer.js`

## Out of scope
- Don't change the model routing chain
- Don't touch the shared-memory format
- Don't add new eval cases (do that in a separate handoff)
```

The connector picks up `codex_handoff.md` from the repo
(or a configured path) and translates it into a Code-mode
task. Codex implements, opens a PR.

## The "self-improving Codex skills" pattern

Codex can generate its own skills — similar to the user's
shipped `distill-lesson` skill, but for Codex's skill format:

1. **Set up a recurring automation** (e.g. weekly Fridays) with the template "From recent PRs and reviews suggest next skills to deepen"
2. **Validate by spawning a sub-agent** with a goal to test the skill against the base branch
3. **Review the sub-agent's report** — did the skill produce high-quality output?
4. **If validated, add to the skill library**
5. **Repeat**

This is structurally the same as your fleet's
`self-improve.js` + `eval-harness.js` loop, applied at the
skill level rather than the routing-rules level.

## The "Codex as code reviewer" pattern

The default use case is PR review:

```bash
# In a PR comment
@codex review
@codex review for security regressions
@codex review in Japanese
@codex review focus on the OAuth 2.1 patterns
```

The connector:
- Reads the diff
- Loads `AGENTS.md` for project rules
- Posts review comments
- Does NOT auto-merge

**Best practice (per OpenAI cookbook):** combine with
human review. Codex is a first-pass reviewer; humans are
the final gate. Codex catches the obvious stuff (typos,
style, missing tests); humans catch the architectural and
business-logic issues.

## The "Codex + MCP" pattern

Codex (and ChatGPT Work) can also install MCP servers as
"connectors." A skill that teaches the agent when to use
the connector, paired with the connector itself, is the
canonical Codex pattern.

```toml
# ~/.codex/config.toml
[[connectors]]
name = "self-improving-agent"
url = "https://self-improving-agent-mcp.<account>.workers.dev/mcp"
auth = "oauth2.1"
```

This is structurally identical to your
`packages/claude-desktop-mcp/` and `packages/mcp-server/`
adapters — same shape, different platform target. The
2026-07-28 MCP spec works uniformly across clients.

## The "connector limitations" pattern

Known limitations in 2026:
- **Private repos via ChatGPT (not Codex):** the connector's OAuth flow for private repos in vanilla ChatGPT (not Codex) has a regression — Codex works, ChatGPT sometimes doesn't. Workaround: connect via Codex directly, not ChatGPT.
- **Each owner needs a separate installation:** personal account + each org = one installation per owner
- **No auto-merge:** the bot does not push or merge; humans decide
- **OAuth scope dependency:** the connector needs `repo` scope on the target repo; install-time permission
- **No silent edits:** Codex PRs go through normal review; no bypass

## The "connector anti-patterns" anti-patterns

### 1. Installing with "All repositories" on a public repo
- **Issue:** External contributors can trigger `@codex review`
- **Fix:** Use "Only select repositories"

### 2. Using ChatGPT Disconnect/Connect to add a new org
- **Issue:** Reconnects the same identity, not adds a new org
- **Fix:** Use the direct install URL `https://github.com/apps/chatgpt-codex-connector/installations/new` once per owner

### 3. Expecting Codex to auto-merge
- **Issue:** It doesn't; humans always gate the merge
- **Fix:** Set expectations: Codex is a first-pass reviewer + implementer, not an autonomous merger

### 4. Writing a vague `codex_handoff.md`
- **Issue:** "Improve the agent" is too broad; Codex wastes hours
- **Fix:** Specific, ranked harness changes with expected eval-score deltas; out-of-scope explicit

### 5. Forgetting AGENTS.md
- **Issue:** Codex reviews without project context
- **Fix:** Write AGENTS.md at the repo root with: what the repo does, what to focus on, what to skip

### 6. Installing skills in the wrong directory
- **Issue:** Codex doesn't see the skill
- **Fix:** Skills go in `~/.codex/skills/<name>/SKILL.md` (user) or `.codex/skills/` (project); plugins go in `.codex/plugin/`

### 7. Relying on the connector for security review
- **Issue:** Codex is a first-pass reviewer; humans are the final gate
- **Fix:** Combine Codex review with mandatory human review for security-sensitive PRs

## The "connector checklist" pattern

For a production Codex integration:
- [ ] Codex account created (Pro or higher)
- [ ] `ChatGPT Codex Connector` installed per GitHub owner
- [ ] Repositories selected (not "All")
- [ ] Codex settings: code review enabled
- [ ] Codex settings: auto-review on PR open
- [ ] AGENTS.md at repo root with project context
- [ ] `@codex review` tested in a small PR
- [ ] Review focus specified (`@codex review for <focus>`)
- [ ] Skills in `~/.codex/skills/` or `.codex/skills/` (not `claude/`)
- [ ] Plugins in `.codex/plugin/` for distribution
- [ ] `codex_handoff.md` template ready
- [ ] HALO optimization (or equivalent) running on every handoff
- [ ] Eval gate (Promptfoo or equivalent) before any handoff
- [ ] Traces captured for every Codex run
- [ ] Human review still required for merge (Codex does not auto-merge)

## Verification
- **Test:** Install connector on a test repo, create a small PR, comment `@codex review`, verify the bot replies with `👀` and posts comments
- **Test:** AGENTS.md change → Codex's next review reflects the new guidance
- **Test:** Codex Skill install → invocation in Codex CLI works
- **Test:** Codex plugin install → available in Codex Cloud + ChatGPT Work
- **Test:** `codex_handoff.md` → Codex implements and opens a PR
- **Audit:** Re-read the connector's setup monthly; OpenAI's toolchain moves fast

## Gotchas
- **The "All repositories" gotcha.** Public repos + All = external contributors trigger reviews.
- **The "Disconnect/Connect" gotcha.** Use the direct install URL for new orgs.
- **The "auto-merge" gotcha.** Codex never auto-merges; humans always gate.
- **The "no AGENTS.md" gotcha.** Without project context, Codex's reviews are generic.
- **The "private repo via ChatGPT" gotcha.** Use Codex, not vanilla ChatGPT, for private repos.
- **The "vague handoff" gotcha.** "Improve the agent" wastes hours; rank specific changes.

## Related
- `patterns/agent-skill-design.md` — the SKILL.md authoring pattern (works for both Claude and Codex)
- `patterns/mcp-server-patterns.md` — the MCP design pattern (Codex consumes MCP servers)
- `cloudflare/mcp-on-workers.md` — the Cloudflare deployment target for an MCP server that Codex/ChatGPT can consume
- `lessons/agent-iteration-discipline.md` — the iteration discipline that the OpenAI cookbook implements
- The shipped `packages/mcp-server/` — your local MCP server, also consumable by Codex
- The shipped `packages/zcode-plugin/skills/` — Claude Skills, the mirror of Codex Skills
- The planned `packages/claude-desktop-mcp/` — Claude Desktop chat-app integration; same shape as Codex connector

**Source URLs (verified 2026-08-09):**
- GitHub App: https://github.com/apps/chatgpt-codex-connector
- Install URL: https://github.com/apps/chatgpt-codex-connector/installations/new
- OpenAI Codex: https://openai.com/codex/
- Codex docs: https://platform.openai.com/docs/codex
- Codex Skills: https://learn.chatgpt.com/docs/build-skills
- Cookbook — agent improvement loop: https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop
- Self-improving Codex skills: https://www.chatprd.ai/how-i-ai/workflows/build-a-self-improving-ai-to-generate-agent-skills-in-codex
- OpenAI community — multiple GitHub accounts: https://community.openai.com/t/connect-a-personal-github-account-and-multiple-organizations-to-chatgpt-codex-and-claude/1387320
- OpenAI community — private repo regression: https://community.openai.com/t/github-connector-connected-but-unusable-for-private-repos-oauth-token-scope-never-applies/1365065
- Tomozumi System — Codex review setup: https://tomozumi-system.com/2026/05/codex-github-review-install/
- Zenn — Codex Cloud PR review: https://zenn.dev/shintaro/articles/164e4a57412e72
- Roompine — ChatGPT GitHub connector: https://roompine.com/chatgpt-github-connector-1/
- BerriAI/self-improving-agent (the npm library, a different but related project): https://github.com/BerriAI/self-improving-agent
- Hermes Agent (Nous Research) — the open-source "self-improving agent" precedent: https://www.youtube.com/watch?v=jmtpYUOr7_U
