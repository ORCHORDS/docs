# Crossplane Cloudflare Provider Kubernetes Operators
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Platform teams running Kubernetes as their control plane want to manage Cloudflare
resources (Workers scripts, KV namespaces, DNS records, R2 buckets) using the same
GitOps pipeline that provisions other cloud resources – without maintaining a separate
Terraform or Pulumi workflow. Crossplane lets you declare Cloudflare resources as
Kubernetes CRDs, track reconciliation status with `kubectl`, and compose Cloudflare
infra into reusable platform abstractions (XRDs).

## Context

Upbound publishes `provider-cloudflare` (formerly `upjet-provider-cloudflare`), a
Crossplane provider generated from the Cloudflare Terraform provider using the Upjet
framework. It exposes Cloudflare resources as Kubernetes CRDs that Crossplane's
provider controller continuously reconciles against the Cloudflare API. State is stored
in the Kubernetes cluster (etcd); Cloudflare API credentials are injected via a
Kubernetes Secret referenced by a `ProviderConfig`.

Crossplane version: v1.17+
Provider version: `xpkg.upbound.io/upbound/provider-cloudflare:v0.5.x`

## Installing Crossplane and the Cloudflare Provider

```bash
# Install Crossplane into the cluster
helm repo add crossplane-stable https://charts.crossplane.io/stable
helm repo update
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --version 1.17.1 \
  --wait
```

```yaml
# crossplane/provider-cloudflare.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-cloudflare
spec:
  package: xpkg.upbound.io/upbound/provider-cloudflare:v0.5.1
  installRuntimeConfig:
    spec:
      resources:
        limits:
          memory: 256Mi
        requests:
          cpu: 100m
          memory: 128Mi
```

```bash
kubectl apply -f crossplane/provider-cloudflare.yaml
kubectl wait provider/provider-cloudflare --for=condition=Healthy --timeout=120s
```

## Configuring the Cloudflare Provider Credentials

```yaml
# crossplane/cloudflare-credentials-secret.yaml
# Pre-create via: kubectl create secret generic cloudflare-credentials \
#   --namespace crossplane-system \
#   --from-literal=credentials='{"api_token":"<CF_API_TOKEN>"}'
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-credentials
  namespace: crossplane-system
type: Opaque
stringData:
  credentials: |
    {
      "api_token": "${CLOUDFLARE_API_TOKEN}"
    }
```

```yaml
# crossplane/providerconfig-cloudflare.yaml
apiVersion: cloudflare.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: cloudflare-credentials
      key: credentials
```

```bash
# Inject real token and apply
envsubst < crossplane/cloudflare-credentials-secret.yaml \
  | kubectl apply -f -
kubectl apply -f crossplane/providerconfig-cloudflare.yaml
```

## Managing a KV Namespace as a CRD

```yaml
# crossplane/managed/kv-namespace.yaml
apiVersion: workerskv.cloudflare.upbound.io/v1alpha1
kind: Namespace
metadata:
  name: my-app-cache
  annotations:
    crossplane.io/external-name: "my-app-cache-production"  # Cloudflare title
spec:
  forProvider:
    accountId: "a1b2c3d4e5f6..."
    title: "my-app-cache-production"
  providerConfigRef:
    name: default
```

```bash
kubectl apply -f crossplane/managed/kv-namespace.yaml

# Watch reconciliation
kubectl get namespace.workerskv my-app-cache -o wide
kubectl describe namespace.workerskv my-app-cache | tail -20
```

## Deploying a Worker Script

```yaml
# crossplane/managed/workers-script.yaml
apiVersion: workers.cloudflare.upbound.io/v1alpha1
kind: Script
metadata:
  name: api-worker
spec:
  forProvider:
    accountId: "a1b2c3d4e5f6..."
    name: "api-worker-production"
    content: |
      export default {
        async fetch(request, env) {
          const val = await env.CACHE.get("greeting");
          return new Response(val ?? "hello world");
        }
      };
    module: true
    kvNamespaceBindings:
      - name: CACHE
        # Reference the KV namespace by its Cloudflare ID via a crossplane reference
        namespaceIdRef:
          name: my-app-cache
  providerConfigRef:
    name: default
```

## Composing a Platform Abstraction with XRD

Define an XRD so application teams request a "WorkerApp" without knowing Cloudflare
resource details:

```yaml
# crossplane/xrd/workerapp.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xworkerapps.platform.example.com
spec:
  group: platform.example.com
  names:
    kind: XWorkerApp
    plural: xworkerapps
  claimNames:
    kind: WorkerApp
    plural: workerapps
  versions:
    - name: v1alpha1
      served: true
      referenceable: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                workerName:
                  type: string
                accountId:
                  type: string
                kvTitle:
                  type: string
              required: [workerName, accountId, kvTitle]
```

```yaml
# crossplane/composition/workerapp-composition.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: workerapp-cloudflare
spec:
  compositeTypeRef:
    apiVersion: platform.example.com/v1alpha1
    kind: XWorkerApp
  resources:
    - name: kv-namespace
      base:
        apiVersion: workerskv.cloudflare.upbound.io/v1alpha1
        kind: Namespace
        spec:
          forProvider:
            accountId: ""
            title: ""
          providerConfigRef:
            name: default
      patches:
        - type: FromCompositeFieldPath
          fromFieldPath: spec.accountId
          toFieldPath: spec.forProvider.accountId
        - type: FromCompositeFieldPath
          fromFieldPath: spec.kvTitle
          toFieldPath: spec.forProvider.title
    - name: worker-script
      base:
        apiVersion: workers.cloudflare.upbound.io/v1alpha1
        kind: Script
        spec:
          forProvider:
            accountId: ""
            name: ""
            content: "export default { async fetch(r,e) { return new Response('ok'); } }"
            module: true
          providerConfigRef:
            name: default
      patches:
        - type: FromCompositeFieldPath
          fromFieldPath: spec.accountId
          toFieldPath: spec.forProvider.accountId
        - type: FromCompositeFieldPath
          fromFieldPath: spec.workerName
          toFieldPath: spec.forProvider.name
```

Application team claim (no Cloudflare knowledge required):

```yaml
# app-team/claim.yaml
apiVersion: platform.example.com/v1alpha1
kind: WorkerApp
metadata:
  name: checkout-service
  namespace: team-payments
spec:
  workerName: checkout-worker-prod
  accountId: a1b2c3d4e5f6...
  kvTitle: checkout-cache-prod
  compositionRef:
    name: workerapp-cloudflare
```

## Anti-patterns

- **Storing Worker bundle content inline in the CRD** – YAML size limits (~1 MB) and
  Kubernetes etcd storage make this impractical for real bundles. Prefer wrangler for
  bundle deployment and Crossplane for supporting resources (KV, R2, DNS).
- **Using Crossplane for high-churn resources** – Crossplane reconciliation runs on a
  poll interval (default 10 min). It is not suitable for per-deploy Worker script
  updates; use wrangler or Pulumi Automation API for the script, Crossplane for durable
  infra (namespaces, buckets, DNS).
- **Granting a full-account Cloudflare token to the provider** – scope tokens to
  required resource types per environment; store staging and production provider configs
  in separate Kubernetes namespaces.

## Gotchas

- `provider-cloudflare` coverage lags the Terraform provider; check the provider's
  CRD list before assuming a resource type exists. Missing types require Terraform or
  wrangler as a complement.
- Crossplane does not support `terraform import`-equivalent bulk import; existing
  Cloudflare resources must be adopted by creating Managed Resources with
  `crossplane.io/external-name` set to the existing resource's Cloudflare ID.
- Deleting a Managed Resource deletes the corresponding Cloudflare resource unless you
  set `spec.deletionPolicy: Orphan` first.
- Composition patches only support JSONPath-style field references; complex
  transformations require a Function (FunctionPipeline) with Go or Python logic.

## Verification

```bash
# Check all managed resources for the Cloudflare provider
kubectl get managed -o wide | grep cloudflare

# Check individual resource health
kubectl get namespace.workerskv my-app-cache \
  -o jsonpath='{.status.conditions}' | jq .

# Confirm resource exists in Cloudflare API
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/storage/kv/namespaces" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[] | select(.title == "my-app-cache-production")'

# Events on a failed reconciliation
kubectl describe namespace.workerskv my-app-cache | grep -A 5 Events
```

## Related

- `crossplane-vs-terraform-control-planes.md` – Crossplane vs Terraform architectural tradeoffs
- `kubernetes-operator-pattern.md` – controller reconciliation model underpinning Crossplane
- `pulumi-cloudflare-workers-infrastructure-as-code.md` – Pulumi as Crossplane alternative
- `cloudflare-workers-kv-namespace-terraform.md` – Terraform path for KV namespaces
- `gitops-argocd-flux.md` – GitOps delivery of Crossplane manifests via Argo/Flux

## Sources

- https://github.com/upbound/provider-cloudflare
- https://marketplace.upbound.io/providers/upbound/provider-cloudflare
- https://docs.crossplane.io/latest/concepts/providers/
- https://docs.crossplane.io/latest/concepts/composite-resource-definitions/
- https://docs.crossplane.io/latest/concepts/compositions/
- https://docs.upbound.io/providers/provider-cloudflare/
