# production-readiness-review

**Issue:** Services reach production because the demo worked and the build was green — and the first 2 a.m. page reveals there are no alerts, no runbook, no rollback plan, and no owner listed anywhere. Production readiness reviews (PRRs), formalized in the Google SRE book's engagement model and since productized by service-catalog platforms like Cortex, OpsLevel, and Port, are a structured review a service passes before it is allowed to take real traffic. The practice catches the operational gaps that code review never sees: observability, capacity, incident response, and security posture. The clear 2025-2026 trend is moving PRRs from one-off manual gate meetings toward continuously computed readiness scores in a service catalog, so readiness becomes a living property of the service rather than a certificate issued once and forgotten.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What a review must cover

1. **Architecture and dependencies.** The service's diagram, its upstream and downstream dependencies, and the failure behavior of each. A service whose dependency outage mode is unknown is not ready, however clean its code.
2. **Observability.** Metrics for traffic, errors, latency, and saturation; structured logs; distributed tracing; and dashboards someone other than the author can read during an incident.
3. **SLOs and alerting.** Defined service level objectives with burn-rate alerts wired to a rotation. Readiness means someone is paged when users start suffering, not when the process dies silently.
4. **Incident response artifacts.** A runbook covering the top failure modes, a documented escalation path, an on-call owner, and a rollback or feature-flag kill switch tested within the last quarter.
5. **Security and compliance.** Threat-model notes, secret handling, authentication between services, dependency and license scanning, and data-classification of anything persisted.
6. **Capacity and load behavior.** Known limits under load, tested autoscaling or queueing behavior, and a plan for ten times current traffic — even if the plan is "we know it falls over at 4x, here is the alert."

## Running the review

1. **Use a template, not a conversation.** A standardized checklist (maintained in version control alongside the code) ensures the twelfth review asks the same questions as the first. Freeform reviews drift with the reviewer's mood.
2. **Review before launch traffic, after internal traffic.** Run the PRR while the service is still in staging or behind a flag, when gaps are cheap to fix. Reviewing after general availability is archaeology.
3. **Require a named reviewer outside the team.** A platform or SRE-adjacent reviewer who did not write the service catches the assumptions insiders no longer see. The author reviews their own checklist answers before the meeting.
4. **Score gaps, do not gate perfection.** Classify each unmet item as launch-blocking or follow-up with an owner and date. A review that demands perfection gets bypassed; one that surfaces a prioritized gap list gets used.
5. **Time-box the meeting.** Most verification happens asynchronously against the checklist; the synchronous session covers only blocking items and disagreement.

## Automation and continuous scoring

1. **Move the checklist into a service catalog.** Platforms such as Cortex, OpsLevel, and Port compute readiness scores continuously from repo, CI, and telemetry data, replacing the annual certificate with a live percentage. This is the dominant 2025 pattern.
2. **Encode checks as code where possible.** Alerts exist, runbook file exists and was touched recently, SLO dashboard exists, latest deploy succeeded — these are queryable facts. Automating them removes the honor system from the process.
3. **Report scores publicly.** A leaderboard of readiness scores across services creates benign pressure and, more importantly, a map of organizational risk. Hide it and the debt concentrates in the dark.
4. **Trigger reviews on change, not on calendar.** A major architecture change, new critical dependency, or new data class should re-open the checklist for that service automatically.

## Avoiding common failure modes

1. **Checklist theater.** Boxes ticked with "yes" and no evidence (no dashboard link, no runbook path) are worse than empty boxes because they transfer blame. Require links, not assertions.
2. **One-time certification.** The launch-day review that is never repeated rots within two quarters as the service evolves. Continuous scoring exists precisely to kill this failure mode.
3. **SRE as a bottleneck.** If every review queues behind the one SRE team, teams route around the process. Train reviewers across senior engineers and keep the checklist self-serve.
4. **Scope creep into code style.** The PRR covers operational readiness, not naming conventions or test aesthetics. Let code review own code; the PRR owns the service in production.

## Post-launch follow-through

1. **Convert follow-ups into tracked work.** Every non-blocking gap leaves the review as a ticket with an owner and a due date, reviewed in the next engineering cycle — otherwise the "follow-up" list is where readiness goes to die.
2. **Feed incidents back into the template.** When a postmortem reveals a gap no checklist item would have caught, add the item. The template is a living distillation of the organization's scars.
3. **Re-verify after ownership changes.** Services with new owners inherit stale runbooks and dead escalations. An ownership change in the catalog should flag the service for a lightweight re-check.
