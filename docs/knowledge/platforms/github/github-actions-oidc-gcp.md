# github-actions-oidc-gcp

**Issue:** Authenticating GitHub Actions to Google Cloud using Workload Identity Federation (OIDC)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service account JSON keys stored as secrets are long-lived and carry high leak risk. Workload Identity Federation eliminates the need for key files.

## Pattern / Solution
GCP setup (one-time):
```bash
# Create Workload Identity Pool
gcloud iam workload-identity-pools create "github-pool" \
  --project=my-project --location="global"

# Create OIDC Provider within the pool
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project=my-project \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='myorg/myrepo'"

# Bind to a service account
gcloud iam service-accounts add-iam-policy-binding sa@my-project.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUM/locations/global/workloadIdentityPools/github-pool/attribute.repository/myorg/myrepo"
```
Workflow:
```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: 'projects/123/locations/global/workloadIdentityPools/github-pool/providers/github-provider'
      service_account: 'sa@my-project.iam.gserviceaccount.com'
  - uses: google-github-actions/setup-gcloud@v2
  - run: gcloud storage ls
```

## Gotchas
- Project number (not ID) is required in the Workload Identity Provider resource path.
- `attribute-condition` restricts which repos can impersonate the service account.
- `id-token: write` permission is mandatory.
- The `google-github-actions/auth` action handles token exchange automatically.

## Related
- `github-actions-oidc-aws.md`
- `github-actions-oidc-cloudflare.md`
