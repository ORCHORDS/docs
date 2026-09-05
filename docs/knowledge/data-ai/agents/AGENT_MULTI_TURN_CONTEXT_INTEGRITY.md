---
title: Agent Multi-Turn Context Integrity
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: quarterly
next-review: 2026-12-05
source: OWASP LLM Top 10 LLM08 Excessive Agency; NIST AI 600-1 §2.2 (Generative AI Profile — Context & Memory); Anthropic "Building effective agents" (2024) — context engineering; Söderström & Arnaut (2024) "Dialogue-level Jailbreak Attack"
---

## Scope

Defines how ORCHORDS preserves the integrity of the agent's multi-turn working context across a session. A multi-turn context is the running sequence of system messages, prior turns, tool calls, retrieved snippets, and inter-agent messages the agent uses to compute its next action. Integrity violations include dropped turns, replayed turns, fabricated turns, role confusion, and context-flood attacks intended to displace or evict safety directives.

## Plan

1. Treat every input as untrusted. The agent must never trust turn provenance on the basis of role labels alone.
2. Maintain a signed, append-only log of accepted turns. Each entry references the prior entry's hash to detect reorder or replay.
3. Enforce a context window budget. When the budget is exceeded, apply an eviction policy that retains system and tool-identity messages and discards early user turns first.
4. Detect cross-turn injection: a later user turn that depends on or defers to a prior injected instruction. Treat such defers as continuing injection, not as legitimate user intent.
5. For multi-agent flows, authenticate each inter-agent message with a session-bound token signed by the orchestrator; reject any message lacking a fresh signature.

## Inputs

- Logging / trace store (OpenTelemetry-compatible).
- Per-session nonce service.
- Agent manifest defining role for each message source.
- Eviction policy configured per agent class.

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Log integrity | append-only, hash-chained |
| Replay detection | within 5 s of duplicate arrival |
| Window budget per agent class | 32k–200k tokens (per agent manifest) |
| Eviction policy | system+tool priority preserved |
| Inter-agent auth | mTLS + signed message envelope |

## Implementation Notes

- Surface turn provenance to the agent via the trace metadata, not via the user-visible message string. Strip any embedded role-claim from the string before display.
- When a context-flood is detected (user pastes 50 pages of token-heavy text mid-session), reset the session and require a fresh re-grounding.
- Cross-turn defers disguised as "as you said above" must be re-validated against the original turn; if the original was injected, the defer is rejected.
- For long sessions, archive the full turn log daily; the active window only carries the summary index plus the most recent N turns.

## Companion Documents

- `AGENT_DISTRIBUTED_TRACING_OTEL.md` — instrumentation backbone.
- `AGENT_HUMAN_HANDOFF_PROCEDURE.md` — escalation when context integrity is in doubt.
- `AGENT_TOOL_USE_AUDIT_TRAIL.md` — complementary tool-side integrity.
