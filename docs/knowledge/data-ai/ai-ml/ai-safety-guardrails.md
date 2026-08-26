# ai-safety-guardrails

**Issue:** LLM applications lack systematic defenses against misuse, jailbreaks, and harmful outputs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An LLM-powered product gets misused via prompt injection, jailbreaks, or adversarial inputs that cause it to produce off-policy content. Relying solely on the model's built-in safety training is insufficient for production applications.

## Pattern / Solution
Layer defenses: (1) system prompt with explicit refusal instructions, (2) input classifier before LLM call, (3) output classifier after, (4) structured output to constrain response space, (5) human review queue for edge cases. Use NeMo Guardrails or Guardrails AI as a framework.

Define colang rules (NeMo) or validators (Guardrails AI) for topic restrictions, output format, and sensitive category handling. Treat guardrails as a separate, independently testable layer — not embedded in prompts.

## Gotchas
- Guardrail latency adds 100-500 ms per call — profile and optimize hot paths
- Overly aggressive guardrails cause false positives that degrade user experience; tune thresholds with real traffic
- System prompt alone is not a guardrail — sufficiently clever adversarial prompts bypass instruction-following

## Related
- ai-content-moderation
- prompt-injection-defense
- prompt-jailbreak-prevention
- ai-output-filtering
