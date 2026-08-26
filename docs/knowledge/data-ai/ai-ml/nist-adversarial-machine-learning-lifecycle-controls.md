# NIST adversarial machine-learning lifecycle controls

**Issue:** Treating “prompt injection” or “model evasion” as a single security feature request leaves gaps before training, during deployment, and after an incident. A useful control plan must identify the ML lifecycle stage, the attacker’s objective and knowledge, then connect each combination to an observable mitigation and owner.

**Date:** 2026-08-17
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What to model

NIST’s adversarial-machine-learning (AML) taxonomy separates ML method, lifecycle stage, attacker goals, objectives, capabilities, and knowledge. Use those terms in the threat model rather than collapsing all attacks into “AI misuse.”

1. **Inventory the system boundary.** Record model, training and fine-tuning data sources, retrieval stores, tools, evaluation datasets, serving endpoint, and human review paths. A control cannot protect an asset the team has not named.
2. **Classify the attack stage.** Distinguish attacks on data collection/training, model development, inference, and downstream decision use. The same unsafe input can mean training-data poisoning in one stage and an evasion attempt in another.
3. **State the attacker objective and access.** Note whether the goal is integrity, availability, privacy, or misuse; and whether the actor can alter data, query the model, supply a tool result, or observe outputs. This makes proposed defenses falsifiable.
4. **Link threats to a tested control.** Examples include provenance and review for training inputs, data-quality and outlier checks, isolation of retrieval/tool permissions, adversarial evaluation, output validation, rate limits, and incident rollback paths. Do not claim a guardrail mitigates a threat until it has a defined test.

## Operating controls

1. **Gate data changes.** Version data, prompts, model configuration, and evaluation sets. Require provenance and review for new sources; preserve a rollback target for each production model or retrieval corpus.
2. **Run adversarial evaluation before promotion.** Include relevant misuse cases, poisoned or conflicting retrieved material, tool-abuse attempts, and privacy probes. Track failures by lifecycle stage and attacker capability, not only a single aggregate score.
3. **Separate authority from generated text.** Model output and retrieved content are untrusted instructions. Enforce authorization at the tool/API boundary with scoped credentials and server-side policy.
4. **Monitor for drift and attacks.** Alert on unexpected input distributions, sharp changes in refusal/tool-call/error rates, retrieval-source anomalies, and abnormal query patterns. Retain only the telemetry justified by the security and privacy design.
5. **Practice containment.** The runbook should say who can disable a tool, withdraw a retrieval source, roll back model/configuration, preserve evidence, and notify affected users. A theoretical mitigation is not an operational control.

## Evidence to retain

- Versioned threat model and data/model lineage.
- Evaluation cases, results, acceptance thresholds, and exceptions.
- Tool authorization policies and access-review records.
- Monitoring dashboards, alert runbooks, and incident lessons.
- Change approvals and rollback verification.

## Anti-patterns

- **One “AI security” checkbox.** AML risks differ materially by attacker capability and lifecycle stage.
- **Trusting model output to authorize itself.** Generated content must never become an access decision without independent policy enforcement.
- **Only testing benign quality.** Capability and accuracy tests do not demonstrate resistance to adversarial inputs.
- **Collecting raw prompts forever.** Security telemetry needs minimization, access control, and retention limits.

## Sources

- [NIST AI 100-2e2025, *Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations*](https://www.nist.gov/publications/adversarial-machine-learning-taxonomy-and-terminology-attacks-and-mitigations-0)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
