---
title: Agent Adversarial Robustness Probes
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: quarterly
next-review: 2026-12-05
source: OWASP LLM Top 10 (LLM01 Prompt Injection, LLM06 Sensitive Information Disclosure, LLM07 Insecure Plugin Design); NIST AI 600-1 Generative AI Profile §2.3 (Confused Deputy & Trust Boundary); MITRE ATLAS Adversarial Threat Landscape for AI Systems AML.T0043 (Craft Adversarial Data)
---

## Scope

Defines the structured adversarial evaluation that every ORCHORDS-managed agent must pass before each release. The probe set exercises direct prompt injection, indirect injection via retrieved documents, system-prompt leakage, jailbreak chain attacks, tool-output tampering, and exfiltration over allowed egress channels. Findings feed back into the agent risk register and gate promotion.

## Plan

1. Maintain a versioned probe corpus. Each probe is a multi-turn script with a known target behaviour (refusal, redaction, alert).
2. Execute the corpus weekly in a forked `adversarial-canary` environment that mirrors production agent runtime but uses disposable credentials and an isolated egress proxy.
3. Score each probe: pass (target behaviour observed), fail (target behaviour bypassed), inconclusive (probe infrastructure failure — never the agent).
4. Treat any new failure as a release-blocking regression until either mitigated or formally accepted by the risk owner.
5. Track false-negative rate: routes where the agent produced a target behaviour while the underlying policy expectation was silently weakened. Replay raw transcripts against the latest policy before signing off.

## Inputs

- Probe corpus under `agents/evals/adversarial/`.
- Production agent graph and tool manifest.
- Risk appetite per agent class (read-only retriever vs tool-using vs autonomous).
- Recent incident transcripts reused (with consent) as additional probes.

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Probe coverage | ≥ 95 % of OWASP LLM Top 10 categories mapped |
| Pass rate floor | ≥ 98 % for system-prompt-leakage probes |
| Probe cadence | weekly + on every model upgrade |
| Escape-detection latency | ≤ 60 s from probe start to alert |
| Corpus freshness | new probes added within 7 days of CVE disclosure |

## Implementation Notes

- Treat prompt-injection probes as untrusted: never log raw probe prompts to the same sink as user data; redact before storage.
- For indirect-injection probes, fabricate a small held-out document set with planted instructions; quarantine the retrieval index while the test runs.
- Differentiate partial bypass (the agent complied partially before re-grounding) from full bypass; both must be reported.
- Use deterministic sampling (temperature 0) for reproducible scoring; full-temp runs are diagnostic only.
- Pair this routine with `AGENT_PROMPT_INJECTION_RED_TEAM_PROBES` — that routine captures novel probes; this one runs the contracted set.

## Companion Documents

- `AGENT_RUNTIME_SANDBOX_EVAL.md` — sandbox posture assumed by this probe set.
- `AGENT_HALLUCINATION_DETECTION_CITATION_FAITHFULNESS.md` — separate quality axis.
- `AGENT_SAFETY_INCIDENT_TRIAGE.md` — invoked when a probe indicates real-world exposure.
