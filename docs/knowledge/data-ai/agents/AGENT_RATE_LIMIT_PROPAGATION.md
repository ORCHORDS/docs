# Agent Rate Limit Propagation

## Scope

This article covers propagating upstream rate-limit responses through an agent's tool calls so that back-pressure is respected across multi-step workflows. When an agent's tool call returns a rate-limit signal — for example, an HTTP 429 with `Retry-After`, a streaming response that closes with a rate-limit error, or a vendor-specific quota indicator — the agent must translate that signal into a decision about its own pacing, its retry schedule, and whether to defer subsequent calls to the same upstream. The article covers the parsing of rate-limit responses, the propagation of the limit through agent state, and the propagation of the limit across multi-step workflows that may include parallel tool calls and downstream delegations.

Out of scope: server-side rate limiting algorithms themselves, which are a server concern, and the design of token-bucket or leaky-bucket primitives. This article assumes the upstream signals its limits in a form the agent can interpret, and focuses on the agent's response.

## Implementation workflow

Parse rate-limit responses consistently. The agent extracts, at minimum, the following fields when present: `Retry-After` (numeric seconds or HTTP-date, per RFC 9110), `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, `RateLimit-Policy`, and any vendor-specific quota fields. The IETF draft of the RateLimit fields for HTTP, draft-ietf-httpapi-ratelimit-headers, defines a richer vocabulary that the agent should also accept. When the response includes both a `Retry-After` and a `RateLimit-Reset`, the agent uses the more conservative of the two.

Maintain a per-upstream rate-limit state object. The state object tracks the upstream identity (a stable identifier independent of DNS aliasing), the current limit window's `remaining` count, the `reset` time, the observed retry-after deltas, and a confidence factor that increases with each successful observation. The state object is local to the agent process; multiple agent processes targeting the same upstream each maintain their own state and the upstream's own limit logic arbitrates among them.

Translate rate-limit signals into agent pacing decisions. When a tool call returns a rate-limit response, the agent marks the upstream as constrained, records the suggested wait, and adds the upstream to a back-pressure set. The agent's tool dispatcher then refuses to make further calls to that upstream until the wait has elapsed or a fresh response indicates the limit has been lifted. This is the same discipline that HTTP/2 connection coalescing uses to prevent a single slow stream from blocking others, applied at the tool-call boundary.

Propagate the limit through multi-step workflows. When the agent is part of a multi-step workflow, it must inform downstream steps and peer agents of the constraint. The propagation mechanism depends on the workflow substrate; for A2A-style workflows, the limit appears in the task metadata; for MCP-style workflows, it appears as a structured error; for batched workflows, the limit is recorded in the batch header. The propagation must be specific: it names the upstream, the wait duration, and the operations affected.

When the agent delegates to another agent (a sub-agent or a peer), the delegation payload includes the rate-limit state for any upstream the delegatee might also call. The delegatee treats the propagated state as authoritative for the duration of the delegation; if it observes a fresher value, it adopts the fresher value. This prevents the delegatee from immediately violating a limit the delegator just observed.

The rate-limit state is observable. The agent emits `rate-limit-observed`, `rate-limit-propagated`, and `rate-limit-cleared` events. The events feed the same telemetry pipeline as trace spans, so reviewers can correlate upstream rate-limiting with agent decisions. The events include the upstream identifier, the wait duration, and the affected operations.

## Controls

Rate-limit responses must be honored, not optimized away. An agent that retries sooner than the upstream suggested, or that pre-emptively throttles only some calls while letting others through, undermines the upstream's resource control. The agent's retry loop reads the rate-limit state at the moment of scheduling each retry; the wait is non-negotiable.

Avoid token hoarding. An agent that holds rate-limit budget for itself and refuses to share it with peer agents is anti-social in the multi-agent sense. Where the upstream allows budget sharing (for example, through a shared token bucket that multiple agents can draw from), the agent should participate in the shared pool rather than maintain its own private budget. Where the upstream's limit is per-caller, the agent must not attempt to circumvent that constraint through caller identity rotation.

Detect silent rate-limit failures. Some upstreams signal rate-limit through side channels (for example, degraded response quality, partial responses, or dropped streaming chunks). The agent must monitor these signals and apply the same back-pressure discipline as it would for an explicit rate-limit response. A monitoring failure is itself an alertable anomaly.

Bound the wait. A rate-limit response that suggests a wait of multiple hours is almost certainly a misconfiguration, an outage indicator, or a malicious response. The agent caps the wait at a configured maximum (commonly sixty seconds for interactive workflows, longer for batch workflows) and treats the response as a `rate-limit-anomaly` that triggers escalation rather than a normal rate-limit response.

## Validation evidence

Conformance tests must cover: parsing of all supported rate-limit header forms, propagation to a downstream agent through A2A and MCP-style workflows, refusal to retry before the suggested wait, detection of silent rate-limit failures, rejection of pre-emption attempts by another part of the same agent, and bounded-wait handling for anomalous responses. Inject rate-limit responses with malformed headers, conflicting values, and vendor-specific fields and verify the agent's parsing.

Operational evidence includes: distribution of waits observed per upstream, count of rate-limit events per workflow, count of propagated constraints honored by peer agents, count of detected silent rate-limit failures, and count of anomalous rate-limit responses. The telemetry must be specific enough to attribute rate-limit back-pressure to the upstream that caused it.

## Failure handling

When the agent cannot determine whether a response is a rate-limit (for example, when the upstream's response is truncated or uses a non-standard format), the agent applies a conservative default: wait, then retry once with backoff. If the second response is also ambiguous, the agent treats the upstream as degraded and surfaces the issue for operator review.

When a rate-limit wait deadline would push the agent past its own overall task deadline, the agent does not silently violate the upstream's rate limit. It surfaces a `rate-limit-deadline-conflict` error to the supervisor and either requests a deadline extension, switches to an alternative upstream, or escalates. The decision is made at the workflow level, not by the tool dispatcher.

When the propagated rate-limit state from a delegator is stale by the time the delegatee observes it, the delegatee refreshes its state by issuing a single low-cost request (if the upstream supports it) or by treating the upstream as constrained for a conservative default period. The delegatee does not assume the limit has been lifted on the basis of stale state.

When multiple rate-limit signals from different upstreams conflict (for example, two upstreams with different policies on the same logical operation), the agent applies the strictest of the constraints. The strictest-wins rule is conservative and prevents the agent from reasoning its way into a violation.

## Canonical sources

- RFC 9110, HTTP Semantics, Section 10.2.3 `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110#section-10.2.3
- IETF draft-ietf-httpapi-ratelimit-headers, RateLimit header fields for HTTP: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
- W3C Trace Context, Level 2 (background reference for context propagation across distributed calls): https://www.w3.org/TR/trace-context/
- NIST SP 800-53 Rev. 5, SC-5 Denial of Service Protection (background reference for resource-control discipline): https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
