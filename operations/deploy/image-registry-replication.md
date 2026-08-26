# image-registry-replication

**Issue:** Container image registry replication, mirroring, garbage collection, and retention across regions
**Date:** 2026-08-13
**Status:** documented

## Symptom
You deploy to multiple regions. A pod in `eu-west-1` pulls an image
that only lives in `us-east-1`. The pull crosses an ocean, takes 45
seconds, and times out during a rolling update. Or worse: you delete
a tag in the primary registry, a replica still serves a stale copy,
and two regions run different code with the same tag.

## Root cause
**A single-region registry is a single point of failure and a latency
bottleneck.** Replicate images to every region where workloads run,
and garbage-collect unreferenced blobs so storage cost does not grow
forever.

**Source:** Portainer — DevOps Containers 2026; Checkmarx — Container
Security 2026 (registry hygiene & trusted-base-image policy).

## The "geo-replication" pattern

For a multi-region cluster, replicate the registry:

```bash
# Harbor: create a replication rule to a remote registry
harbor-cli replication create \
  --name us-to-eu \
  --source registry.internal/core \
  --dest registry-eu.internal/core \
  --mode pull \
  --trigger scheduled \
  --cron "0 */6 * * *"   # sync every 6h

# Trigger an immediate replication run
harbor-cli replication run us-to-eu
```

Each region pulls from its local replica. The pull is fast, and a
WAN outage between regions does not block a rolling update.

## The "pull-through cache" pattern

For a lightweight mirror without a full registry, use a pull-through
cache. The first pull fetches upstream; later pulls are local:

```yaml
# Docker Registry v2 as a pull-through cache
version: 0.1
proxy:
  remoteurl: https://registry-1.docker.io
storage:
  delete:
    enabled: true
  cache:
    blobdescriptor: inmemory
http:
  addr: :5000
```

```bash
# Run the cache in each region
docker run -d -p 5000:5000 \
  -v /data/registry:/var/lib/registry \
  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io \
  registry:2
```

The cache is read-mostly. It is not a source of truth.

## The "immutable tags" pattern

For reproducibility, never re-push the same tag:

```bash
# BAD: re-tagging :v2 overwrites the prior artifact
docker build -t registry/core:prod .
docker push registry/core:prod   # what is "prod" now?

# GOOD: tag with git SHA + build number
docker build -t registry/core:2.4.1-$(git rev-parse --short HEAD)-b421 .
docker push registry/core:2.4.1-abc1234-b421
```

A replica can never serve "a different version under the same tag"
because the tag is never overwritten.

## The "garbage collection" pattern

For storage cost, delete unreferenced blobs:

```bash
# Harbor: enable GC on a schedule (runs read-only mode)
harbor-cli gc start --dry-run      # preview what will be freed
harbor-cli gc start                # actually run

# Raw distribution v2: mark+delete, then GC
docker exec registry registry garbage-collect /etc/docker/registry/config.yml --delete-untagged
```

**Gotcha:** GC requires the registry to be read-only during the run.
Run it in a maintenance window or on a replica you can briefly take
offline.

## The "retention policy" pattern

For lifecycle, delete old tags automatically:

```bash
# Harbor: retention rule — keep last 10 tags per repo, delete the rest
harbor-cli retention create \
  --repository "core/*" \
  --algorithm "last_n" \
  --n 10 \
  --schedule "0 2 * * 0"   # weekly Sunday 02:00

# ECR lifecycle policy (JSON): expire untagged after 7 days, keep 20 tagged
aws ecr put-lifecycle-policy \
  --repository-name core \
  --lifecycle-policy-text file://ecr-lifecycle.json
```

```json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "expire untagged",
      "selection": { "tagStatus": "untagged", "countType": "sinceImagePushed", "countUnit": "days", "countNumber": 7 },
      "action": { "type": "expire" }
    },
    {
      "rulePriority": 2,
      "description": "keep last 20 tagged",
      "selection": { "tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 20 },
      "action": { "type": "expire" }
    }
  ]
}
```

## The "promotion-only registry" pattern

For supply-chain safety, the prod registry is write-once and only
accepts promoted artifacts from staging:

```bash
# Copy (not rebuild) the promoted image to prod
crane copy staging.internal/core:2.4.1-abc1234-b421 \
         prod.internal/core:2.4.1-abc1234-b421

# Lock the prod repo to promoted-only via registry policy
# (Harbor: disable push for non-promotion service accounts)
```

You never build directly into prod. The SBOM and signature travel
with the copied manifest.

## Verification
- **Test:** Pull from each region's replica succeeds and is local
  (`time kubectl run test --image=...`).
- **Test:** GC dry-run reports unreferenced blobs without deleting.
- **Test:** Retention rule preserves the last N tags.
- **Audit:** Quarterly review of storage cost vs. tag count.

## Gotchas
- **The "re-tagged :latest" anti-pattern.** A replica may serve the
  old manifest for hours due to cache TTL. Use immutable, content-
  addressed tags.
- **The "GC during writes" anti-pattern.** Running GC while images
  are pushed can corrupt the registry. Make it read-only first.
- **The "no retention" anti-pattern.** Storage cost grows unbounded;
  a year of CI builds can reach terabytes. Set a retention policy
  before it hurts.
- **The "cross-region pull" anti-pattern.** If `time kubectl run`
  shows a multi-second pull, the replica is missing or misconfigured.

## Related
- `container-image-tagging.md`
- `supply-chain-security-sbom-signing.md`
- `multi-region-deployment.md`
- `multi-arch-builds-arm-x86.md`
- `docker-layer-caching-ci.md`
