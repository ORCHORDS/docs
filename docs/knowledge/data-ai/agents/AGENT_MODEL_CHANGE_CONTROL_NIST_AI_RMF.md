# Model and Configuration Change Control for Agents

## Scope

An agent's behavior can change when the model, system instructions, tool catalog, retrieval corpus, policy, decoder settings, dependency, or routing rule changes. This article turns NIST AI RMF governance and measurement outcomes into an engineering change-control process. It complements general evaluation guidance by focusing on release identity, impact analysis, approval, rollback, and evidence.

Treat the deployable agent as a configuration set, not just a model name. The same model can produce materially different risk when granted a new tool or supplied a different corpus. Conversely, a silent supplier revision can invalidate prior evidence even if application code is unchanged.

## Implementation workflow

Create an immutable release manifest containing model and endpoint identifiers, available revision information, prompts and policy hashes, tool schema versions, retrieval snapshot or index generation, safety settings, orchestrator build, evaluation suite revision, and infrastructure policy. Integrity-protect the manifest and bind it to deployment telemetry.

Classify proposed changes by affected capability and potential impact. A spelling correction may use an abbreviated route; adding write access, changing identity propagation, moving data regions, or replacing the model requires full review. The proposer documents intended benefit, affected populations, new failure modes, dependency changes, evaluation plan, migration strategy, and rollback conditions.

Run a baseline-versus-candidate comparison on frozen tests plus tests targeted to the change. Include task quality, unauthorized-action attempts, privacy leakage, refusal correctness, latency, cost, accessibility, and operational limits as relevant. Investigate meaningful regressions rather than allowing gains in an aggregate score to offset a critical safety failure. Use staged deployment to isolated test, internal traffic, limited cohort, and broader production only when monitoring gates pass.

## Controls

Separate proposing, approving, and deploying high-impact changes. Protect production manifests from direct mutation. Pin dependencies and artifacts where stable identifiers are supported; where exact pinning is impossible, continuously probe for behavioral drift and record that limitation. Tool privileges must not expand merely because the candidate asks for them.

Define release gates as explicit invariants and thresholds. Include zero-tolerance conditions for cross-tenant access, unapproved consequential actions, and secret disclosure. Establish canary stop criteria before rollout. Keep the previous compatible release, data schema, and policy available long enough for tested rollback. Ensure migrations are reversible or provide a forward-recovery procedure.

## Validation evidence

The evidence packet should include the approved change record, manifest diff, risk assessment, test data provenance, test results with uncertainty, failed-case analysis, reviewer identities, staged rollout observations, and final authorization. Runtime traces should allow an incident responder to recover the exact manifest used for a decision without storing sensitive prompt bodies unnecessarily.

Exercise rollback periodically. Verify that routing returns to the prior release, new work stops entering the candidate, in-flight tasks reach a defined terminal state, and state created by the candidate remains interpretable. Use shadow or replay tests only with approved, minimized data. Audit production for manifests that lack approval or whose hashes do not resolve to retained artifacts.

## Failure handling

When a gate fails, block promotion and preserve the candidate evidence; do not average away the failure. During rollout, automatically pause or roll back on predefined safety indicators. Revoke newly introduced credentials and disable new tools independently if full rollback would harm state integrity. If an upstream revision cannot be reversed, route to a tested alternative or disable the affected capability, then re-baseline evaluations under a new manifest.

After an incident, identify all sessions and side effects associated with the release, reconcile durable state, and update tests to represent the violated invariant. Record residual uncertainty and obtain a new decision before resuming rollout.

## Canonical sources

- NIST AI RMF 1.0: https://doi.org/10.6028/NIST.AI.100-1
- NIST AI RMF Playbook: https://airc.nist.gov/airmf-resources/playbook/
- NIST Secure Software Development Framework 1.1: https://doi.org/10.6028/NIST.SP.800-218
