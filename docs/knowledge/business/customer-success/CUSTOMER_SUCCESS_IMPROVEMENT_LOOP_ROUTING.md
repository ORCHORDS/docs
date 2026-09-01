# Customer Success Improvement Loop Routing

An information bank full of diagnosis — recurring friction themes, root-cause findings from complaint analysis, patterned gaps surfaced in voice-of-customer review — creates value only when it changes the product or the service. Unrouted findings rot in quarterly reviews; routed-but-unowned findings die in a backlog nobody watches; closed-without-evidence findings teach the organization that escalation is theater. This article governs the routing of information-bank findings into product change: triage classification, ownership assignment, and the closure evidence required before a finding may be marked resolved.

## Scope

Applies to findings that emerge from customer-success information banks — complaint root-cause analyses, escalation patterns, adoption friction logs, survey themes, support case clusters — and are candidates for product or service change. Covers the route from confirmed finding to disposition and verified closure. Does not cover the root-cause analysis itself (its own methodology), individual case resolution, or emergency incident handling, which follows incident procedure and may only later submit its findings into this loop. Where a finding alleges a compliance, safety, or security defect, it routes to the corresponding authority immediately and this article's loop handles the recurrence-prevention track in parallel.

## Workflow or implementation guidance

1. **Confirm the finding before routing.** A finding enters the loop only with a stated pattern, the evidence base (how many cases, what period, which segments), and a screening against known duplicates and already-open items. Anecdote-shaped submissions are returned for evidence, not routed onward on enthusiasm.
2. **Triage on impact and recurrence, not volume alone.** Classify by customer harm severity, recurrence rate, breadth across segments, and strategic weight. A low-frequency, high-harm finding outranks a high-frequency annoyance; the matrix makes these comparisons explicit instead of rhetorical.
3. **Assign a single accountable owner.** Every accepted finding gets one named owner in the receiving product or service area. Shared ownership is refused at intake; "the platform team" is not an owner, a person is.
4. **Record the receiving queue's disposition obligation.** The owning area commits to a disposition decision — fix, mitigate, accept with rationale, or decline with rationale — within a defined window scaled to severity. Declining is legitimate and recorded; slow-fading is not.
5. **Link every disposition to its evidence trail.** A fix disposition links to the change record, release, or policy amendment that implements it. A mitigation links to the interim control and its owner. An acceptance or decline links to the written rationale the customer-success side can see and, where appropriate, relay.
6. **Define closure evidence before closure.** Closure requires the loop's own verification: after the change ships, does the pattern in the information bank actually stop? Closure evidence is a post-change measurement over a defined window — recurrence count, theme frequency in new cases, or the affected accounts' friction signals — compared against the pre-change baseline.
7. **Handle non-closure honestly.** When the change ships but the pattern persists, the finding reopens with a fresh root-cause pass rather than being closed on activity. Two consecutive ineffective fixes trigger an escalation review of the problem's framing itself.
8. **Feed the loop metrics upward.** Publish routing volumes, disposition mix, time-to-disposition, closure-verification pass rate, and reopen rate. These metrics are the loop's health; volumes without outcomes are vanity.

## Controls

- Findings cannot be closed by the team that would have to do the work without second-party review of the closure evidence.
- Severity classification uses a published rubric; ad-hoc downgrades to escape service windows require escalation-lead approval.
- The customer-facing commitments made during routing ("this will be addressed") are captured in the commitments register with due dates, because a routing promise is a promise.
- Duplicate suppression runs at intake and again at disposition, so two teams do not independently "fix" one finding while believing they each solved something.
- Access to raw case narratives inside the routing record follows the information-bank privacy rules; routing artifacts carry themes and counts, with minimal excerpting.

## Validation evidence

A functioning loop shows: intake records with evidence base and duplicate screening; the triage classification with rubric reference; named owners with disposition due dates; disposition records with linked change or rationale artifacts; and — the distinguishing evidence — closure verification measurements showing post-change pattern data against baseline for a sample of closed findings. Reopen records with their re-analysis demonstrate the loop's integrity under failure. Quarterly, sample five closures and attempt to reproduce their verification numbers from the information bank directly.

## Failure modes and correction

- **Routing into a void** (findings accepted, nothing dispositioned): the time-to-disposition metric breaches its floor; escalation to the owning area's leadership is automatic, not discretionary.
- **Activity closure** (marked resolved when a change shipped, no recurrence check): reopen with the closure-evidence requirement applied retroactively; count in the pass-rate metric.
- **Owner churn orphaning findings** (the named owner leaves): ownership reassignment is part of offboarding workflow; orphan scan runs monthly and reassigns with notification.
- **Severity gaming** (mass down-classification to clear the queue): rubric-audit samples classifications; discrepancies are corrected and counted against the queue's process score.

## Limitations

The loop depends on the receiving area's genuine capacity; governance can force honest disposition, not infinite engineering throughput, and the accept-with-rationale path exists precisely for that boundary. Findings grounded in misdiagnosis will route perfectly toward the wrong fix, so the loop's quality is bounded by upstream root-cause quality. Very long-lead changes make closure windows impractical, and those items are tracked as open-with-milestone rather than falsely closed.

## Canonical sources

- [ISO 9001 Quality management](https://www.iso.org/iso-9001-quality-management.html) — corrective action, effectiveness verification, and records discipline.
- [NIST SP 800-61 Rev. 2, Computer Security Incident Handling Guide](https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final) — follow-up, lessons-learned, and verification structure for recurring-problem handling.

Local procedures should track the edition in force and be reviewed when the authority replaces it.
