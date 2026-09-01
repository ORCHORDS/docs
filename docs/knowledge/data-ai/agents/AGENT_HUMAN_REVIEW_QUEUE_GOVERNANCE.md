# Human-Review Queue Governance for Agent Actions

## Scope

Human approval is ineffective when reviewers receive ambiguous requests, queues silently age, or the presented action differs from the executed action. This article governs the queue between an agent's proposal and a human decision. It complements approval checkpoints and intent confirmation by focusing on immutable review packages, assignment, expiry, workload, and execution binding.

NIST AI RMF frames human oversight as a contextual risk-management activity rather than a universal guarantee. NIST SP 800-53 supplies separation-of-duties, least-privilege, audit, and access-control objectives. The design below makes review evidence concrete while acknowledging that a human click does not prove a correct outcome.

## Workflow

1. The agent creates a proposed action but cannot execute it. Normalize the target, parameters, expected side effects, data classes, reversibility, and estimated impact.
2. Build an immutable review package with a unique proposal ID, canonical action digest, policy reason for review, relevant source summaries, uncertainty, alternatives, and expiry.
3. Route by risk, domain, tenant, and required reviewer qualifications. Enforce separation of duties where the proposer or operator may not self-approve.
4. Present material facts in a consistent interface. Clearly distinguish agent assertions, retrieved evidence, and policy-generated warnings. Hide neither omitted information nor partial failures.
5. Let the reviewer approve, reject, request changes, or escalate. Approval must identify the exact digest and may add narrower constraints; free-text approval is not executable authority.
6. Before execution, reauthorize the reviewer and proposal, check expiry, verify no material target state changed, and compare the action digest byte-for-byte.
7. Execute once through a fenced operation. Record the outcome separately from the approval decision.
8. Close or requeue according to policy. Any material edit creates a new proposal and review rather than mutating the approved package.

## Controls, data, and evidence

Use role and attribute checks for assignment, not possession of a link. Limit reviewers' tenant and domain scope. Apply queue deadlines, maximum age, escalation paths, vacation coverage, and capacity alerts. Random assignment or conflict-of-interest declarations may be needed for sensitive decisions. Prevent the model from choosing its reviewer.

The review record should contain proposal and action digests, proposer identity, risk class, routing rule, assignee, timestamps, displayed package revision, reviewer decision and constraints, authentication context, execution ID, state-precondition result, and final outcome. Sensitive payloads may remain in the source system behind authorized references. Evidence includes role reviews, queue-aging reports, sampling of decision quality, interface usability tests, separation-of-duty exceptions, and mismatch rejection tests.

## Validation tests

Approve a proposal, then change one parameter, target identifier, or hidden default; execution must fail digest comparison. Let approval expire and confirm no side effect occurs. Revoke the reviewer's role after approval but before execution and apply the documented reauthorization rule. Attempt self-approval and cross-tenant review.

Change target state after review, such as account balance or resource owner, and verify the precondition triggers rereview. Send duplicate execution messages and confirm one fenced action. Flood the queue and verify high-risk work does not silently bypass review or age without escalation. Test keyboard-only and screen-reader workflows for material warnings. Ask for changes and ensure the next proposal has a new ID and preserves linkage to the prior record.

## Failure handling

If the review system is unavailable, hold proposals without execution. A separately designed emergency process may exist, but it must provide equivalent identity, scope, expiry, separation, and evidence rather than a blanket bypass. If displayed evidence cannot be loaded, disable approval and allow only rejection or later review.

When queue age exceeds policy, expire or escalate the proposal; do not infer consent from silence. If an action digest mismatch occurs, reject execution and generate a fresh package. If an unauthorized approval was accepted, fence unexecuted work, assess completed actions, revoke affected credentials, and preserve decision and execution records. Reviewers should be told when execution fails so approval is not mistaken for completion.

## Limitations

Reviewers face fatigue, automation bias, time pressure, and incomplete domain knowledge. More checkpoints can normalize approval rather than improve it. Immutable packages cannot guarantee that summaries are accurate; source access and uncertainty remain important. Separation of duties may be impractical for small teams and requires documented compensating controls. Human review also cannot make an unlawful or technically unsafe action acceptable.

## Canonical sources

- **NIST, AI Risk Management Framework 1.0:** https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- **NIST, AI RMF Generative AI Profile (NIST AI 600-1):** https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- **NIST, SP 800-53 Revision 5:** https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
