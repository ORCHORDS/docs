# Agent Human Handoff Authentication

## Scope

This article covers authentication and authorization when an agent hands off a task to a human reviewer. The handoff is the moment when an automated workflow transfers a decision, an action, or a task to a person; that moment is also when many of the security properties of the automated workflow must be re-established under human control. The article covers identity binding, scope transfer, audit continuity, replay protection, and the lifecycle of the credentials used during the handoff.

Out of scope: the broader question of who is authorized to review which kinds of agent decisions, which is a policy question for the deploying organization, and the human-review-queue governance article in this family covers queue mechanics. This article addresses the cryptographic and protocol aspects of authentication at the boundary.

## Implementation workflow

Generate a dedicated handoff credential at the moment of handoff. The credential is short-lived, narrowly scoped, and bound to a specific (task_identity, reviewer_identity, intent) triple. The credential is delivered to the reviewer through an out-of-band channel that the agent has verified as belonging to the reviewer; for example, a push notification with a one-time code that the reviewer redeems through an authenticated web session. The credential itself is not the same credential the agent used; the agent's credentials remain under agent control and are not transferred.

The handoff credential carries a precise scope description. The scope enumerates the actions the reviewer may take on behalf of the agent: approve, reject, request more information, or escalate. It excludes any action the reviewer does not need. If the reviewer must invoke a tool to gather information, the credential carries a tool-call scope that is itself short-lived and rate-limited. The OAuth 2.0 authorization framework, RFC 6749, and the resource indicator extension, RFC 8707, give a vocabulary for these scopes.

The handoff record carries an evidence packet. The packet contains the task identity, the explanation summary (per the explainability summaries article), the relevant input data, the agent's pending decision, the deadline by which the reviewer must act, and the consequences of inaction. The packet is signed by the agent's workload identity and is the reviewer's primary reference during the handoff. The packet's integrity is preserved by signing the packet itself with a key bound to the agent's SPIFFE workload identity.

The reviewer authenticates using their own credentials and redeems the handoff credential. The two credentials are joined at the moment of redemption: the handoff credential's (task_identity, reviewer_identity, intent) must match the reviewer's authenticated session and the agent's signed evidence packet. Any mismatch fails closed. This binding prevents a leaked handoff credential from being redeemed by a different reviewer, and prevents a reviewer from applying a handoff credential to a different task.

The reviewer's decision is signed under the reviewer's own identity and delivered back to the agent through an authenticated channel. The agent verifies the signature, the reviewer's authentication freshness, the binding to the original task identity, and the absence of tampering. The decision is then applied to the task under the same audit trail as the rest of the agent's work.

Replay protection follows established patterns. The handoff credential carries a single-use redemption marker; once redeemed, the marker is invalidated. The reviewer's decision carries a nonce that the agent tracks for the duration of the handoff window; replayed decisions are rejected.

## Controls

Handoff credentials expire aggressively. The default expiration is on the order of minutes, not hours. The expiration must be shorter than the time an attacker would need to phish, steal, or otherwise compromise the credential; this is the same discipline as for password reset tokens in RFC 8628 (device authorization grant).

Multi-party authorization for high-blast-radius actions. When the handoff involves an irreversible action (for example, sending a message to an external party, modifying a customer record, or triggering a financial transaction), the handoff credential scope requires two reviewers. The second reviewer authenticates independently and signs the decision; both signatures are required for the action to proceed. The threshold is configurable but defaults to two for any action classified as high-blast-radius.

Audit continuity. The handoff record, the reviewer's redemption event, and the reviewer's decision are all part of the same audit trail. The agent does not permit a handoff to proceed without an intact audit chain; if any link is missing, the handoff is treated as unauthenticated. The OpenTelemetry audit log correlation ID article in this family describes the broader correlation discipline.

Privacy during handoff. The handoff packet must apply data minimization. The reviewer sees only what is necessary for their decision; sensitive fields not relevant to the decision are redacted or replaced with opaque references. The W3C Trace Context security guidance and the OWASP logging privacy cheat sheet both inform this practice.

## Validation evidence

Conformance tests must cover: credential issuance at handoff time, redemption with matching identity, redemption rejection when the reviewer's session does not match the handoff intent, expired credential rejection, replay rejection after redemption, multi-party authorization flow for high-blast-radius actions, audit chain integrity, and redaction of sensitive fields by default. Inject a stolen handoff credential, a replayed decision, a mismatched reviewer, and a missing audit link and verify each is rejected.

Operational evidence includes: count of handoffs per task, distribution of time-to-review, redemption rate (how often a credential is actually used), count of credentials expired without redemption, count of multi-party authorizations invoked, and count of replay attacks rejected. Reviewers' feedback on the quality of the evidence packet is also an evidence input.

## Failure handling

When the reviewer's authentication cannot be verified (for example, when the identity provider is unavailable), the agent treats the handoff as in progress and extends the deadline once. Further extensions require operator intervention. The agent does not silently proceed without a valid reviewer's decision.

When the handoff credential is lost, expired, or compromised, the agent issues a new credential only after re-authenticating the reviewer and revoking the old credential. The revocation is recorded in the audit trail. The reviewer cannot reuse the old credential to claim continuity of session.

When the audit chain is broken (for example, when the handoff record was not properly persisted before redemption), the agent refuses to accept the reviewer's decision and re-issues the handoff with a fresh credential. The break is itself an audit event that triggers an operator review.

When the reviewer cannot complete the review within the deadline, the task is escalated per the escalation policy. The escalation policy article in this family describes the broader discipline; specifically, deadline-driven escalation must be clearly communicated to the reviewer at handoff time so that the deadline is not a surprise.

## Canonical sources

- RFC 6749, The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 8628, OAuth 2.0 Device Authorization Grant: https://www.rfc-editor.org/rfc/rfc8628
- RFC 8707, Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
- NIST SP 800-63B, Digital Identity Guidelines — Authentication and Lifecycle Management: https://pages.nist.gov/800-63-3/sp800-63b.html
