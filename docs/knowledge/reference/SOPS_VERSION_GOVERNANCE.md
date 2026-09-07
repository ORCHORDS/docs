---
title: Mozilla SOPS Encrypted YAML Secrets Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Mozilla SOPS project (getsops/sops); Mozilla Public License 2.0; documentation at getsops.io and the upstream release index
---

# Mozilla SOPS Encrypted YAML Secrets Version Governance

## Overview

This card governs how `orchords-docs` evaluates Mozilla SOPS (Simple Ops for encrypted Secrets) across versions, key source modes, and GitOps integration. It is the canonical reference for any KB card that cites encrypted-at-rest secrets in Git, decryption patterns, or key rotation in repository workflows.

SOPS is an open-source editor for encrypted files, released under the Mozilla Public License 2.0 and maintained under the `getsops/sops` upstream. SOPS encrypts the values of structured files while leaving keys, comments, and structure in plaintext, enabling safe storage of secrets in Git. This card treats SOPS as a controlled dependency: version pin, key source policy, and integration pattern (Kustomize / FluxCD / ArgoCD) are decided centrally and inherited by all dependent cards.

## Encryption formats

SOPS supports encrypting the values of multiple structured formats while preserving structure:

- YAML: the canonical format for Kubernetes manifests; comments and keys remain readable, only values are encrypted.
- JSON: supported, with the same value-only encryption policy.
- INI: supported with `.ini` files; values are encrypted, keys preserved.
- Binary: an opaque payload format (`--input-type binary --output-type binary`) used for non-text secrets.
- ENV (`.env`): value encryption while leaving keys and comments readable.
- Use YAML for Kubernetes manifests, ENV for dotenv-style configuration, and Binary for non-text secrets. JSON is reserved for legacy paths.

References: `https://github.com/getsops/sops`, `https://getsops.io/`.

## KMS / age / PGP key source modes

SOPS supports three key source families; selection is policy:

- KMS (cloud key management): AWS KMS, GCP KMS, Azure Key Vault. Each encrypted value is wrapped to one or more KMS keys; decryption requires IAM access to the key.
- age: a modern, audited, GPG-free encryption scheme. Public-key only; identity files can be stored on disk, in KMS, or in HashiCorp Vault. Recommended for greenfield deployments.
- PGP/GPG: legacy; widely deployed but discouraged for new projects due to UX complexity and historical weaknesses in key handling.
- Combined configurations are supported: SOPS can encrypt to a mix of KMS, age, and PGP recipients, enabling key escrow and staged rotation.
- Pin a single primary key source per environment; treat mixed sources as a migration aid only.

## Integration with GitOps

SOPS integrates with the three major Kubernetes GitOps controllers:

- FluxCD: uses the `sops` integration natively in `Kustomization`; decryption key is supplied via a Kubernetes `Secret` referenced as `decryption.secretRef`.
- ArgoCD: requires the `argocd-vault-plugin` sidecar or the ArgoCD `inline` Helm values pattern; configure plugin-specific `sourceHydrator` if applicable.
- Kustomize: uses the `sops` secret generator plugin; key supplied through a `SOPS_GPG_KEY` / `SOPS_AGE_KEY_FILE` path.
- Always keep encryption keys out of the Git repository; store them in the cluster's `Secret` store or in the GitOps controller's secret backend.

## Key rotation

SOPS supports two rotation paths:

- Add recipient (`--add-recipient`): extend the recipient set without re-encrypting existing values; required when onboarding a new key.
- Re-encrypt (`--rotate-in-place` or `--encrypt --input ...`): re-encrypt existing values to a new key set; required when retiring a compromised key.
- Rotation cadence: rotate KMS keys on the cloud provider's recommended cadence; rotate age keys on a 180-day cycle or immediately on suspected compromise.
- Keep at least one previous recipient active until all clusters and CI runners have refreshed their key material.
- Treat key rotation as a controlled change: open a ticket, run in staging first, then roll cluster-by-cluster.

## SOPS + Kustomize / FluxCD / ArgoCD patterns

- Kustomize secret generator: `sops:`-prefixed `secretGenerator` entries; SOPS decrypts at apply time using the controller's key material.
- FluxCD: configure `decryption: provider: sops` on each `Kustomization`; reference the key material `Secret` in the same namespace.
- ArgoCD: enable the SOPS plugin under `configs.cm.yaml`; configure the `argocd-vault-plugin` repository credentials and the `SOPS_AGE_KEY_FILE` path inside the repo-server pod.
- Avoid committing decrypted manifests; let the controller decrypt at apply time so the Git source remains encrypted.
- Use `.sops.yaml` configuration to bind file path patterns to specific key sources; treat this file as code-reviewed infrastructure.

## Detached vs inline secrets

SOPS supports two placement patterns for encrypted secrets:

- Inline: encrypted values live in the same manifest file as the Kubernetes resource (e.g., a `Deployment` with a SOPS-encrypted `env.valueFrom`). Convenient for tightly coupled workloads.
- Detached: a separate SOPS file is referenced by the workload (e.g., a `Secret` manifest whose `data:` block is generated from a `secrets.enc.yaml`). Cleaner separation, easier auditing.
- Prefer detached for shared credentials and inline for single-workload secrets.
- Whichever pattern is used, the decrypted secret must still flow through the standard Kubernetes `Secret` materialization path before reaching the workload.

## Audit and decryption logging

- SOPS does not produce runtime decryption logs by default; enable `SOPS_LOG=debug` in CI runners only (it writes key material fingerprints to stderr).
- Forward GitOps controller logs to the central log pipeline and alert on `decrypt` failures or unexpected `sops` provider errors.
- Audit the `.sops.yaml` file on the same cadence as other access control files; recipients must be reviewed every cycle.
- Treat any decryption attempt outside a known CI runner, controller pod, or operator as a security event.
- Cloud-side KMS decrypt calls are already auditable in AWS CloudTrail, GCP Cloud Audit Logs, and Azure Activity Log; correlate SOPS decrypt failures with KMS audit events when investigating.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07. The Knowledge Engineering owner re-validates the encryption format policy, key source matrix, and GitOps integration patterns on each cycle and on every SOPS minor release.

## References

- SOPS docs: `https://getsops.io/`
- SOPS repo: `https://github.com/getsops/sops`
- Releases: `https://github.com/getsops/sops/releases`
- age encryption: `https://github.com/FiloSottile/age`
- FluxCD SOPS integration: `https://fluxcd.io/flux/guides/mozilla-sops/`
- ArgoCD SOPS integration: `https://argo-cd.readthedocs.io/en/stable/user-guide/private-repositories/`
