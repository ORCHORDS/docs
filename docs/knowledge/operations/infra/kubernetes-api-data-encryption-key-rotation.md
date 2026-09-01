---
title: "API Data Encryption and Key Rotation"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# API Data Encryption and Key Rotation

## API semantics

The API server's `--encryption-provider-config` points to an `apiserver.config.k8s.io/v1` `EncryptionConfiguration`. `resources` entries are processed in order; providers are attempted in order for reads, and the first provider encrypts new writes. Resource names are plural, optionally qualified by API group. Providers include `identity`, `aesgcm`, `aescbc`, `secretbox`, and KMS v2 as documented for the target release. Never reuse nonce-sensitive key material, and keep `identity` last only during a deliberate plaintext migration.

## Minimal configuration

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
- resources: ["secrets", "configmaps"]
  providers:
  - aescbc:
      keys:
      - name: key-2026-09
        secret: ${NEW_ENCRYPTION_KEY_BASE64}
  - aescbc:
      keys:
      - name: key-2026-06
        secret: ${PREVIOUS_ENCRYPTION_KEY_BASE64}
  - identity: {}
```

## Ordering, versions, and edge cases

All API servers must receive the new read-capable configuration before writes switch. Restarting one replica at a time with inconsistent provider lists can create ciphertext another replica cannot read. Adding a key only changes new writes; rewrite existing objects through the API, for example `kubectl get secrets --all-namespaces -o json | kubectl replace -f -`. That command exposes data to client memory and requires careful logging controls. Back up etcd first and verify restore.

## Deployment, evidence, and rollback

Write a canary Secret, then query etcd directly and verify an `k8s:enc:<provider>:<keyname>:` prefix and no plaintext. Track API-server decrypt errors and KMS gRPC health/latency where used. After rewrite, scan selected keys for old prefixes, test reads through every API-server endpoint, then remove the old provider. Roll back by restoring the old decrypt provider after the new one, not by placing `identity` first; retain old keys until restore tests prove retirement safe.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Rotation sequence

Use four explicit phases: add new decrypt capability everywhere; place the new provider/key first everywhere; rewrite; retire. Compare config hashes and API-server readiness between phases. For high-volume kinds, paginate and rate-limit rewrites to avoid overwhelming etcd or audit storage. Include CRD resources only when explicitly named and supported by the configuration; `secrets` does not imply arbitrary sensitive custom resources.

Backups must retain every key required by ciphertext in that snapshot. Test a restore into an isolated control plane using the matching encryption configuration. File permissions and distribution of locally stored symmetric keys are part of the control. KMS v2 uses an external plugin and key identifiers, so preserve plugin configuration and external-key lifecycle with the backup. Alert on `StorageError`, decrypt failures, KMS health failure, and old ciphertext prefixes. Never delete an old KMS key merely because live-object scanning is clean; historical etcd backups may still require it.

## Sources

- [Encryption at rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
- [KMS](https://kubernetes.io/docs/tasks/administer-cluster/kms-provider/)
