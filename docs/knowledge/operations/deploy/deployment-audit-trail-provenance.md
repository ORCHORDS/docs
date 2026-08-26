# deployment-audit-trail-provenance

**Issue:** When a production incident begins with "what exactly changed last night?", teams without a deployment audit trail answer by correlating Slack messages, expired CI logs, and human memory. The Minimum CD catalog lists this as a named symptom: no evidence of what was deployed or when. Every deployment should leave an immutable record of who or what triggered it, which artifact (by digest, never by mutable tag) went out, the exact source commits and PRs it contains, the target environment, the timestamp, and whose approvals cleared the gates. Automated pipelines produce this evidence as a side effect — but only if it is deliberately persisted, because CI log retention expires, chat scrolls away, and a human deploying from a laptop leaves no trace at all. Beyond incident response, SOC 2, ISO 27001, and similar frameworks require exactly this chain of evidence, and its absence turns every audit into an archaeology project.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What every deploy record must capture

1. **Trigger identity.** The human user, service account, or automated agent that initiated the deploy — resolved to a real identity, not a shared bot token. When an AI agent or automation triggers deploys, record the agent identity and the human on whose behalf it acted; "the pipeline did it" is not an answer an auditor or incident commander accepts.

2. **Artifact identity by digest.** Record the immutable artifact digest (OCI digest, package hash, bundle checksum) plus its build identifier. Tags drift and get reused; if your history says "deployed v1.4.2" without a digest, you cannot prove what bytes were actually running.

3. **Source linkage.** The commit SHAs and pull requests contained in the artifact, ideally inherited from the build's provenance attestation rather than reconstructed from git at deploy time. This is the join key that lets an incident commander map a bad commit straight to the deploys that shipped it.

4. **Environment, time, and outcome.** Target environment, start and completion timestamps, final status (succeeded, rolled back, partial), and the previous artifact digest that was replaced. The previous digest is what makes one-command evidence-based rollback possible.

5. **Gate and approval outcomes.** Which checks ran, which protection rules approved the deploy, and which humans signed off where required. For regulated changes, the approval record is the difference between "process followed" and "process asserted."

## Making capture automatic

1. **The pipeline is the only deploy path.** Audit trails come free from automation, so remove alternatives: no production deploys from developer machines, no console click-throughs, no kubectl apply from laptops. Enforce with infrastructure permissions — if humans cannot deploy out-of-band, out-of-band deploys cannot go unaudited.

2. **Emit deploy events to an append-only store.** Have the pipeline emit a structured deploy event (identity, digest, environment, outcome) to centralized logging or a dedicated deployments table at every transition. Treat this stream as the canonical history; CI vendor logs are a rendering, not the record.

3. **Mark deployments where they run.** Annotate running workloads (Kubernetes annotations, Lambda alias description, release notes endpoints like a /version route returning commit and build metadata) so the live system can be compared against the audit trail on demand — which is also how you detect drift between what the trail says and what is actually serving.

4. **Pipeline configuration is part of the trail.** Record the pipeline definition version (commit SHA of the CI/CD config) used for each run. If someone edits the deploy process itself, that change must be visible in the same history as the changes it deployed.

## Retention and integrity

1. **Append-only storage.** Deploy records go to WORM-style storage or a database with no update path — insert only. A trail that can be edited after the fact is not an audit trail; it is a draft.

2. **Retention windows matched to compliance.** Set retention to the longest applicable requirement (often years for regulated systems), and snapshot CI evidence (logs, provenance, approval artifacts) into durable storage before the CI system's own retention deletes them — commonly 90 days or less by default.

3. **Attestation linkage.** Connect deploy records to signed build provenance (SLSA-style attestations) so each entry can prove builder identity and source integrity, not just catalog events. During a supply-chain investigation, provenance answers "could this artifact have come from somewhere else," which timestamps cannot.

## Using the trail

1. **The incident diff.** The first query in any incident: list deploys to the affected environment within the symptom window, with digests and commits. A good trail turns this from a 40-minute Slack archaeology session into a single command that names the suspects.

2. **Compliance evidence on demand.** Map each recorded field to the control it satisfies, so audits become an export from the deploy event store instead of a quarter of screenshot collection. Reviewers trust a system whose evidence is generated by the same automation that does the work.

3. **Out-of-band change detection.** Reconcile what is actually running (live digest markers) against the latest audit entry on a schedule. A mismatch means someone or something changed production without a deployment record — arguably the most important alert this system can fire.
