# Feature Backfill Migration Playbook

## Purpose

Migrate an existing feature view to a new transformation version, source snapshot, or schema while preserving the workload's freshness SLA, online / offline parity, and tenant-scoping guarantees. The playbook aligns with [Feature Pipeline Lineage Governance](../standards/FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md) and [Feature Store Architecture Governance](../standards/FEATURE_STORE_ARCHITECTURE_GOVERNANCE.md).

## Audience

Workload owners, ML platform engineers, data engineers, Feature Platform engineers.

## Pre-conditions

1. The target transformation version is registered in the Feature Platform registry with a documented transformation card.
2. The target source snapshot is captured, content-addressed, and frozen in the snapshot store.
3. The freshness SLA and the online / offline parity contract for the workload are documented; the evaluation set is current.
4. A staging replica of the source feature view is available for the rehearsal run.
5. Security review is complete for any change that affects personal-data feature values.

## Procedure

1. **Scope the backfill.** Identify the source and target feature-view versions, the cutover strategy (dual-write + switch, or shadow + cutover), the batch size, and the abort criteria. Record the plan in the migration ticket.
2. **Rehearse in staging.** Run the transformation pipeline against the staging snapshot; emit lineage records; measure freshness, point-in-time correctness, and online / offline parity against the existing view. Resolve any regression before the production run.
3. **Provision the target view.** Create the target feature view with the new transformation version, source snapshot, and freshness SLA. Validate that the access layer rejects queries without a tenant filter.
4. **Run the production materialisation job.** Process the source snapshot in batches; write feature values and lineage records to the target view. Surface progress on the workload dashboard.
5. **Validate during the run.** Sample at least 100 entity keys per batch and compare freshness, parity, and determinism against the baseline. Halt the run if any metric regresses by more than the abort criterion.
6. **Wire dual-write or shadow reads.** Configure the application to write to both views and read from the source view until the cutover is approved.
7. **Cut over.** Switch reads to the target view; keep dual-writes active for at least 24 hours to catch late-arriving records.
8. **Quarantine the source view.** Mark the source view as `quarantined`; retain the storage for at least 30 days; do not delete until the migration is signed off.
9. **Sign off.** Confirm the freshness SLA is met, parity is within tolerance, and lineage records are complete; close the migration ticket.
10. **Decommission the source view.** After the quarantine window, delete the source feature values and lineage records following the data-lifecycle procedure.

## Rollback

1. Stop the materialisation job and freeze writes to the target view.
2. Switch reads back to the source view.
3. If dual-write was not active, restore the source view from the most recent snapshot; document the data gap.
4. Open a remediation ticket that captures the regression metric, the abort criterion that was triggered, and the proposed fix.
5. Communicate the rollback to stakeholders and reschedule the migration after the fix is verified.

## References

- [Feature Pipeline Lineage Governance](../standards/FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)
- [Feature Store Architecture Governance](../standards/FEATURE_STORE_ARCHITECTURE_GOVERNANCE.md)
- [Feature Store Access Control Governance](../standards/FEATURE_STORE_ACCESS_CONTROL_GOVERNANCE.md)
- [Feast Open Source Feature Store Version Governance](../reference/FEAST_VERSION_GOVERNANCE.md)
- [Tecton Feature Platform Version Governance](../reference/TECTON_VERSION_GOVERNANCE.md)
- [Hopsworks Feature Store Version Governance](../reference/HOPSWORKS_FEATURE_STORE_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
