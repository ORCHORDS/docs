# GitHub Copilot CLI Usage Metrics (Enterprise, 2026)

## Overview
As of the February 2026 changelog, GitHub expanded Copilot enterprise usage
metrics to include Copilot CLI telemetry. Previously, the enterprise Copilot
usage dashboard surfaced IDE chat, code completion, and (later) coding-agent
sessions but did not capture `gh copilot` CLI usage. With CLI telemetry now
included, enterprise admins get a complete picture of Copilot adoption across
every surface: IDE, github.com, PR review, the coding agent, and now the CLI.

This matters for procurement decisions, seat allocation, and security review:
you cannot govern what you cannot measure, and CLI usage was a blind spot for
teams that do most of their work in the terminal.

## Symptom
- Finance asks "are we actually using all 500 Copilot seats we pay for?" and
  the dashboard shows low IDE usage — but the engineering team runs
  `gh copilot suggest` and `gh copilot explain` constantly in the terminal.
  Without CLI metrics, utilization looks artificially low.
- A team requests more Copilot seats. Their IDE numbers are modest, but you
  suspect heavy CLI use. You cannot confirm or deny without CLI telemetry.
- Security wants to know whether engineers are pasting internal code into
  Copilot CLI prompts. The audit log shows IDE prompt content but not CLI.
- After a billing spike, you cannot attribute usage to a specific tool surface
  because CLI was bucketed under "other".

## Gotchas
- **Telemetry requires opt-in on older CLI versions.** Users on `gh` < the
  version that shipped with the Feb 2026 changelog will not emit enterprise
  metrics even after the feature is enabled org-side. Push a CLI version bump
  via your device-management tooling.
- **GHE (Enterprise Server) lag.** The changelog applies to GitHub.com first;
  GHE Server picks features up on a later release. If you are on GHE, confirm
  the feature flag is actually on before telling leadership the numbers are
  complete.
- **CLI usage is per-invocation, not per-minute.** A single `gh copilot
  suggest` that runs for 30 seconds counts as one event, not 30. Do not
  compare CLI event counts directly with IDE "acceptance rate" metrics.
- **Anonymous/ghost users.** Service accounts and bots that invoke the CLI
  with a token but no enrolled user identity may produce metrics rows that do
  not map to a seat. Filter these out before reporting seat utilization.
- **Privacy mode vs metrics.** Users in "duplicate detection"/privacy
  configurations still generate usage telemetry; privacy mode affects prompt
  content retention, not the existence of a usage row. Be precise in
  communications with employees to avoid the misconception that "opting out
  of training" also hides usage from their employer — it does not.
- **Data residency.** EU-resident orgs should confirm where CLI telemetry
  lands. It may differ from where IDE telemetry is stored.

## Where the Data Lands
- **Enterprise > Settings > Copilot > Usage.** A new "By Surface" breakdown
  now lists: IDE completions, IDE chat, github.com chat, PR review, coding
  agent, and CLI.
- **Audit log API.** CLI invocations appear as
  `copilot_cli_invocation` events queryable via the GraphQL and REST audit-log
  endpoints (`github-audit-log-api.md`).
- **Export.** CSV/JSON export from the usage page includes the CLI column; the
  API requires requesting the expanded projection.

## Querying via API
```bash
# Pull CLI-only Copilot usage for a date range via the audit log API
gh api -X GET /enterprises/{enterprise}/audit-log \
  -f phrase="action:copilot_cli_invocation" \
  -f include=all \
  -f after="$(date -d '7 days ago' +%Y-%m-%dT00:00:00Z)" \
  | jq 'group_by(.actor) | map({user: .[0].actor, count: length})'
```
This gives a per-user CLI invocation count for the last week — useful for
seat-reallocation conversations.

## Reporting Pitfalls
1. **Summing across surfaces double-counts users.** A user who is active in
   both IDE and CLI counts once in each surface; report "active users" by
   distinct user across the union, not by summing per-surface counts.
2. **CLI counts include failed/suggestions-not-accepted.** Do not infer
   productivity from raw counts; pair with the existing acceptance-rate metric
   where available.
3. **Time zones.** The dashboard defaults to UTC; teams in other zones will
   see "low Monday usage" that is actually Sunday-evening activity. Align the
   reporting window with the business day.

## Pairing With Other Metrics
- Combine with `github-copilot-impact-dashboard.md` for adoption vs impact.
- Cross-reference with `github-copilot-coding-agent.md` session counts to see
  the ratio of interactive CLI use vs autonomous agent runs.
- Use alongside `github-audit-log-api.md` patterns to build a single pane.

## Summary
CLI telemetry closing the measurement gap is a quiet but important 2026
change. For terminal-heavy teams it can flip the adoption story from
"underused" to "essential", and it gives security the visibility they have
been asking for since `gh copilot` shipped. Roll out a CLI version bump, then
re-baseline your Copilot reporting.
