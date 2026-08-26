# config-deploy-blast-radius-2026

> The 2025 Cloudflare Nov 18 outage (and a dozen smaller ones since) taught
> the industry that a config push is a deploy, and config deploys need the
> same blast-radius controls as code deploys — canary, rollback, and a
> kill switch that isn't the same button that broke it.

## Symptom

A team ships a new WAF / bot-management / routing config to global edge at
17:00 on a Tuesday. The config was reviewed in a YAML diff, looked correct,
and was pushed via the provider's "publish" button. Within 90 seconds, error
rates across three customer-facing properties climb from 0.1% to 62%. The
config had a subtle interaction with a path-rewrite rule that only triggered
on requests carrying a specific cookie — a shape that existed in ~30% of
production traffic but in none of the team's synthetic tests.

Rollback was technically possible (the previous config version was retained),
but the "publish" and "revert" actions lived behind the same privileged
console, which was now being hammered by every team checking "is that us?"
The revert landed 47 minutes after the publish. Customer-visible impact:
~47 minutes of degraded traffic, one lost enterprise deal in flight.

The root cause in the postmortem was not the bad rule. It was: **"a global
config change was treated as a low-risk edit because it didn't require a
build, and therefore bypassed every safety gate we built for code."**

## Gotchas

- **"It's just config, it can't be that bad" is the most expensive sentence
  in platform engineering.** Config changes touch the same runtime as code
  but are routinely shipped without CI, without canary, and without a
  reviewer who didn't write them. The 2025 edge-provider outages were almost
  all config, not code. Treat every config push as a production deploy with
  the same weight as a service release.

- **Global config has no natural canary.** A code deploy can be pinned to
  one region or one pod. A WAF rule or a routing table is usually applied
  globally and atomically. If your provider doesn't support staged/partial
  config rollout, you have to fake it: deploy to a low-traffic shadow
  property first, watch error rates for 10 minutes, then promote. "We can't
  canary this" is not an acceptable answer for anything customer-facing.

- **The revert button must not share an auth path with the deploy button.**
  When the console is the only way to ship *and* to roll back, an incident
  that floods the console also disables your recovery. Keep a documented,
  separately-authenticated rollback path (CLI with stored creds, or an API
  token in a sealed secret). Practice using it before you need it.

- **Config tests must exercise real traffic shapes, not happy paths.** The
  bad rule above passed every unit test because tests used clean requests.
  Replay-based testing — feeding a sample of real (PII-scrubbed) production
  requests through the candidate config — catches the interaction bugs that
  hand-written tests cannot. If you can't replay real traffic, at minimum
  run the candidate config in "log only" / "dry run" mode for a full day
  before enforcing it.

- **Reviews of YAML diffs are weaker than reviewers think.** A 6-line config
  diff looks reviewable; the reviewer approves it in 90 seconds. But those
  6 lines can interact with 400 other rules the reviewer isn't holding in
  their head. Pair config review with an automated impact report: "these N
  rules will change behavior for these M request patterns, here are
  examples." Make the reviewer react to examples, not to syntax.

- **Blast radius is proportional to the scope of the thing the config
  controls.** A per-service config change is a contained fire. A shared
  platform config change (edge routing, auth policy, TLS) is a forest fire
  waiting for a spark. Add an explicit "scope: shared-platform" tag to
  shared configs and require two-person approval plus a change-window for
  anything carrying it.

- **Time-of-day matters more than you think.** The 17:00 push above meant
  the incident peaked after business hours, when the people who understood
  the rule interaction were already off clock. Default config pushes for
  mid-morning local time on a weekday. Never ship a shared-platform config
  change on a Friday afternoon, before a holiday, or during an on-call
  handoff window.

- **Feature-flag the config itself when possible.** If the config system
  supports a flag (e.g., "this rule is active but in observe mode"), use it
  for any non-trivial change. Observe-only for 24 hours, then enforce. The
  cost is a one-day delay; the benefit is not appearing in a postmortem.

## What to do instead

1. Inventory every place config is shipped without a code deploy. That list
   is your real risk surface.
2. For each, define: canary strategy, rollback path (separate from deploy),
   required reviewers, and an allowed time window.
3. Run a quarterly game day that pushes a deliberately-bad config and
   measures time-to-detect and time-to-revert. If either exceeds 15 minutes,
   the controls are insufficient.
