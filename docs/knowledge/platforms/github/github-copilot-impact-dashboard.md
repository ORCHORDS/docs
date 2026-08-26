# github-copilot-impact-dashboard

**Issue:** Tracking GitHub Copilot ROI, active-seat usage, code-acceptance rate, and per-model token spend via the Copilot Impact Dashboard (2026 GA with ROI + per-model breakdown)
**Date:** 2026-08-12
**Status:** documented

## Context

Enterprise Copilot contracts cost real money and finance teams ask "what are
we getting for it." The Copilot Impact Dashboard, upgraded in 2026 with a
**return on investment (ROI) section** and **per-model token breakdown** in the
usage report, is the official answer. This KB covers where to find it, what
the metrics actually mean, and the common misreadings.

## Symptom

- Finance asks for Copilot ROI; you have no numbers to give them.
- You can't tell which seats are unused (so you can't reclaim them).
- One team is burning Claude tokens; another barely uses Copilot; you can't
  see the split.
- Acceptance rate looks like 35% but engineers insist Copilot is everywhere —
  the metric definition doesn't match intuition.
- The dashboard shows 0 active users for a team that definitely uses Copilot.

## Where the dashboard lives

Org level: `https://github.com/organizations/<org>/copilot/dashboard`
Enterprise level: `https://github.com/enterprises/<enterprise>/copilot/dashboard`

Requires `owner` or `billing_manager` role, or a custom role with the
`read:enterprise_billing` / `read:org_copilot` permission.

## Metrics and what they actually measure

### Active Copilot users

A user is "active" in a given day if they triggered **any** Copilot completion
acceptance, chat message, or code-review request. Hovering-over-a-suggestion
without accepting does **not** count. This is why engineers feel they "use it
all day" but show as inactive — they're reading suggestions, not accepting.

### Acceptance rate

`acceptances / (acceptances + dismissals)` for inline completions. **Chat
suggestions and code-review comments are NOT in this denominator.** A team
that relies on Copilot Chat heavily will show a low acceptance rate even
though they're getting value. Don't benchmark chat-heavy teams against
completion-heavy teams.

### ROI section (new 2026)

Estimates time saved based on accepted lines × an industry constant, then
converts to dollars using your blended engineering rate (which you set in the
dashboard). The constant is configurable but defaults to GitHub's research
number. Treat the absolute dollar figure as directional, not GAAP.

### Per-model token breakdown (new 2026)

Shows token consumption split by model (e.g., GPT-5, Claude Sonnet, Kimi K3,
MAI-Code-1.1-Flash). This is the report that lets you spot the team that
switched everyone to the most expensive model.

## Configuring the ROI inputs

Settings → Copilot → Impact dashboard:

```yaml
# These are UI fields, not a YAML file — shown as YAML for clarity
blended_hourly_rate_usd: 95          # set to your actual rate
time_per_accepted_line_minutes: 0.5  # GitHub default; tune if you have data
included_models:
  - gpt-5
  - claude-sonnet
  - kimi-k3
reporting_period: monthly            # daily|weekly|monthly
```

## Pulling the data programmatically

```bash
# Org-level Copilot usage metrics (seat usage, acceptance rate)
gh api -X GET orgs/:org/copilot/usage \
  --field since=2026-07-01 \
  --field until=2026-07-31 | jq '.[] | {day, total_active_users, total_engaged_users}'

# Enterprise-level Copilot transaction (per-model token) data
gh api -X GET enterprises/:enterprise/copilot/billing \
  --field since=2026-07-01 \
  --field until=2026-07-31 | jq '.[] | {model, prompt_tokens, completion_tokens, total_cost_usd}'
```

For automated monthly reporting to finance, pipe this into a scheduled
Cloudflare Worker or a nightly GitHub Action.

## Gotchas

- **"Active user" undercounts Chat-heavy teams.** A team that uses Copilot
  Chat 50x a day but accepts no inline completions shows as inactive. Combine
  the seat-usage report with the chat-message-count report (separate API) for
  a truer picture.
- **Acceptance rate is completions-only.** Don't compare it to "did we find
  Copilot useful." Compare it across teams using similar workflows (all
  completion-heavy or all chat-heavy).
- **The ROI dollar figure is sensitive to `blended_hourly_rate_usd`.** Set it
  once, in writing, with finance. Otherwise every report will be argued about.
- **The per-model breakdown arrives ~48 hours late.** Don't expect same-day
  token totals for cost-control alerts; budget on a 2-day lag.
- **Enterprise-managed settings suppress per-repo overrides.** If your
  enterprise has pinned everyone to one model via managed settings, the
  per-model report will show 100% one model — not a bug, the policy worked.
  See `github-mcp-allowlists-enterprise-managed-settings.md` for the related
  controls.
- **Inactive seats are billed.** Copilot doesn't auto-reclaim unused seats.
  Use the dashboard's "no activity in 30 days" filter monthly to find seats to
  revoke.
- **Code-review tokens are billed under the requester, not the PR author.**
  If one reviewer requests Copilot review on 100 PRs, their seat looks
  expensive. Don't blame the PR authors.
- **The dashboard only covers Copilot, not other AI tools.** If your team also
  uses Cursor or an in-house LLM, the "we saved $X" number is Copilot-only and
  will overstate total AI ROI if reported as company-wide.

## Diagnostic checklist

- [ ] Confirm reporting role has read access (`owner` / `billing_manager`).
- [ ] Confirm `blended_hourly_rate_usd` is set and matches finance's number.
- [ ] Pull both the seat-usage AND chat-message reports before judging a team
      "inactive."
- [ ] Schedule a monthly export so you can show finance a trend, not a
      one-shot.
- [ ] Cross-check per-model token totals against the billing invoice; they
      should match within the 48-hour lag.

## References

- Changelog: "Copilot impact dashboard adds a return on investment section"
  (2026)
- Changelog: "Per-model token breakdown in the usage report" (2026)
- API: `GET /orgs/{org}/copilot/usage`, `GET /enterprises/{enterprise}/copilot/billing`
- Related KB: `github-copilot-coding-agent.md`,
  `github-copilot-code-review-effort-levels.md`
