# Agent MCP Sampling Approval Gate

MCP sampling inverts the usual direction of trust: the server asks the client to run an LLM generation on its behalf via `sampling/createMessage`, optionally with tools attached. The client owns the model credentials, pays for tokens, decides which model answers, and controls what comes back. Without a gate, a connected server can exfiltrate context through crafted prompts, burn budget with chatty requests, or steer the client's model toward attacker-chosen tool loops. A sampling approval gate is the client-side decision layer that decides which sampling requests proceed, which are modified, and which are rejected before any model call happens.

## Scope

Applies to MCP clients and hosts that declare the `sampling` capability, including the `sampling.tools` extension where the server supplies tool definitions inside the sampling request. Covers the decision lifecycle: capability negotiation, request inspection, approval modes, execution constraints, and response handling. Server-side tool execution and the tool-result balance rules of the multi-turn loop are referenced only where they affect client gating. Batched or scheduled sampling from background servers is in scope; automated approval is treated as a policy choice that must be explicit.

## Workflow or implementation guidance

1. Negotiate narrowly. Declare `sampling` only for server profiles that need it. Declaring `sampling.tools` separately means tool-enabled requests are rejected as unsupported by default, which is the safest starting posture.
2. Inspect before anything user-visible. Parse the request fully: message history, `systemPrompt`, `modelPreferences`, `maxTokens`, `tools`, `toolChoice`. Requests that fail schema validation are rejected with `-32602`, not repaired.
3. Classify the request against a policy table keyed by server identity and request shape: estimated token cost bucket, presence of `systemPrompt` overrides, presence of tools, inclusion of prior conversation, and content-type mix. Classification selects one of three approval modes.
4. Human approval mode: present the request with the server named, the prompt visible and editable, the estimated cost, and the tools listed. The specification's guidance is that a human should be in the loop with the ability to deny; treat unattended human approval as a configured exception, never a default.
5. Modified approval: the client may strip or rewrite fields before execution, for example removing a `systemPrompt` that conflicts with the host's own, capping `maxTokens`, or mapping `modelPreferences.hints` to an approved model list. Any modification is shown to the approver when a human is present, and logged when not.
6. Policy approval (unattended): only for requests matching a narrow pre-approved template, with hard ceilings on tokens per request, requests per task, and concurrent generations. Anything outside the template escalates to human review or is denied with `-1` (user rejected).
7. Execute through the client's model layer, not a server-supplied endpoint. Record the model actually used, the final prompt after any modification, and the stop reason.
8. Gate the response symmetrically. Generated output is untrusted server-bound data: apply the same filtering tier used for tool results before returning it, and let the user review responses for high-risk servers before delivery.
9. Enforce loop limits for tool-enabled sampling. Each follow-up `sampling/createMessage` that continues a tool loop consumes iteration budget; when the budget is exhausted, force a final answer by refusing further tool-enabled requests rather than silently continuing.

## Controls

- Per-server sampling quota: requests per task, tokens per request, total tokens per session, and a concurrency ceiling. Quota exhaustion denies with a distinct, logged reason.
- Prompt diffing: when a request reuses history, diff against the previous request so the approver sees what changed instead of rereading everything.
- Model allowlist resolution: `modelPreferences` hints are advisory and mapped to approved models only; unmapped hints never select a model by string match against arbitrary names.
- Content boundary: reject requests mixing `tool_result` content with other content in one message, and enforce the rule that every tool use is answered by a matching tool result before other messages continue.
- Full audit chain per request: policy decision, modifications applied, approver identity or policy rule ID, model used, token counts, and a content hash of both prompt and response.

## Validation evidence

- Decision matrix tests: each policy table entry fires the documented mode for representative requests, including a request that sits exactly on a quota boundary.
- Rejection tests: unsupported tool-enabled request against a bare `sampling` capability, malformed message arrays, missing `maxTokens`, and quota-exceeded requests; each returns the specified error code and logs the reason.
- Cost tests: a server issuing a tool loop of ten continuations stops at the configured iteration ceiling and returns a terminal state instead of an eleventh generation.
- Exfiltration drill: a hostile server crafts a prompt asking the model to repeat prior conversation; verify the modified-approval path redacts or blocks the history portion, and that the user-visible diff made the attempt obvious.
- Telemetry review across a release: median approval latency, denial rate by server, and modification frequency, demonstrating the gate is neither a rubber stamp nor a bottleneck.

## Failure modes and correction

- Approval fatigue in interactive mode leads to blanket accepts. Correction: collapse repeated identical requests into a single "allow this template" decision that creates an explicit policy entry, rather than training users to click.
- Over-broad policy approval after an incident-free month quietly widens to new request shapes. Correction: policy templates are versioned and reviewed; new shapes match nothing and escalate by default.
- `ath`-style freshness does not exist here, so a stalled server can hold approvals open; correction: approvals expire with the originating task and are never reusable across sessions.
- Response-side gating is skipped because the request side already approved, letting a crafted generation carry injection into server-side tool execution. Correction: responses pass the same untrusted-content filter regardless of who approved the request.

## Limitations

The gate cannot see what the server does with returned generations; confidentiality of anything sent into a sampling prompt depends on not sending it at all. Human approval quality degrades with prompt length and frequency, so the gate is only as strong as its diffing and templating. Cost estimates from token counts are approximate before execution. Finally, a client that must run unattended inevitably trades human judgment for template precision, and that trade is a documented risk acceptance, not an eliminated risk.

## Canonical sources

- Model Context Protocol specification, Client Sampling: https://spec.modelcontextprotocol.io/specification/2025-11-25/client/sampling
- Model Context Protocol specification, Security Best Practices: https://spec.modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices
- OWASP, LLM Top 10 for LLM Applications (LLM02 Sensitive Information Disclosure): https://genai.owasp.org/llm-top-10/
