# Sealed Secrets Rotation in GitOps

**Issue:** Sealed Secrets encrypts Kubernetes Secret data into a Safe format that can be safely committed to Git, but a sealed secret whose underlying encryption key is rotated leaves operators with no clear path to re-seal existing values without disrupting running workloads. Teams that defer rotation until a security event discover that rotation requires coordinated work across CI, controller, and Git history, and that any one of those surfaces will hold the migration hostage.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How Sealed Secrets Key Rotation Actually Works

The Sealed Secrets controller holds an asymmetric key pair; the public key encrypts values via `kubeseal`, producing a SealedSecret CRD whose `.spec.encryptedData` field is decryptable only by the controller's matching private key. The controller runs in the cluster namespace and watches for SealedSecret resources. When a SealedSecret appears, the controller decrypts the encrypted data with its private key and creates or updates the underlying Kubernetes Secret.

Rotation, in the official sense, means replacing the controller's key pair so that subsequent decrypts use the new key. The controller supports a transition phase: during rotation, the controller accepts both old and new key material, decrypts SealedSecrets that were sealed under either, and signs new SealedSecrets with the new key. Operators re-seal existing values to migrate them onto the new key without touching the underlying Secret. The transition is finite; the controller eventually prunes the old key.

## The Re-Seal Workflow

Re-sealing under a new key requires reading the plaintext value out of the cluster, which means accessing the Secret. This is a chicken-and-egg problem in GitOps: the plaintext lived in the SealedSecret, was decrypted by the controller, and was never re-exported. A clean migration path is to have the controller emit a re-seal endpoint, or to run `kubeseal --fetch-cert` against the new certificate and use a CI job that reads the existing Secret from the cluster, re-seals it, and commits the result.

This workflow must be exercised in a non-production environment before rotation day. The drill selects a SealedSecret, runs the re-seal pipeline against a staging cluster whose controller holds the new key, verifies the resulting SealedSecret decrypts correctly, and confirms the underlying Secret is byte-identical. The drill verifies two things: that the CI job has permission to read the existing Secret, and that the new controller key material is accessible to the seal command.

## GitOps Implications

Re-sealing produces a commit that updates the SealedSecret in Git. The commit must be paired with the controller key rotation in the same window; otherwise the cluster will have a mix of old and new keys during the transition, and the GitOps repository will have a mix of old and new ciphertext. Operators should plan a maintenance window in which both the cluster and Git move together, and revert either side if the other side fails.

Flux and Argo CD react to the commit by reconciling the new SealedSecret. If the new SealedSecret decrypts with the new key material in the controller, the Secret is updated transparently. If the new SealedSecret is rejected because the controller still holds only the old key, the Kustomization reports Ready=False and the underlying Secret remains at its last-known-good state. This asymmetry is desirable: a failed re-seal should never silently propagate, and the GitOps controller will not push a Secret it cannot decrypt.

## Handling Old Sealed Secrets Post-Rotation

After rotation, the GitOps repository still contains SealedSecrets sealed under the old key. During the transition phase these continue to decrypt, but once the controller prunes the old key, the next reconciliation of an old SealedSecret produces an error. The repository must therefore be fully re-sealed before pruning completes. Use the controller's `--key-ttl` flag to set a transition window that aligns with the time required to re-seal the entire repository.

Schedule the re-seal as a batch job rather than as per-secret effort. The batch reads every SealedSecret in the repository, runs it through the re-seal pipeline, and overwrites the ciphertext with the new key's output. The batch must be idempotent: re-running on already-rotated secrets should be a no-op. Validate the batch's output against a known set of plaintext values before pushing the commits to Git.

## Failure Modes

The most common failure is rotating the controller key without re-sealing the repository, then pruning the old key too aggressively. The controller will reject every old SealedSecret, and the affected Secrets will be deleted (because SealedSecret controls its underlying Secret). The remediation path is to re-apply the old key material temporarily, re-seal the entire repository, then re-rotate. This works only if the controller's key history is preserved at the rotation step, which is why the controller provides a transition phase that operators must use deliberately.

A second failure is rotating too often. Each rotation is a planned outage window in which both Git and cluster must move together. Teams that rotate quarterly create an operational tax that detracts from the security benefit; teams that rotate annually have a smaller attack surface but lose the operational muscle memory. A pragmatic cadence is annual rotation with an additional drill every six months.

A third failure is rotation during an unrelated incident, when the team is already operating at degraded attention. Rotation requires careful coordination and is best done during a quiet maintenance window. If a security event forces emergency rotation, follow the same drill steps but expect longer mean-time-to-recovery and document the deviations for after-action review.

## Canonical sources

1. https://github.com/bitnami-labs/sealed-secrets/blob/main/docs/rotating-sealed-secrets.md
2. https://fluxcd.io/flux/components/kustomize/kustomizations/