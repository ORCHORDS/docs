# Rekor Transparency Log Inclusion Rollout Playbook

## Purpose

Bring Sigstore Rekor into a CI/CD pipeline under the version, inclusion-proof, and sharding constraints in `REKOR_VERSION_GOVERNANCE.md` so that every Cosign-signed artifact carries a verifiable, durable inclusion proof.

## Audience

Platform engineers, supply-chain security engineers, and SREs responsible for signature verification in CI/CD pipelines.

## Pre-conditions

- The cluster and CI runners run a supported Kubernetes release under `KUBERNETES_VERSION_GOVERNANCE.md`.
- Cosign release and Rekor release are pinned to a supported minor under `COSIGN_VERSION_GOVERNANCE.md` and `REKOR_VERSION_GOVERNANCE.md`.
- A documented Rekor trust-root pin exists in the sigstore-root TUF client configuration.
- A monitoring and alerting destination is configured for Rekor checkpoint and signed-note tree size.

## Procedure

### Step 1 — Select Rekor deployment mode

- For new deployments, select Rekor 2.5.x with rekor-tiles GA; pin the log ID and the public key.
- For existing Rekor 2.1.x–2.4.x deployments, plan a migration to rekor-tiles within the documented upgrade window.
- For air-gapped environments, deploy a local Rekor mirror; document the trust-root out-of-band delivery.

### Step 2 — Pin trust root and log parameters

- Consume the sigstore-root TUF metadata through the TUF client; never pin by raw PEM.
- Pin the Rekor log ID per environment (production, staging, dev); record the pin in the deployment manifest.
- Document the checkpoint interval and the monitoring threshold for the signed-note tree size.

### Step 3 — Wire CI signing through Cosign with inclusion proof

- Configure Cosign to require `--inclusion-uri` and `--rekor-url` at signing time; reject signatures without an inclusion proof.
- Persist the inclusion proof alongside the artifact in the registry or in a parallel attestations store.
- Verify the inclusion proof in CI as a release gate; treat a missing proof as a release-blocking defect.

### Step 4 — Configure monitoring

- Monitor Rekor checkpoint lag against the documented threshold; alert on threshold breach.
- Monitor signed-note tree size against the documented threshold; alert on threshold breach.
- Run `rekor-cli verify` against a canary entry on a documented cadence; alert on failure.

### Step 5 — Validate end-to-end

- Sign a canary artifact; verify the inclusion proof from a clean workstation.
- Re-verify the canary signature 24 hours later to confirm the entry is persisted in the log.
- Document the validation outcome and attach it to the rollout record.

### Step 6 — Roll out to production

- Promote the deployment to production in the documented change window.
- Open a release ticket that records the Rekor version, the log ID, and the trust-root pin.
- Re-baseline the monitoring thresholds if production traffic changes the baseline.

## Rollback

- Revert the Cosign `--inclusion-uri` requirement; signatures remain but are flagged as "no inclusion proof" in the verifier.
- Roll back the Rekor deployment to the previous minor; record the rollback reason and the impacted signers.
- Open a remediation ticket that names the trust-root update or log-shard transition that triggered the rollback.

## References

- `REKOR_VERSION_GOVERNANCE.md`
- `COSIGN_VERSION_GOVERNANCE.md`
- `FULCIO_VERSION_GOVERNANCE.md`
- `COSIGN_IMAGE_SIGNING_PLAYBOOK.md`
- `NIST_SP_800_218_SSDF_V1_1_GOVERNANCE.md`
- `EU_CYBER_RESILIENCE_ACT_2024_GOVERNANCE.md`
