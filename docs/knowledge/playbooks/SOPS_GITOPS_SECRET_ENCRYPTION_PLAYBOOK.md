# SOPS GitOps Secret Encryption Playbook

## Purpose

Encrypt GitOps-managed YAML and JSON secrets with Mozilla SOPS using age or cloud KMS keys so that secret-bearing manifests remain readable and reviewable in Git while the secret values themselves stay encrypted at rest. The procedure covers key bootstrap, decryption integration with Flux or Argo, and key rotation.

## Audience

Platform engineers, security engineers, and GitOps controller operators (Flux and Argo CD) responsible for keeping secrets encrypted in Git without breaking reconciliation.

## Pre-conditions

- SOPS version pinned per `docs/knowledge/reference/SOPS_VERSION_GOVERNANCE.md`.
- An age keypair has been generated (`age-keygen -o keys.age`) OR a cloud KMS key ARN has been provisioned (AWS KMS, GCP KMS, Azure Key Vault).
- A `.sops.yaml` rules file exists at the repo root with per-path key mappings and creation rules.
- The GitOps controller can decrypt via a plugin (Flux `kustomize-controller` + SOPS, or Argo CD with the SOPS plugin installed) or via the `sops-operator`.
- SOPS CLI installed at the version recorded in the governance reference.

## Procedure

### Step 1 — Install and pin SOPS

1. Install the SOPS CLI at the pinned version; verify with `sops --version`.
2. Place the age private key in a sealed location (cluster `Secret`, sealed-secrets controller, or 1Password CLI) — never in Git.
3. For KMS-backed encryption, grant the decryption principal (cluster IAM role / workload identity) `kms:Decrypt` and `kms:GenerateDataKey` on the key.
4. Confirm `sops --version` and `age-keygen -y keys.age` succeed locally.

### Step 2 — Encrypt the first Secret manifest

5. Author the Secret manifest in plaintext under `manifests/<env>/<secret>.yaml`.
6. Encrypt in place: `sops --encrypt --in-place manifests/<env>/<secret>.yaml`.
7. Verify the file is now a SOPS document (starts with `sops:` metadata, data block is encrypted).
8. Commit and push the encrypted file; confirm the Git diff shows encrypted data, not plaintext.

### Step 3 — Configure `.sops.yaml` rules

9. Add per-path rules: `path_regex` matches the secret directory and `key_groups` lists the age recipient or KMS ARN allowed to decrypt.
10. Add a `creation_rule` that selects the key based on path so contributors cannot accidentally encrypt with the wrong key.
11. Validate the config with `sops --config .sops.yaml --encrypt --dry-run manifests/<env>/<secret>.yaml`.
12. Commit `.sops.yaml` to the repo and enforce it via CODEOWNERS.

### Step 4 — Integrate decryption with Flux or Argo

13. For Flux: configure `kustomize-controller` with the SOPS decryption provider and a Kubernetes Secret that holds the age private key (or workload identity for KMS).
14. For Argo CD: install the Argo CD SOPS plugin, mount the same age key / KMS identity into the repo-server, and set `data.kind: Secret` decryption in the Application manifest.
15. Confirm the controller can decrypt: `flux get kustomizations` or `argocd app diff <app>` shows reconciled resources.
16. Confirm the controller cannot decrypt with the wrong key: temporarily delete the key, observe a `Decryption failed` event, restore the key.

### Step 5 — Rotate an age key

17. Generate a new keypair: `age-keygen -o keys-new.age`.
18. Update `.sops.yaml` to add the new recipient under `key_groups` while keeping the old recipient until re-encryption completes.
19. Re-encrypt every secret with both keys: `sops updatekeys --yes manifests/<env>/<secret>.yaml` for each file.
20. Remove the old recipient from `.sops.yaml` once `grep -rL <old-fingerprint> manifests/` returns no matches.
21. Archive or destroy the old private key per the key-management policy.

### Step 6 — Decrypt-audit logging

22. Enable SOPS audit logging by exporting `SOPS_LOG_LEVEL=debug` or by piping through a structured logger in CI.
23. Forward SOPS events to the centralized log pipeline so that every `sops --decrypt` invocation is recorded with the operator and the file.
24. Review decrypt events weekly and alert on any decryption outside the approved GitOps reconciliation path.

## Rollback

- Revert `.sops.yaml` to the previous commit so path rules return to the prior key mapping.
- Run `sops --decrypt manifests/<env>/<secret>.yaml > /tmp/decrypted.yaml` and `diff` against the previous plaintext to confirm the rotation landed correctly.
- If a plaintext branch must be restored (for example, during a key-loss incident), create a new branch, decrypt every secret locally, commit, and rotate the downstream consumer's value before merge.
- Never commit a decrypted Secret to Git history without an immediate rotation: scrub history with `git filter-repo` and rotate the secret value in the upstream provider.

## References

- `docs/knowledge/reference/SOPS_VERSION_GOVERNANCE.md`
- Mozilla SOPS documentation: `https://github.com/getsops/sops`
- Mozilla SOPS age key guide: `https://github.com/getsops/sops#encrypting-using-age`
- Flux SOPS integration: `https://fluxcd.io/flux/guides/mozilla_sops/`
- Argo CD SOPS plugin: `https://argocd-cmp-plugin.readthedocs.io/en/stable/`
