# gitops-flux-cd

**Issue:** Bootstrapping and operating Flux CD for GitOps-driven Kubernetes deployments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams adopting GitOps need a pull-based delivery mechanism. Flux CD watches Git repos and reconciles cluster state automatically, eliminating manual `kubectl apply` steps and providing audit trails through Git history.

## Pattern / Solution
```bash
# Install Flux CLI
curl -s https://fluxcd.io/install.sh | sudo bash

# Bootstrap against a GitHub repo
flux bootstrap github \
  --owner=my-org \
  --repository=fleet-infra \
  --branch=main \
  --path=clusters/production \
  --personal

# Verify installation
flux check

# Create a GitRepository source
flux create source git podinfo \
  --url=https://github.com/stefanprodan/podinfo \
  --branch=master \
  --interval=1m

# Create a Kustomization that reconciles from the source
flux create kustomization podinfo \
  --source=podinfo \
  --path="./kustomize" \
  --prune=true \
  --interval=5m \
  --health-check="Deployment/podinfo.default"

# Watch reconciliation
flux get kustomizations --watch

# Force immediate reconciliation
flux reconcile kustomization podinfo --with-source

# Suspend reconciliation (e.g., during incident)
flux suspend kustomization podinfo
flux resume kustomization podinfo
```

Image automation (update image tags in Git):
```yaml
# ImageRepository
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageRepository
metadata:
  name: podinfo
  namespace: flux-system
spec:
  image: ghcr.io/stefanprodan/podinfo
  interval: 5m

# ImagePolicy
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: podinfo
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: podinfo
  policy:
    semver:
      range: '>=1.0.0'
```

## Gotchas
- Flux reconciles on interval AND on Git push webhooks; configure both for fast delivery
- `--prune=true` deletes resources removed from Git — confirm teams understand this before enabling
- SOPS or age encryption is required for secrets; never store plaintext in the GitOps repo
- Multi-tenancy requires separate namespaces per tenant with scoped `ServiceAccount` permissions
- Image automation commits back to Git, so the Flux bot needs write access to the repo

## Related
- `gitops.md`
- `gitops-argocd-patterns.md`
- `kubernetes-config-maps-secrets.md`
