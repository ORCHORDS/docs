# gcp-cloud-run-patterns

**Issue:** Cloud Run production patterns for concurrency, min instances, and traffic splitting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloud Run services cold-start on every request, run out of memory, or route all traffic to a single revision during deploys.

## Pattern / Solution
```yaml
# cloudbuild.yaml deploy step
- name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
  args:
    - gcloud
    - run
    - deploy
    - my-service
    - --image=us-docker.pkg.dev/PROJECT/repo/app:$SHORT_SHA
    - --region=us-central1
    - --platform=managed
    - --min-instances=3          # keep warm — eliminates cold starts
    - --max-instances=100
    - --concurrency=80           # requests per container
    - --cpu=2
    - --memory=2Gi
    - --cpu-throttling           # remove for always-on CPU (WebSockets, SSE)
    - --no-traffic               # deploy without shifting traffic
```

Canary traffic split:
```bash
gcloud run services update-traffic my-service \
  --to-revisions=my-service-v2=10,my-service-v1=90 \
  --region=us-central1

# After validation, promote
gcloud run services update-traffic my-service \
  --to-latest \
  --region=us-central1
```

Direct VPC egress (for Cloud SQL, Memorystore access):
```bash
gcloud run services update my-service \
  --vpc-connector=projects/PROJECT/locations/us-central1/connectors/my-connector \
  --vpc-egress=private-ranges-only
```

## Gotchas
- `--cpu-throttling` (default) throttles CPU outside request handling — breaks background goroutines/threads
- Concurrency >1 means your container must be thread-safe
- Min instances incur cost even when idle — use only for latency-critical services
- Cloud Run jobs (not services) are for batch workloads — no HTTP ingress, timeout up to 24 h

## Related
- `gcp-cloud-sql-patterns.md`
- `gcp-iam-workload-identity.md`
- `auto-scaling-policies.md`
