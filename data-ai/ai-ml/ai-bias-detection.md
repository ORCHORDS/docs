# ai-bias-detection

**Issue:** LLM outputs exhibit demographic, cultural, or factual bias that varies across user groups
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An LLM-based hiring tool gives shorter or less enthusiastic responses for resumes with female names. A customer service bot is more polite to users writing in formal English. Bias is invisible until systematically tested.

## Pattern / Solution
Build a bias evaluation suite: create paired test cases varying protected attributes (name, gender, ethnicity, age) while holding content constant. Measure output quality differences with embedding similarity and human ratings. Run bias evals on every model version before deployment.

Use counterfactual data augmentation (CDA): generate training/eval data by swapping protected attributes to surface model asymmetries. Apply bias metrics like Equal Opportunity Difference and Demographic Parity across defined groups.

## Gotchas
- Bias can be subtle — measure at scale (hundreds of paired examples) rather than anecdotally
- Debiasing one axis (e.g., gender) can introduce bias on another (e.g., name-based ethnicity inference)
- Regulatory requirements (EU AI Act, US EO on AI) mandate bias audits for high-risk applications

## Related
- prompt-testing-evals
- ai-safety-guardrails
- ai-content-moderation
