# incident-timeline-reconstruction

**Issue:** After every example project incident, the postmortem author spends hours in archaeology: scrolling Slack threads, half-remembered DMs, alert floods, and Git logs to reconstruct what happened in what order. The resulting timeline is subjective, has gaps where decisions were made verbally, and cannot distinguish "the fix deployed at 14:32" from "impact ended at 14:41." A defensible incident timeline — the backbone of every good postmortem — requires that the raw events (alerts, deploys, config changes, human actions, mitigation effects) be captured with timestamps at incident time and correlated afterward, not reconstructed from memory.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Event sources to capture during the incident

1. **Alert lifecycle events, not just alert fires.** For each alert record four timestamps: fired, delivered/paged, acknowledged, resolved. The gaps between them are your detection time and acknowledgment time — the two components of MTTA that `alert-quality-metrics-mtta-mttr.md` tracks — and they come for free from Alertmanager/PagerDuty webhooks if you persist them.
2. **Change events: deploys, config, and infrastructure.** Emit every deploy (commit SHA, service, actor), every config change, and every scaling/infra mutation as timestamped events into a queryable store. The first question of every incident is "what changed," and a change feed answers it in one query instead of three tool UIs.
3. **The response channel, captured programmatically.** Archive the incident Slack channel (or incident tool's timeline) at incident close. Modern incident platforms (Rootly, incident.io, Datadog postmortems) auto-build the human-action timeline from chat, alerts, and status-page updates — the Reddit SRE refrain of "4 hours stitching Slack threads into a postmortem" is the alternative.
4. **Impact telemetry aligned to the same clock.** The SLI time series (error rate, latency, queue depth) with its breach and recovery timestamps defines when user impact started and ended. Keep all sources on UTC and record clock skew if any events originate from devices — a mobile client clock skewed by minutes will misorder the timeline.
5. **Customer-visible actions.** Status page updates, support blast emails, and individual customer notifications are part of the timeline and often contractually significant for SLA reporting.

## Assembling the timeline after the fact

1. **Anchor on impact, then bisect.** Build outward from the two certain points — SLI breach and SLI recovery — placing change events before the breach (candidate causes) and mitigation actions before recovery (candidate fixes). Anything that cannot be placed in either region is context, not cause.
2. **Tag every entry with a source and evidence link.** Each timeline row carries: timestamp (UTC), event type (alert/change/human/impact), actor, a link to the raw evidence (alert permalink, deploy URL, Slack message link), and a confidence note. A postmortem timeline without evidence links is an opinion document.
3. **Separate the three parallel tracks.** Render the timeline as parallel lanes — system events (alerts, SLI), change events (deploys/config), human events (ack, investigation notes, mitigation) — so reviewers can see detection lag and action lag separately. A single merged list hides whether the delay was noticing, diagnosing, or acting.
4. **Distinguish "mitigation applied" from "impact resolved."** Record both timestamps explicitly and treat the delta as data: if the fix deployed at 14:32 but errors persisted to 14:41, either the fix was not the fix, caches drained slowly, or something else resolved it. Postmortems routinely conflate these and therefore claim wrong fixes worked.

## Automating capture so reconstruction is trivial

1. **Declare the incident in-tool as the first action.** Opening the incident (in incident.io, Rootly, PagerDuty, or a `#inc-YYYYMMDD` channel plus a bot) starts structured capture: everything after that marker is auto-attached. Late-declared incidents lose the most valuable early timeline.
2. **Bot-slash commands for human actions in-channel.** `/timeline mitigated rollback on checkout` posted by the responder at the moment of action beats a paragraph typed 90 minutes later. The friction difference is what determines whether the timeline has real timestamps or reconstructed ones.
3. **Pre-correlate alert → incident via the routing key.** When alerts page, tag them with the incident number automatically (grouping keys from `alert-grouping-patterns.md`). Postmortem tooling then pulls the complete alert cascade — including the alerts nobody acknowledged — without manual filtering.
4. **Persist webhooks to an append-only log.** Route Alertmanager, PagerDuty, deploy CI, and status-page webhooks through one collector into an immutable store with received-at timestamps. This becomes the ground truth when a vendor UI's displayed timestamps disagree with what was paged.

## Common reconstruction failure modes

1. **Timezone drift between tools.** Grafana in browser-local time, logs in UTC, PagerDuty in the responder's TZ — merge them naively and deploys appear to happen after their effects. Normalize everything to UTC at write time; convert only at display time.
2. **Alert storms drowning the signal.** A 400-alert cascade makes the timeline unusable; collapse repetitive firings into "alert X fired 400 times over 12m" with first/last timestamps, and keep only state transitions plus distinct alert names in the summary view.
3. **Survivorship bias toward the noisiest channel.** Decisions made in a DM or a call never appear in the Slack-derived timeline. The postmortem template must ask "what was decided outside this channel, and when?" and interview participants to backfill.
4. **Retroactive edits to the narrative.** If the timeline lives in a mutable doc, refine freely but keep the initial auto-captured version archived — the diff between "what we thought at 15:00" and "what we concluded Friday" is exactly the diagnostic-process data a learning review needs.
