# kubernetes-config-maps-secrets

**Issue:** Safely injecting configuration and secrets into Kubernetes workloads
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hardcoded config in images blocks promotion across environments. Secrets in ConfigMaps or Git expose credentials. This entry covers safe patterns for both.

## Pattern / Solution
ConfigMap from file directory:
```bash
kubectl create configmap app-config \
  --from-file=./config/ \
  --dry-run=client -o yaml | kubectl apply -f -
```

Mount ConfigMap as volume (live reload on change):
```yaml
volumes:
- name: config
  configMap:
    name: app-config
containers:
- name: myapp
  volumeMounts:
  - name: config
    mountPath: /etc/app/config
    readOnly: true
```

ExternalSecrets with AWS Secrets Manager:
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-credentials
  namespace: production
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: ClusterSecretStore
  target:
    name: db-credentials
    creationPolicy: Owner
  data:
  - secretKey: password
    remoteRef:
      key: production/myapp/db
      property: password
```

Reference the generated Secret in a Deployment:
```yaml
env:
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: db-credentials
      key: password
```

Seal a secret for GitOps (Sealed Secrets):
```bash
kubeseal --format yaml < secret.yaml > sealed-secret.yaml
# sealed-secret.yaml is safe to commit; only the in-cluster controller can decrypt
```

## Gotchas
- Secrets are base64-encoded, NOT encrypted, in etcd by default — enable EncryptionConfiguration or use KMS provider
- Environment variable injection does not update on ConfigMap change; volume mounts do (with inotify-aware apps)
- `secretKeyRef` mounts fail silently if the Secret key doesn't exist — pod enters CrashLoopBackOff
- Never `kubectl get secret -o yaml` and commit the output; rotate immediately if this happens
- Sealed Secrets are cluster-specific; you cannot decrypt a sealed secret in a different cluster without the private key

## Related
- `secrets-in-deploy-2026.md`
- `kubernetes-namespace-isolation.md`
- `kubernetes-rbac-patterns.md`
