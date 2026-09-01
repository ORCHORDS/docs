# Agent Identity Propagation Across Hops

An agent rarely works alone: it calls a sub-agent, that sub-agent queries an MCP server, the MCP server calls a third-party API, and somewhere down the chain a decision gets made and data gets returned. If each hop authenticates as itself, the chain ends up authorized as its most privileged link, and no single system can answer "who caused this." Identity propagation carries the original authenticated principal, and the causality chain, across every hop, so each participant can authorize on whose behalf it acts and auditors can reconstruct the whole path. This article covers token strategies, causality fields, hop-by-hop rules, and the failure modes that quietly break both.

## Scope

Applies to multi-agent and multi-service chains where an action originates with an authenticated principal (a user or a workload) and flows through intermediaries: orchestrator to sub-agent, agent to MCP or A2A server, server to downstream API. Covers delegation token patterns, identity assertion hygiene, causality and correlation propagation, and end-to-end verification. Does not cover the mechanics of any one framework's authorization model, key management for signing, or audit-log normalization.

## Workflow or implementation guidance

1. Establish the origin identity once, strongly. The first hop authenticates the principal with a real credential: user session, workload identity, or mTLS client identity. Everything downstream receives that identity only as a delegated, signed statement, never as a bare unauthenticated header someone typed.
2. Choose the delegation pattern per hop and record it. Common options: OAuth token exchange (RFC 8693), where the intermediary presents its own credentials plus the subject token and receives a narrower downstream token; JWT assertion forwarding, where a signed token carries the original subject plus the actor claim; or platform-trusted identity headers behind mutual TLS. The invariant in all of them: the assertion is signed or mTLS-protected by the hop that stands behind it, and the audience is the specific downstream, not "anyone who sees it."
3. Never forward the original credential verbatim. Passing the user's access token to a downstream server hands over every scope the principal had, lets the downstream impersonate the principal elsewhere, and makes revocation propagation impossible to reason about. Exchange, narrow, and audience-bind instead.
4. Assert the actor alongside the subject. Downstream authorization usually needs two facts: on whose behalf (subject) and through what chain (actor). A token that says only "acting as alice" without saying "via agent X" cannot distinguish a direct user call from an automated chain, and the two deserve different policies.
5. Carry causality separately from authorization. Trace context propagates the request's causal identity: the same trace identifiers across every hop, with span attributes naming the initiating principal, the agent chain, and the triggering task. W3C Trace Context standardizes the wire fields; keep agent-specific identity out of baggage unless you govern its contents, because baggage is visible everywhere it travels.
6. Enforce hop-by-hop verification. Every receiver validates the assertion's signature, issuer, audience, expiry, and the immediate sender's identity, and rejects unsigned or misaudience identity claims even inside a trusted network. The trust model is per-hop chains, not a perimeter.
7. Bound delegation depth. Assertions record the chain length or carry a limit; a chain exceeding its configured depth stops and requires either a fresh direct authorization or an explicit exception. Unbounded delegation turns one confused deputy into an untraceable one.
8. Scope monotonically. Each exchange requests only the scopes or permissions the downstream step needs, which must be a subset of what the caller holds; the token exchange endpoint enforces narrowing, and a hop requesting more than it was granted is a policy violation to alert on, not a configuration puzzle.
9. Reconcile at the end. The final response carries correlation identifiers back up the chain, and each hop logs the full tuple: subject, actor chain, trace identifiers, the action, and the decision. Post-hoc, one query by trace identifier reconstructs every system that touched the request.

## Controls

- Audience-pinning policy: identity assertions are issued to named downstream audiences, and shared or missing audience values fail validation.
- Exchange-only forwarding rule: intermediaries exchange rather than relay credentials, enforced by gateway configuration and tested by replay probes.
- Depth and scope ceilings per agent topology, with violations raising alerts rather than silently truncating.
- Clock-skew tolerance and short assertion lifetimes tuned together, so a replayed assertion has a narrow window and a legitimate chain does not fail on drift.
- Audit-completeness check: scheduled job verifies that every recorded downstream action joins back to an initiating principal via trace identifiers, and orphaned actions are investigated.

## Validation evidence

- Chain verification matrix: valid multi-hop chains succeed end to end; each tampering variant, forged signature, wrong audience, expired assertion, skipped exchange, and depth-exceeded chain, fails at the documented hop with the documented error.
- Replay drill: capture assertions from a live chain and attempt reuse from a different sender after the window; both must fail, proving the per-hop sender binding.
- Narrowing proof: token logs from a representative chain showing scope sets shrinking or holding constant per exchange, never growing.
- Reconstruction exercise: given only a trace identifier, an auditor script enumerates every hop, subject, actor, and decision; completeness rate is the evidence, and any gap is a defect.

## Failure modes and correction

- An intermediary caches exchanged tokens across different subjects to save exchange calls, causing cross-user actions. Correction: exchange results are keyed by subject-plus-audience-plus-scope, cache TTLs bounded by assertion lifetime, and cross-subject cache hits are impossible by construction and verified by test.
- Legacy services accept unsigned identity headers "inside the network," and a path routes through them. Correction: inventory of identity-integrity exceptions with expiry dates, and routing policy that keeps governed chains off those paths.
- Deep chains fail near their depth ceiling during a busy period and operators raise the ceiling at 2 a.m. Correction: ceiling changes are reviewed changes; the operational fix is re-authorizing or restructuring the chain.
- Trace identifiers are dropped at an async boundary (queue, scheduled continuation), orphaning downstream actions. Correction: async propagation is part of the harness contract, and the audit-completeness check catches the gap as a standing control.

## Limitations

Propagation is only as trustworthy as the weakest signing hop; one compromised intermediary can assert whatever chain it likes within its privileges. Cross-organization chains hit trust-model limits: your signature means nothing to a third party without federation, which is a relationship problem, not a protocol one. Assertion validation on every hop adds latency and failure surface. And full causal reconstruction depends on discipline at async boundaries, which is exactly where engineering attention tends to fade.

## Canonical sources

- RFC 8693, OAuth 2.0 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
- W3C Trace Context, Level 1: https://www.w3.org/TR/trace-context/
- RFC 6749, The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
