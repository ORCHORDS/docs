# artifact-versioning-strategy

**Issue:** How to version build artifacts (Docker images, npm packages, binaries) to enable reliable deploys and rollbacks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Using `latest` tags or branch names as artifact versions means deploys are non-deterministic — the same tag can point to different code tomorrow. A versioning strategy ensures every deployed artifact is immutable and traceable to a commit.

## Pattern / Solution
**Versioning hierarchy (use the most specific that applies)**
1. Semantic version tag (`v2.41.3`) — for released artifacts
2. Git SHA (`sha-a3f8c21`) — for every commit artifact
3. Branch + short SHA (`main-a3f8c21`) — for branch builds
4. PR number + SHA (`pr-142-a3f8c21`) — for PR preview builds

**Never use as a production artifact version**
- `latest`
- Branch name alone (`main`, `develop`)
- Date strings (`2026-08-11`) — non-monotonic across timezones

**CI tagging pattern (Docker)**
```yaml
- name: Set image tags
  id: meta
  uses: docker/metadata-action@v5
  with:
    images: ghcr.io/org/api
    tags: |
      type=semver,pattern={{version}}
      type=semver,pattern={{major}}.{{minor}}
      type=sha,prefix=sha-,format=short
      type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

- name: Build and push
  uses: docker/build-push-action@v5
  with:
    tags: ${{ steps.meta.outputs.tags }}
```

**Artifact registry retention policy**
- Keep all semver-tagged images indefinitely
- Keep SHA-tagged images for 30 days
- Delete PR images 7 days after PR close

**Traceability**
- Embed the git SHA as an image label and as an env var the app serves on `/healthz`
- Store artifact→deploy mappings in your deployment system (Argo CD, ECS) for audit trail

## Gotchas
- Docker manifest lists (multi-arch) share a tag but have different digests per platform — always reference by digest for reproducibility in production
- npm's `latest` dist-tag is mutable; use exact versions in `package.json` for production dependencies
- Artifact signing (cosign) should be applied at build time, not added later

## Related
- `container-image-tagging.md`
- `semver-best-practices.md`
- `docker-multi-stage-build.md`
- `rollback-runbook.md`
