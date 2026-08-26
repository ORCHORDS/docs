# privacy-preserving-federated-learning-threat-model

**Issue:** Federated learning is described as private by default without assessing information leakage from model updates.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Keeping raw records on devices does not eliminate privacy risk. Model updates can reveal membership or reconstruct sensitive information under some threat models. Secure aggregation and differential privacy address different risks and need evaluated parameters.

**Source:** [NIST privacy attacks in federated learning](https://www.nist.gov/blogs/cybersecurity-insights/privacy-attacks-federated-learning).

## Fix

- define participants, server trust, collusion, update visibility, and attacker capabilities;
- evaluate membership-inference and reconstruction risks for the actual model/data;
- use secure aggregation where individual update visibility is unnecessary;
- apply and document differential-privacy mechanism and utility/privacy budget where appropriate;
- test data-poisoning and privacy attacks before release;
- minimize update retention and protect telemetry.

## Verification

- The threat model identifies who can see individual updates.
- Privacy attack tests and acceptance thresholds are recorded.
- Aggregation/DP controls are validated against the intended deployment.
- A participant removal or failure follows a documented protocol.

## Related

- `ai-ml/machine-unlearning-governance.md`
- `issues/ai-data-poisoning-2026.md`
