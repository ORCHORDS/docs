---
title: Agent Prompt Leakage Defense
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: quarterly
next-review: 2026-12-05
source: OWASP LLM Top 10 LLM07 Insecure Plugin Design; OWASP LLM02 Sensitive Information Disclosure; NIST AI 600-1 §2.3 (Trust Boundaries); Carnegie Mellon SEI "Adversarial Testing for Generative AI" (Feb 2024) §4 (System Prompt Leakage)
---

## Scope

Defends against the disclosure of any system-prompt instruction, hidden chain-of-thought, retrieval anchor, tool schema, or governance directive the agent relies on. A leakage occurs when the agent reproduces, paraphrases, or is manipulated into reproducing internal configuration to an external user, retrieved document, or downstream tool. Treat any leak as a configuration disclosure incident.

## Plan

1. Catalogue every value the agent must keep private: system message contents, tool JSON schemas, retrieval indices and their keys, internal usernames, prompts of any other agents in a multi-agent flow.
2. Apply a defence-in-depth stack: pre-tool filtering of agent output, output-classifier trained to detect system-prompt fragments, post-tool redaction, and policy-enforcing egress proxy.
3. Add adversarial probes from `AGENT_ADVERSARIAL_ROBUSTNESS_PROBE.md` that explicitly ask the agent to share its instructions, role-play as a developer, or otherwise attempt to extract hidden text.
4. When a probe or live signal indicates leakage, rotate the affected configuration and audit recent transcripts.
5. Maintain a "system prompt diff" log: every prompt change is reviewed, signed by the owner, and tied to a release tag.

## Inputs

- Full agent configuration (system prompt, tools, retrievers).
- Output redaction service or classifier (`/internal/llm-redactor`).
- Transcript store with retention controls.
- Legal review for jurisdiction-specific disclosure thresholds.

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Leakage-classifier recall | ≥ 99 % on held-out probe set |
| Output token redaction floor | trim internal blocks before transmission |
| Tool output redaction | regex + embedding classifier + heuristic sensitive-key match |
| Disclosure escalation latency | ≤ 15 min from classifier signal to on-call page |
| Rotation SLA | ≤ 60 min for any leaked component |

## Implementation Notes

- Never expose the raw system message to the model output channel. Treat the prompt as an environment variable the agent reads from; never as a user-facing string.
- Train the leakage classifier on labelled corpora of "block A leaked" / "block A did not leak" using deterministic eval splits.
- For multi-agent flows, audit the entire chain: a downstream agent may leak the upstream agent's prompt even when the upstream itself was clean.
- When you discover a novel extraction technique in a live incident, add a probe and rotate the prompt — never add a silent band-aid.

## Companion Documents

- `AGENT_PROMPT_INJECTION_RED_TEAM_PROBES.md` — produces the probe library.
- `AGENT_HUMAN_HANDOFF_PROCEDURE.md` — used when leakage escalates to a user-visible disclosure.
- `AGENT_CONTENT_MODERATION_GATEWAY.md` — separate content-policy defence.
