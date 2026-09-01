# Workers Gradual Deployments Traffic Split Verification

Shipping a new Worker version to every user at once is a bet that staging reproduced production faithfully. Gradual deployments replace that bet with a measured ramp: a deployment can point at two versions simultaneously, splitting traffic by percentage, so a defect reaches a bounded slice of requests before it reaches everyone. The hard part is not moving the percentage — it is verifying, at each step, that the split is doing what you think, that errors and latency are attributed to the right version, and that rollback is one action away. This article defines that verification loop.

## Scope

Covers verification activities around gradual deployments of Worker versions: split correctness checks, per-version observability during rollout, and rollback execution. Applies to Wrangler-driven rollouts and dashboard-driven promotions alike. Excludes the schema-migration coupling concerns covered in versioned migration discipline, multi-version service-binding skew handling beyond basic detection, and preview-environment functional testing.

## Workflow or implementation guidance

1. Before the rollout, capture the candidate version ID from `wrangler versions upload` and the currently deployed version ID, and record both in the change ticket. These are the only two legitimate targets of the deployment during the rollout.
2. Start the split at a small percentage with `wrangler versions deploy`, specifying the candidate and prior version IDs with their percentages. Percentages must sum to 100.
3. Verify split correctness immediately: confirm via `wrangler versions list` (or the dashboard deployment view) that the deployment shows exactly the intended two versions and percentages, and that no stale version retains traffic.
4. Tag observability by version. Ensure logs, exceptions, and metrics distinguish the two versions — Workers observability attaches version information to log events — so error rates can be attributed per version rather than blended.
5. Define promotion criteria up front: error-rate delta threshold, latency percentile guardrails, and a dwell time per step. Write them into the ticket before the first split so the decision is mechanical, not improvised.
6. Step the percentages upward (for example 10, 25, 50, 100), re-verifying split state and criteria at each step. Any criterion breach freezes the ramp.
7. On breach, roll back by redeploying the prior version at 100 percent. Because versions are immutable and retained, this is a deployment-pointer change, not a rebuild.
8. After full promotion, record the final deployment state and close the loop with a short outcome note (clean ramp or rollback, with the triggering metric if rolled back).

## Controls

- Two-version invariant: during a gradual rollout, the deployment may reference only the recorded candidate and prior versions; introducing a third mid-ramp requires restarting the process with a new ticket.
- Split-state verification step: after every percentage change, the recorded deployment state is re-read and matched against intent before observability is trusted.
- Version-tagged telemetry requirement: rollouts proceed only where logs and exceptions carry version attribution; unattributable error rates are treated as unknown and block promotion.
- Pre-registered promotion criteria: thresholds and dwell times defined before the first split; changing them mid-rollout requires explicit justification in the ticket.
- Rollback rehearsal: the rollback command for the prior version is written out in the ticket before the ramp starts, so execution under pressure is copy-paste, not recall.
- Ramp freeze on unexplained anomaly: any metric deviation that cannot be attributed to a version (for example a dependency incident) pauses the ramp until explained.

## Validation evidence

- `wrangler versions list` or `wrangler versions view` output at each step showing versions and traffic percentages, time-stamped.
- Per-version error-rate and latency comparison charts across the rollout window, with the split percentages annotated.
- Sampled log lines or exception records demonstrating version attribution is present and correct for both versions.
- The pre-registered promotion criteria as recorded pre-rollout, and the evaluation result at each step.
- Rollback artifacts when applicable: the redeploy command, its output, and post-rollback error-rate recovery.
- Final deployment record showing the candidate at 100 percent (or the prior version restored) plus the outcome note.

## Failure modes and correction

- Blended telemetry hides a version-specific defect: if errors cannot be split by version, stop the ramp, restore version attribution (check observability configuration and log fields), and only then continue.
- Percentages drift from intent after a dashboard edit or a second operator action: re-read the deployment state from the API, correct to the intended split, and add a post-change verification habit to the runbook.
- Requests crossing service bindings execute mixed versions, producing confusing cross-version errors: apply version affinity or a version override on the binding for the rollout window, then remove the override after promotion.
- Candidate performs acceptably at 10 percent but saturates a dependency at 50 percent: freeze, roll back if the guardrail is breached, and re-scope the rollout after capacity analysis — the ramp did its job.
- Rollback target version no longer available within the retained version window: deploy a fresh upload of the previous code as the rollback vehicle rather than waiting.
- Durable Objects interactions during a split behave differently than expected: consult the gradual deployments documentation for Durable Objects specifics and consider promoting before enabling new DO-facing features.

## Limitations

- Traffic splitting is at the edge and per-request; user-level stickiness is not guaranteed without affinity mechanisms.
- Only versions within the retained window can participate in a gradual deployment; older code must be re-uploaded.
- Low-traffic Workers may take a long time to accumulate statistically meaningful error attribution at small percentages.
- Percentage splits distribute requests but not necessarily workload equally if caching or geographic skews interact with the new version.
- Dashboard and CLI views can lag the API momentarily; treat the API as authoritative for split state.

## Canonical sources

- Cloudflare Workers docs, "Gradual deployments": https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- Cloudflare Workers docs, "Versions & deployments": https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Cloudflare Workers docs, "Rollbacks": https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/
