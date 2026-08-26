# image-pull-secrets-rotation

**Issue:** Rotating Kubernetes image pull secrets and registry credentials without breaking running pods
**Date:** 2026-08-13
**Status:** documented

## Symptom
Your team's registry deploy token leaks into a Slack thread, or
security mandates 90-day credential rotation. You rotate the token in
the registry. Within an hour, new pods fail to start with
`ImagePullBackOff: 401 Unauthorized`. Existing pods keep running —
until the next rolling update, when the whole deployment goes red.

## Root cause
**A Kubernetes `imagePullSecrets` references a Secret by name, not
by content.** Rotating the credential means updating the Secret, but
pods that already pulled their image never re-read it. New pods (new
nodes, scale-outs, restarts) hit the stale credential and fail.
Rotation must be: update Secret → trigger a controlled rollout →
verify every replica pulled successfully.

**Source:** Orca Security — Container Security Best Practices 2026
(credential rotation & secret hygiene); Checkmarx 2026 (remove
secrets from images, rotate deploy tokens).

## The "secret rotation" pattern

For rotating the registry credential, update the Secret in place:

```bash
# 1. Create the new registry token (Harbor / ECR / GHCR / GitLab)
#    Example: ECR get-login-password, valid 12h
aws ecr get-login-password --region us-east-1 > /tmp/new-token

# 2. Build the new .dockerconfigjson
kubectl create secret docker-registry regcred \
  --docker-server=registry.internal \
  --docker-username=ci-deploy \
  --docker-password="$(cat /tmp/new-token)" \
  --docker-email=devops@example.com \
  --dry-run=client -o yaml | kubectl apply -f -
```

The Secret is updated. Existing pods are unaffected (image already
pulled). New pods use the new token.

## The "trigger a controlled rollout" pattern

After rotating, force every pod to re-pull so you know the new
credential works before a crisis does:

```bash
# Trigger a rolling restart — pods recreate and re-pull using the new Secret
kubectl rollout restart deployment/api -n prod
kubectl rollout restart deployment/worker -n prod
kubectl rollout restart deployment/web -n prod

# Watch the rollout
kubectl rollout status deployment/api -n prod --timeout=5m
```

If the new token is wrong, the rollout stalls here — in a controlled
way, not during a 3 a.m. incident.

## The "verify every pod pulled" pattern

Confirm no pod is still stuck on the old credential:

```bash
# Any pod still in ImagePullBackOff after rotation = stale secret
kubectl get pods -A -o wide | grep -iE "ImagePullBackOff|ErrImagePull"

# Check the events for a specific failing pod
kubectl describe pod <pod-name> | grep -A5 "Events:"
```

A clean result (no ImagePullBackOff pods) means rotation succeeded.

## The "service-account-bound secret" pattern

For not having to attach `imagePullSecrets` to every Deployment,
bind the secret to the namespace default ServiceAccount:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: default
  namespace: prod
imagePullSecrets:
  - name: regcred
```

Every pod in the namespace inherits the credential. Rotation is one
`kubectl apply` + one `rollout restart`, not N deployment edits.

## The "ExternalSecret + scheduled rotation" pattern

For fully automated 90-day rotation, drive the Secret from an
ExternalSecret backed by a vault (AWS Secrets Manager, Vault, GCP
Secret Manager) and let the vault rotate the underlying token:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: regcred-es
  namespace: prod
spec:
  refreshInterval: 1h           # re-sync from vault hourly
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: regcred               # the Secret pods actually reference
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {"auths":{"registry.internal":
            {"username":"{{.user}}","password":"{{.token}}"}}}
  data:
    - secretKey: user
      remoteRef:
        key: secret/data/registry/regcred
        property: username
    - secretKey: token
      remoteRef:
        key: secret/data/registry/regcred
        property: password
```

The vault rotates `registry/regcred` on a schedule; ExternalSecret
re-syncs hourly; you still need a periodic `rollout restart` to make
pods use the fresh value.

## The "long-lived token vs. short-lived STS" pattern

For ECR / cloud registries, prefer workload identity (short-lived
STS tokens) over a static deploy token:

```yaml
# IRSA: pod assumes an IAM role that can pull from ECR — no static token at all
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api
  namespace: prod
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111:role/ecr-puller
```

No Secret to rotate — the token is fetched per-pod and expires in
~1 hour. This is the 2026 recommended pattern where the registry
supports it.

## Verification
- **Test:** After rotation + rollout, `kubectl get pods -A` shows
  zero `ImagePullBackOff`.
- **Test:** Deliberately rotate to a bad token in staging — the
  rollout must stall (proving the verification step catches it).
- **Audit:** Quarterly — confirm no registry Secret older than 90
  days unless it uses workload identity.

## Gotchas
- **The "rotate then walk away" anti-pattern.** Updating the Secret
  does not restart pods. The next autoscale event fails. Always
  trigger a controlled rollout after rotating.
- **The "long-lived static token" anti-pattern.** A deploy token
  that never expires is a standing credential. Prefer workload
  identity or scheduled vault rotation.
- **The "secret in the image" anti-pattern.** Baking a registry
  token into a base image means rotating it requires rebuilding every
  image. Inject at runtime instead.
- **The "one Secret, many namespaces" anti-pattern.** A token valid
  across every namespace is over-privileged. Scope per-namespace.

## Related
- `kubernetes-config-maps-secrets.md`
- `gitops-secrets-management.md`
- `terraform-state-backend-security.md`
- `env-binding-precedence.md`
- `image-registry-replication.md`
