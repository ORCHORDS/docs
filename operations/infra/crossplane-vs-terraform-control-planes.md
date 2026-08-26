# crossplane-vs-terraform-control-planes

**Issue:** Choosing between Terraform (plan/apply pipeline) and Crossplane (Kubernetes-native reconciliation) for infrastructure provisioning — and avoiding the failure modes of each
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
Platform teams default to Terraform because it is familiar, then hit its operational ceiling: every developer infrastructure request becomes a CI pipeline run, state-file locking conflicts appear under concurrency, and drift is only detected when someone remembers to run a plan. Meanwhile teams that adopted Crossplane struggle with slow compositions, opaque errors in composite resources (XRs), and providers lagging behind cloud APIs. The 2026 platform-engineering consensus: use both — Terraform for foundational/one-time infra, Crossplane for developer-facing self-service that needs continuous reconciliation.

## Pattern / Solution
Match the tool to the change cadence and ownership:

| Dimension | Terraform | Crossplane |
|---|---|---|
| Execution model | Batch: plan → apply → exit | Continuous: controller reconciles |
| State | External state file (+ locking) | etcd (cluster itself) |
| Drift | Detected only when plan runs | Reverted automatically by controller |
| Concurrency | State-lock serialization | Per-claim, no central lock |
| Day-2 ops | Imperative follow-ups | Built into provider controllers |
| Best for | VPCs, DNS, org policy, foundations | App-tier infra: buckets, DBs, queues per team |

**Crossplane minimal setup:**
```bash
helm upgrade --install crossplane \
  --namespace crossplane-system --create-namespace \
  crossplane-stable/crossplane

# Install a provider, then a managed resource
cat <<EOF | kubectl apply -f -
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-s3
spec:
  package: xpkg.upbound.io/upbound/provider-aws-s3:v1.x
EOF
```

**Self-service via Claim (developer-facing):**
```yaml
apiVersion: s3.example.io/v1alpha1
kind: Bucket
metadata:
  name: team-a-artifacts
spec:
  compositionSelector:
    matchLabels:
      provider: aws
  writeConnectionSecretToRef:
    name: team-a-artifacts-creds
  # developer sees 3 fields, not 40
```

**Keep Terraform for what it is good at.** Bootstrap the cluster, the VPC it lives in, and Crossplane provider IRSA roles with Terraform; then let Crossplane own everything above that line. This is the "Terraform builds the platform, Crossplane runs the platform" split.

**Guardrails for Crossplane at scale:**
- One Composition per service tier with `compositionSelector` labels — do not let teams select raw managed resources
- Set `providerConfigRef` via a policy, never per-claim
- Watch XR conditions: `kubectl get bucket team-a-artifacts -o yaml | kubectl neat` — the `status.conditions` array is where real errors surface

## Gotchas
- etcd is the state store: 1.5 MB object limit and 8 MB total request limit. XRs embedding large inline configs (e.g., big IAM policy documents) blow up API server writes Terraform never would have.
- Deleting a Crossplane `Provider` or `ProviderConfig` before its managed resources finalizes hangs everything with `DeletionBlockedByExternalResource`. Always drain managed resources first.
- Crossplane providers lag cloud APIs by months. New services/features arrive in Terraform (or the cloud provider's own IaC, e.g. OpenTofu/CDK) first — verify the upbound provider supports the resource before promising it.
- Reconciliation cuts both ways: a manual "quick fix" in the console is reverted within minutes. Teams used to console hotfixes find this surprising; document it or set `deletionPolicy: Orphan` where humans must intervene.
- Crossplane upgrades are cluster upgrades: provider package versions, composition revisions, and the core CRDs move together. Pin versions and test in staging cluster exactly as you would a K8s minor upgrade.
- Terraform `for_each` + templating can express fan-out that Crossplane Compositions make genuinely hard (cross-resource naming schemes, computed lookups). Do not force it.
- Cost: every Crossplane managed resource polls the cloud API. Hundreds of XRs across many clusters can hit API rate limits (AWS throttle errors appear as `ReconcileError` in events, not obvious logs).

## Related
- `platform-engineering-idp.md`
- `iac-best-practices.md`
- `terraform-modules.md`
- `gitops-argocd-flux.md`
