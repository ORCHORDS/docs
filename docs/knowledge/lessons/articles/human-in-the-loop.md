# human-in-the-loop

- **Issue**: An agent that never asks is a footgun. An agent that asks for everything is unusable. The 2026 production pattern is a four-tier risk classification with three HITL modes, and the load-bearing rule is **the agent that reasons never holds write credentials**.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/lessons/agent-iteration-discipline.md` and `documentation/docs/policies/lessons/when-to-ask-vs-push.md`.

## Symptom

- Agent sends the email, charges the card, or merges the PR before the user noticed anything was wrong. The "confirmation" was a log line.
- The agent asks permission for every read, every step, every turn. Users mute it.
- Two agents in a pipeline pass an approval token that turns out to be forgeable or replayable. The audit log says approved; the incident says otherwise.
- A reviewer was supposed to approve an irreversible action, but the approval flow was the same UI as a non-reversible one, with the same single click. No dual control.

## Root cause

The mistake is treating "human-in-the-loop" as a single checkbox. It is three placements, three modes, and four tiers, plus a non-negotiable trust boundary between the agent and the executor.

## The four-tier risk classification (production 2026)

| Tier | Risk | Mode | Examples |
|---|---|---|---|
| **T1** Read-only | None | No approval | DB queries, calendar reads, file reads |
| **T2** Reversible writes | Low | Autonomous with logging | Draft creation, internal state changes, email labeling |
| **T3** External / third-party | Medium | Staging queue or confidence gating | Outbound API calls, ticket creation, non-final PR comments |
| **T4** High-risk / irreversible | High | **Mandatory human approval, no exceptions** | Production deploys, money movement, data deletion, privilege changes, external sends |

The five canonical "always demand approval" actions, agreed across the 2026 vendor consensus: deploying to production, sending external communications, financial transactions above a configurable threshold (default $100), deleting data, changing privileges.

## The three HITL modes

- **Blocking (in-the-loop)** — agent pauses mid-execution and waits. Use for T4. The cost of a wrong action is higher than the cost of making the agent wait.
- **Post-processing (draft review)** — agent generates output; a human reviews before finalization. Use for content creation, report generation, any "draft" workflow. Agent does not pause; human reviews async.
- **Deferred (async feedback)** — agent completes the task; feedback is collected later. Use for low-stakes actions where speed matters: opening a PR, triaging tickets, suggesting a refactor.

The guiding question per tool: **what is the cost of the agent getting this wrong, and what is the cost of making a human wait?** The ratio picks the mode.

## The load-bearing rule: separate reasoning from execution

Proposing, approving, and executing are **three different processes with three different privilege levels**. The agent that reasons never holds cloud or cluster write credentials. The executor that holds credentials never talks to the LLM. The approval sits between them as a signed handoff. **Draw that boundary wrong and the approval becomes theatre.**

## The four control-loop patterns (2026 consensus)

1. **Scoped authority before approval** — narrow the possible action space *before* asking the human to approve anything. Temporary AWS credentials, Stripe restricted keys, OAuth Rich Authorization Requests. The request is "do this kind of action on this resource for this limited period," not "do anything."
2. **Approval leases instead of permanent permission** — a short-lived capability issued after consent, valid only for a specific operation or narrow action set. If the action is delayed, retried, or mutated into something broader, the lease no longer applies.
3. **Dual control for irreversible actions** — the proposer cannot be sole approver; production deploys require a second principal; destructive actions require elevated approval class. GitHub deployment reviewers and AWS approval chains are the reference pattern.
4. **Receipts and auditability** — log who proposed, what context, who approved, what lease was issued, what the tool actually executed, what outcome came back, whether execution matched the approved scope.

## The five fields in a typed approval object

1. **action type** — the kind of side effect
2. **target resource** — exact URI / id / scope
3. **allowed side effects** — what may change as a result
4. **expiration time** — lease timeout (default: 7 days for ordinary, 24 hours for sensitive)
5. **max use count** — and the delegating principal

Plus: optional second approver, idempotency key, hash of the proposed action.

## Async-first is the production default

Synchronous approval collides with gateway timeouts, token expiry, and stale cursors. The pattern that survives real infrastructure is **durable, state-managed interruption with idempotency keys**:

1. Generate an idempotency key *before* the interruption; persist it in state.
2. Store a hash of the proposed action at interrupt time.
3. The agent serializes its state to a checkpoint; the request enters a queue with a TTL.
4. Execution resumes from the checkpoint only after a human responds — no re-running from scratch.
5. On execution, re-verify the token, re-validate the action against the allowlist, and re-hash the proposed action. If the underlying data drifted while approval was pending, the hashes diverge and you refuse to execute a stale decision.

Recommended defaults: **7-day TTL for ordinary operations, 24 hours for sensitive ones**.

## The minimum context package for an approval notification

- The action in plain language
- The agent's reasoning
- Estimated financial impact
- Reversibility flag
- Alternative approaches the agent evaluated
- A diff of before-and-after field values (not raw payloads)
- Impacted row counts / dollar amounts
- Session ID for audit correlation
- Approval deadline timestamp
- A "reject with edits" path (not binary yes/no)

## Approval data is operational data

- **Monitor gate exercise rates** per tool. A tool that goes from 20 approvals/week to zero didn't become unnecessary; routing changed.
- **Constrain the supervisor's tool access**. If the supervisor shouldn't send emails directly, don't give it email tools. Force the delegation path through the agent that has the gates.
- **Audit traces for governance bypasses**. Verify high-risk actions flow through the gated paths.
- **Schedule a monthly approval data review**. Approval rates and modification patterns tell you which gates to relax and which agent instructions to tighten.

## Verification

- **Forged token test** — fixture a forged token; assert `verify_token` rejects it.
- **Expired token test** — fixture an expired token; assert rejection.
- **Replayed token test** — fixture a replayed token; assert rejection.
- **Non-allowlisted action test** — fixture an action targeting a non-allowlisted namespace; assert the executor refuses.
- **Hash-drift test** — change the underlying resource between approval and execution; assert the hash check fails and execution is refused.
- **Exercise rate per tool** — weekly dashboard; alert on any tool that drops to zero.
- **For every T4 action, verify** the proposer ≠ approver (dual control).

## Gotchas

- **A confirmation dialog is not HITL.** It is a UI element. HITL means the action does not execute until a separate, authenticated, audited approval has been recorded.
- **Same-process approval is theatre.** If the agent that proposes is the same binary as the executor, the approval cannot be enforced; the agent can simply skip it. The boundary must be a process boundary, with the credentials held by a different process.
- **Approvals without leases are standing authority.** Standing authority in agent systems is dangerous because context can shift after the permission was granted.
- **Approvals without scope are too broad; scope without approval is too permissive; both without logs are not auditable.**
- **Synchronous approval at gateway timeouts is a 504.** Use durable queues with TTL.
- **"Reject with edits" must be a real path, not a no-op.** A binary yes/no forces a re-proposal loop that wastes tokens and time.
- **Don't gate reads.** Confirmation fatigue kills more agents than missing approvals do.
- **An audit log is not a receipt.** A receipt binds proposal + approval + lease + execution + outcome into one verifiable record. A log line per event is not the same.
- **Dual control must be enforced by the runtime**, not by social convention. A single user with two roles can satisfy social dual control and bypass it.

## Related

- `documentation/docs/policies/lessons/agent-iteration-discipline.md` — the "when to stop" rule that HITL overrides
- `documentation/docs/policies/lessons/when-to-ask-vs-push.md` — when asking is the right move
- `documentation/docs/policies/lessons/agent-self-correction.md` — what the agent does *before* escalation
- `documentation/docs/policies/security/ai-agent-security.md` — Tool-Input/Output firewalls and Rule of Two complement HITL
- `documentation/docs/policies/patterns/multi-agent-orchestration.md` — where the approval boundaries sit in a multi-agent system
- `documentation/docs/policies/cloudflare/sandbox-2026.md` — secure credential injection via egress proxy is one implementation of "the agent that reasons never holds write credentials"

## Source URLs (verified 2026-08-09)

- "Human-in-the-Loop Authorization for AI Agents" (agenticwire) — https://www.agenticwire.news/article/agent-ux-design-patterns
- "Human-in-the-Loop Approval Gates for DevOps AI Agents" (devtocash) — https://devtocash.com/blog/2026-07-27-human-in-the-loop-approval-gates-devops-ai-agents
- "Human-in-the-Loop Agent Approvals: A Mastra Pattern" (Galarza) — https://www.damiangalarza.com/posts/2026-05-27-human-in-the-loop-agent-approvals-a-mastra-pattern/
- "Approval, Consent, and Control Loops for AI Agents" (zylos) — https://zylos.ai/en/research/2026-03-26-approval-consent-control-loops-ai-agents/
- "Human-in-the-Loop Escalation Design for AI Agents 2026" (digitalapplied) — https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026
