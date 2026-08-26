# gcp-iam-workload-identity

**Issue:** Using Workload Identity Federation to eliminate service account key files in GKE and CI/CD
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service account JSON key files committed to repos, rotated manually, or leaked in container images. Workload Identity eliminates the need for key files entirely.

## Pattern / Solution
GKE Workload Identity (bind K8s ServiceAccount to GCP ServiceAccount):
```bash
# Enable Workload Identity on cluster
gcloud container clusters update CLUSTER \
  --workload-pool=PROJECT.svc.id.goog

# Create GCP service account
gcloud iam service-accounts create my-app-sa

# Bind K8s SA to GCP SA
gcloud iam service-accounts add-iam-policy-binding \
  my-app-sa@PROJECT.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:PROJECT.svc.id.goog[NAMESPACE/KSA_NAME]"
```

```yaml
# K8s ServiceAccount annotation
apiVersion: v1
kind: ServiceAccount
metadata:
  name: my-app
  namespace: production
  annotations:
    iam.gke.io/gcp-service-account: my-app-sa@PROJECT.iam.gserviceaccount.com
```

GitHub Actions → GCP (no keys):
```yaml
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: projects/123/locations/global/workloadIdentityPools/github/providers/github
    service_account: deployer@PROJECT.iam.gserviceaccount.com

- uses: google-github-actions/setup-gcloud@v2
```

Create the pool:
```bash
gcloud iam workload-identity-pools create github \
  --location=global

gcloud iam workload-identity-pools providers create-oidc github \
  --location=global \
  --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='my-org/my-repo'"
```

## Gotchas
- Workload Identity requires GKE metadata server — pods must not block 169.254.169.254
- The attribute condition is a security boundary — lockdown to specific repos/branches in CI
- GOOGLE_APPLICATION_CREDENTIALS env var should not be set when using Workload Identity
- Cross-project: GCP SA must be in the project where the pool is defined

## Related
- `aws-iam-least-privilege.md`
- `secrets-management-comparison.md`
- `gcp-cloud-run-patterns.md`
