# Kubernetes pod-certificate projection rotation

**Issue:** Long-lived TLS secrets require manual rotation and can leave workloads using mismatched or expired key/certificate files.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

For Kubernetes 1.36, enable the PodCertificateRequest API and feature gate deliberately, authorize a specific signer, constrain accepted key type and maximum lifetime, and prefer credentialBundlePath so key and chain are read atomically. Make applications watch and reload the file, validate the chain and intended identity, and reject unrecognized user annotations in the signer.

## Verification

Test initial issuance blocking, signer denial, short lifetimes, atomic rotation, application reload, expired/revoked chains, kubelet restart, node drain, and separate-file mismatch handling. Confirm private keys never enter logs or API objects.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://kubernetes.io/docs/concepts/storage/projected-volumes/#podcertificate-projected-volumes)
