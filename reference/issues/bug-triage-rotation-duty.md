# bug-triage-rotation-duty

**Issue:** Bug triage — classifying, labeling, and routing new issue reports — is continuous, low-glamour work that defaults to whoever is most conscientious or least able to say no. Without a formal duty rotation, the predictable failures follow: triage happens in bursts when the backlog becomes alarming, one or two engineers accumulate the unwritten role and burn out (a documented driver of maintainer attrition in large open-source projects), and classification quality oscillates because every triager applies a private standard. A rotation distributes the duty fairly, makes intake latency predictable, and — because each engineer periodically works the intake queue — spreads system knowledge across the team. This article covers designing the rotation, the duty holder's checklist, and keeping the duty sustainable. It complements triage-priority-matrix (how to classify) and labeling-taxonomy-design (what labels mean); the subject here is the human rota itself.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why a rotation beats ad-hoc triage

1. **It makes intake latency a contract, not a hope.** With a named duty holder per interval, "new bugs triaged within 24-48 hours" becomes checkable, and time-to-triage becomes a metric instead of a wish. Ad-hoc triage produces unbounded queues between bursts.
2. **It prevents silent knowledge concentration.** The Kubernetes project distributes issue triage across SIGs with published guidelines precisely so that context about incoming reports lives in the group, not in one person's head. A rotation is the single-team version of the same defense.
3. **It is burnout insurance.** On-call research (Datadog, incident.io) consistently recommends rotations sized so no one serves more than about once a month; continuous unrotated triage violates that principle and is a recurring theme in maintainer-burnout reporting.
4. **Every engineer becomes a better reporter.** Working intake exposes each engineer to how bad reports read from the receiving side, which measurably improves the team's own bug-report quality — a compounding benefit beyond the triage itself.

## Designing the rotation

1. **Pick a shift length that matches intake volume.** Weekly shifts suit most product teams; high-volume open-source trackers use daily or follow-the-sun shifts across regions. The test is that one shift's intake is triageable within a bounded daily time budget, roughly an hour or two.
2. **Staff a primary and a backup.** The primary owns the queue; the backup covers leave, incidents, and overloaded weeks and is the escalation target for disputed classifications. The primary/secondary pattern from on-call scheduling maps directly.
3. **Size the pool for fairness and competence.** Rotations of six to eight people keep duty infrequent while preserving skill continuity; smaller pools over-serve, larger pools let triage skills decay between turns. Include senior engineers — triage judgment is where seniority pays off cheapest — and onboard juniors by pairing their first shift with the previous holder.
4. **Publish the roster and automate the handoff reminder.** A visible schedule (calendar or tracker integration) plus an automated shift-start notification removes the "who is on triage this week" chat question and the missed-handoff failure it causes.
5. **Write the runbook once.** The triage runbook — classification rules, label definitions, assignment routing, and the do-not-decide list — is the artifact that makes every triager interchangeable. Without it, the rotation rotates people into improvisation.

## The duty holder's checklist

1. **Sweep the queue on a fixed cadence.** Once or twice daily, process every new issue: read it, reproduce or sanity-check where cheap, then classify. The cadence is the SLA; deferring the whole week's queue to Friday violates it.
2. **Apply the four-way outcome promptly.** Every new issue gets one of: accepted and routed (labels plus assignee or owning queue), returned for information (needs-repro steps and the specific missing data), closed (duplicate, working-as-intended, or declined per the wontfix policy), or parked for a group decision. Nothing leaves the shift unclassified.
3. **Protect the reporter relationship.** First response is customer-facing work: acknowledge, ask precisely what is missing, and link duplicates to their originals. Rude or lazy first responses suppress future high-quality reports.
4. **Escalate the scary ones immediately.** Suspected security issues, data-loss symptoms, and availability-threatening regressions bypass the queue and page the on-call or security channel per the escalation policy; the duty holder's job is recognition and routing, not solo diagnosis.
5. **Record what the runbook does not cover.** Novel or ambiguous classifications go to a shared list for the weekly triage review, which either answers the case or amends the runbook. This loop is what keeps the runbook alive.

## Handoffs between shifts

1. **End the shift with a written handoff note.** Items still awaiting reporter replies, disputed classifications, and anything partially investigated get a two-line entry each: state, next action, owner. The incoming triager reads this before touching the queue.
2. **Hand off open loops, not just the queue.** The outgoing holder's obligations — promised follow-ups to reporters, pending questions to other teams — transfer explicitly. Untransferred promises are the main source of reporter-facing silence across shift boundaries.
3. **Do a short overlap or asynchronous debrief.** Even fifteen minutes of overlap, or a written debrief the successor responds to, catches classification disagreements while both holders have context, before inconsistent labels accumulate.
4. **Reset the queue at shift boundaries where practical.** Aim for inbox-zero on classifiable items at handoff; a permanently half-triaged queue handed onward conceals latency and makes the next holder's SLA unmeasurable from the start.

## Keeping it sustainable

1. **Budget triage as real work.** The duty holder's feature workload is reduced during their shift; pretending triage is free guarantees it gets squeezed out under deadline pressure and the queue silently grows.
2. **Track time-to-triage and queue age as the duty's health metrics.** Rising time-to-triage means the shift or cadence is undersized; growing median queue age means classification outcomes are leaking (issues parked without decisions).
3. **Rotate the rotation's management.** The roster, runbook, and review meeting themselves need an owner; hand that meta-duty over periodically so the rotation does not recreate the single-point dependency it exists to remove.
4. **Review classifications weekly and prune the taxonomy.** A brief weekly review of disputed or reversed labels feeds the labeling taxonomy; labels that are never used or always confused get merged or killed, keeping the classification system as lean as the duty that applies it.
