# ai-data-poisoning-2026

**Issue:** A team trains a model on user-generated content. An attacker submits poisoned data points to bias the model. The team reads about Anthropic's Sleeper Agents, NIST AI 100-2 Adversarial ML Taxonomy. The team needs the 2026 reference for data poisoning defense.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 poisoning attack types

1. **Backdoor attack.** Trigger phrase in input causes targeted misclassification. Trained into weights.
2. **Sleeper agent.** Model behaves normally until a date or trigger, then acts maliciously. Hard to detect by evaluation.
3. **Targeted bias.** Flooding dataset with biased examples shifts model behavior in a direction.
4. **Untargeted degradation.** Random noise / incorrect labels degrade model accuracy.
5. **Data contamination.** Submitting a paper / dataset to public corpora that will be scraped for training.

## The 5 detection strategies

1. **Anomaly detection on training data.** Statistical outliers, near-duplicates, suspicious sources.
2. **Activation clustering.** Find inputs that produce unusual internal activations.
3. **Probing evaluation.** Test for known trigger phrases, model-on-model consistency.
4. **Backdoor scanners (Neural Cleanse, ABS).** Reverse-engineer potential triggers.
5. **Data provenance.** Track who submitted what; rate-limit high-impact sources.

## The 5 defense patterns

1. **Data filtering** - reject outliers, near-duplicates, suspicious patterns.
2. **Trusted source priority** - licensed data first, scraped data vetted.
3. **Differential testing** - compare model behavior across data subsets.
4. **Anomaly detection on activations** during training.
5. **Post-training red teaming** for backdoor detection.

## The 5-step adoption pattern

1. **Inventory data sources** with provenance.
2. **Anomaly detection** on incoming training data.
3. **Activation clustering** during training to surface outliers.
4. **Differential evaluation** across data subsets.
5. **Post-training red team** for backdoor detection.

## The 5 anti-patterns

1. **"Garbage in, garbage out"** without active filtering.
2. **Trusting all scraped data equally** - some sources adversarial.
3. **No backdoor-specific evaluation** - accuracy tests miss triggers.
4. **Training data version not isolated** - poison spreads to all models trained on it.
5. **Post-training only** - too late if poison is well-distributed.

## Gotchas

- Backdoor triggers can be subtle (a specific URL, a date, a particular token sequence).
- Sleeper agents are designed to evade standard evaluation.
- Data contamination via public papers/datasets is the most common 2026 attack vector.
- Activation clustering requires access to internal model state, not just API.
- Some defenses (Neural Cleanse) work better on image models than LLMs.

## Source URLs (verified 2026-08-10)

- https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-2.pdf
- https://arxiv.org/abs/2401.05566 (Sleeper Agents)
- https://github.com/IBM/adversarial-robustness-toolbox
- https://arxiv.org/abs/1708.06733 (Neural Cleanse)
