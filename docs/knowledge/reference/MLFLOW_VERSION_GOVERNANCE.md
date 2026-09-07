---
title: MLflow Model Registry Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/mlflow/mlflow
---

# MLflow Model Registry Version Governance

## Purpose
Define how teams select, upgrade, and operate MLflow tracking and
model registry deployments so machine learning artefacts remain
versioned, traceable, and aligned with platform governance for model
lifecycle, evaluation, and deployment.

## Scope
Applies to MLflow Tracking Server, MLflow Model Registry, and any
internal integrations packaging MLflow for model experimentation
pipelines and production model promotion across development,
staging, and production environments.

## Version Line Policy
- Track the latest stable minor release for at least 90 days before
  declaring it production-ready.
- Hold one previous minor release available for rollback for at least
  30 days after promotion.
- Skip releases with breaking changes to the tracking API, registry
  schema, or artefact store contract without an internal exception
  record.
- Align MLflow server version with the Python and Java client SDKs
  shipped in the platform's model training and serving runtimes.

## Component Lifecycle
- Tracking components, registry components, and artefact store
  backends progress through the upstream stability ladder.
- New project stages (e.g., `Staging`, `Production`, `Archived`)
  evolve per upstream schema changes and require coordinated
  migration.
- Plugin contracts (authentication, storage, search) are versioned
  per release and any in-house plugin MUST be re-validated per
  upgrade.

## Compatibility Considerations
- Backend store and artefact store backends (PostgreSQL, MySQL,
  S3-compatible object stores, Azure Blob, GCS) MUST be on versions
  supported by the chosen MLflow release.
- Authentication integration MUST interoperate with the platform
  identity provider (OIDC, LDAP, or basic auth fallback).
- Search and tag query syntax MUST remain compatible with
  downstream dashboards and reporting tooling.

## Upgrade Procedure
1. Read upstream release notes and identify breaking changes affecting
   tracking APIs, registry schema, or artefact store contracts.
2. Validate the new release in a staging environment with a snapshot
   of recent experiment runs, registered models, and stage
   transitions.
3. Run a canary upgrade for the tracking server and confirm
   experiment logging, parameter capture, and artefact upload
   succeed against the synthetic workloads.
4. Promote the upgrade across remaining instances with pre-staged
   rollback artifacts and on-call coverage.
5. Record the upgrade window, observed deltas, and any compensating
   configuration changes in the change log.

## Rollback Procedure
- Re-deploy the previous MLflow image and configuration from the
  versioned artefact store.
- Restore the prior registry schema snapshot so registered models and
  stage transitions match the pre-upgrade state.
- Re-validate experiment logging and artefact upload against the
  synthetic probes.
- Open a regression ticket capturing the cause of the rollback and
  link it to the originating upgrade record.

## Security Considerations
- Pin MLflow images by digest and verify signatures using the
  container trust store.
- Restrict tracking API write access to the model training and
  evaluation pipelines; restrict registry write access to authorised
  promotion pipelines.
- Use external authentication providers and disable local admin
  accounts outside break-glass scenarios.
- Scrub secrets from parameter values before logging and reject
  artefact uploads containing protected data classes.

## Operational Impact Points
- Registry upgrades require coordinated pipeline pauses; expect
  momentary experiment logging delays covered by client retry.
- Backend store retention and artefact garbage collection policies
  trade disk usage for audit and reproducibility capability.
- High-cardinality tag dimensions can degrade search performance;
  enforce tag naming conventions and cardinality budgets.
- Production promotion workflows MUST be wired through the model
  registry with documented approvers before serving rollout.

## Cross-References
- See [KServe version governance](KSERVE_VERSION_GOVERNANCE.md) for
  inference serving integration.
- See [Triton Inference Server version governance](TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md)
  for runtime compatibility.
- See [AI Model Lifecycle Playbook](../playbooks/AI_MODEL_LIFECYCLE_PLAYBOOK.md)
  for end-to-end lifecycle practice.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
