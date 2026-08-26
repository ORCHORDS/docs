# GHCR Container Image Cleanup and Lifecycle Automation with Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Every merged PR in your Cloudflare Workers CI pipeline builds and pushes a container image
(e.g., a build environment, a test runner, or a service image) to GitHub Container Registry
(ghcr.io). Over months, hundreds of untagged and PR-specific images accumulate, consuming
storage quota and inflating billing. GitHub does not provide a native lifecycle policy (unlike
AWS ECR or GCR). You need an automated cleanup strategy.

Goals:
- Delete **untagged** images (dangling layers) immediately after they are superseded
- Retain the `latest` and all `v*` semver-tagged images indefinitely
- Purge PR preview images (`pr-123`) 7 days after the PR closes
- Run cleanup on a schedule via a Cloudflare Worker + Cron Trigger

---

## Context

GHCR stores images as **packages** under `ghcr.io/{owner}/{image-name}`. Each push creates a
**package version** (a digest). Tags are pointers to versions; a version without any tag is
"untagged". Untagged versions still consume storage.

The GitHub Packages REST API exposes:
- `GET /orgs/{org}/packages/container/{package_name}/versions` — list versions
- `DELETE /orgs/{org}/packages/container/{package_name}/versions/{version_id}` — delete one version
- `GET /user/packages/container/{package_name}/versions` — for user-scoped images

Required token scopes: `delete:packages` + `read:packages`. A fine-grained PAT or GitHub App
with **"Packages" (read and write)** permission works. The default `GITHUB_TOKEN` in Actions
has `packages:write` and `packages:read` during a workflow run but not `delete:packages` unless
granted explicitly.

---

## GitHub Actions: Immediate Untagged Cleanup After Push

Run after every image push to delete the old untagged layers in the same repo:

```yaml
# .github/workflows/cleanup-untagged.yml
name: Delete untagged GHCR images
on:
  workflow_run:
    workflows: ["Build and push image"]
    types: [completed]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    if: github.event.workflow_run.conclusion == 'success'
    permissions:
      packages: write   # required for deletion

    steps:
      - name: Delete untagged versions of the build-env image
        uses: actions/delete-package-versions@v5
        with:
          package-name: "build-env"
          package-type: "container"
          delete-only-untagged-versions: "true"
          min-versions-to-keep: 1     # keep at least the most recent untagged (current push)
          token: ${{ secrets.GITHUB_TOKEN }}
```

> `actions/delete-package-versions` handles pagination internally and respects the
> `min-versions-to-keep` guard to avoid deleting the image that was just pushed before
> the workflow run that consumed it finishes.

---

## PR Preview Image Cleanup (Post-merge)

Tag PR images with `pr-{number}` and delete them when the PR closes or merges:

```yaml
# .github/workflows/cleanup-pr-image.yml
name: Delete PR preview image
on:
  pull_request:
    types: [closed]

jobs:
  delete-preview:
    runs-on: ubuntu-latest
    permissions:
      packages: write

    steps:
      - name: Delete PR container image
        uses: actions/delete-package-versions@v5
        with:
          package-name: "workers-preview"
          package-type: "container"
          delete-only-package-with-semver-range: ""    # not used
          # Match tag pattern pr-{number}
          package-version-pattern: "pr-${{ github.event.pull_request.number }}"
          token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Cloudflare Worker: Scheduled Org-Wide Cleanup

For org-wide cleanup across many images and more complex retention rules, use a scheduled
Worker. This avoids GitHub Actions minutes cost and centralises policy.

```typescript
// src/workers/ghcr-cleanup.ts
export interface Env {
  GITHUB_PAT: string;       // secret: <redacted-secret> + read:packages
  ORG: string;              // Worker variable, e.g. "acme-corp"
  PACKAGES: string;         // comma-separated image names to manage
  RETENTION_DAYS: string;   // numeric string, e.g. "30"
}

interface PackageVersion {
  id: number;
  name: string;             // digest e.g. "sha256:abc..."
  created_at: string;
  updated_at: string;
  metadata: {
    container: {
      tags: string[];
    };
  };
}

const GH_API = "https://api.github.com";

async function ghFetch(path: string, method: string, token: string): Promise<Response> {
  return fetch(`${GH_API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "acme-ghcr-cleanup/1.0",
    },
  });
}

async function listVersions(
  org: string,
  packageName: string,
  token: string,
): Promise<PackageVersion[]> {
  const all: PackageVersion[] = [];
  let page = 1;

  while (true) {
    const res = await ghFetch(
      `/orgs/${org}/packages/container/${encodeURIComponent(packageName)}/versions?per_page=100&page=${page}`,
      "GET",
      token,
    );

    if (res.status === 404) break;   // package doesn't exist yet
    if (!res.ok) {
      console.error(`list versions failed: ${res.status} ${await res.text()}`);
      break;
    }

    const batch = (await res.json()) as PackageVersion[];
    all.push(...batch);
    if (batch.length < 100) break;
    page++;
  }

  return all;
}

async function deleteVersion(
  org: string,
  packageName: string,
  versionId: number,
  token: string,
): Promise<boolean> {
  const res = await ghFetch(
    `/orgs/${org}/packages/container/${encodeURIComponent(packageName)}/versions/${versionId}`,
    "DELETE",
    token,
  );
  return res.status === 204;
}

function shouldDelete(version: PackageVersion, retentionDays: number): boolean {
  const tags = version.metadata?.container?.tags ?? [];

  // Never delete semver-tagged or "latest" images
  if (tags.some((t) => t === "latest" || /^v\d+/.test(t))) {
    return false;
  }

  // Always delete untagged images older than retention period
  const age = Date.now() - new Date(version.updated_at).getTime();
  const ageDays = age / (1000 * 60 * 60 * 24);

  if (tags.length === 0 && ageDays > retentionDays) {
    return true;
  }

  // Delete PR images (pr-NNN) after retention period
  if (tags.some((t) => /^pr-\d+$/.test(t)) && ageDays > retentionDays) {
    return true;
  }

  // Delete branch-sha images (main-abc1234, sha-abc1234) after retention
  if (tags.some((t) => /^(main|sha|branch)-[0-9a-f]+$/.test(t)) && ageDays > retentionDays) {
    return true;
  }

  return false;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const packages = env.PACKAGES.split(",").map((p) => p.trim()).filter(Boolean);
    const retentionDays = parseInt(env.RETENTION_DAYS, 10) || 30;
    let totalDeleted = 0;

    for (const pkg of packages) {
      const versions = await listVersions(env.ORG, pkg, env.GITHUB_PAT);

      for (const version of versions) {
        if (!shouldDelete(version, retentionDays)) continue;

        const tags = version.metadata?.container?.tags ?? [];
        const deleted = await deleteVersion(env.ORG, pkg, version.id, env.GITHUB_PAT);

        if (deleted) {
          totalDeleted++;
          console.log(
            `[ghcr-cleanup] deleted ${pkg}@${version.name.slice(0, 16)} ` +
              `tags=[${tags.join(",")}] age=${Math.floor(
                (Date.now() - new Date(version.updated_at).getTime()) / 86_400_000,
              )}d`,
          );
        }

        // Stay under secondary rate limits: ~1 req/sec
        await new Promise((r) => setTimeout(r, 1000));
      }
    }

    console.log(`[ghcr-cleanup] done. total deleted: ${totalDeleted}`);
  },
};
```

---

## `wrangler.toml`

```toml
name = "ghcr-cleanup"
main = "src/workers/ghcr-cleanup.ts"
compatibility_date = "2026-08-01"

[vars]
ORG      = "acme-corp"
PACKAGES = "build-env,workers-preview,api-service"
RETENTION_DAYS = "30"

# Run every Sunday at 03:00 UTC
[[triggers]]
crons = ["0 3 * * 0"]

# Set secret: wrangler secret put GITHUB_PAT
```

---

## Verifying Retention Policy Before Enabling Deletion

Add a dry-run mode gated by an environment variable:

```typescript
const DRY_RUN = env.DRY_RUN === "true";

if (DRY_RUN) {
  console.log(`[dry-run] would delete ${pkg}@${version.name.slice(0, 16)}`);
} else {
  await deleteVersion(env.ORG, pkg, version.id, env.GITHUB_PAT);
}
```

Run `wrangler dev --env dry-run` locally to preview what would be deleted.

---

## Anti-patterns

- **Deleting by version index** — do not delete "the oldest N versions" by list position. The
  API order is not guaranteed to be chronological. Always sort by `updated_at` or use
  `shouldDelete` logic based on date arithmetic.

- **Using `GITHUB_TOKEN` for org-level deletions** — `GITHUB_TOKEN` is scoped to the single
  repository where the workflow runs. For org-wide cleanup across multiple image names owned
  by the org, you need a PAT or GitHub App with org-level `delete:packages`.

- **Deleting the image a concurrent build is pulling** — add a `min-versions-to-keep: 1` guard
  or a minimum age of 1 day for untagged versions to avoid racing with active CI jobs.

- **Ignoring multi-arch manifests** — a multi-arch image is a manifest list pointing to
  per-arch layers. Deleting a child manifest while the index still references it orphans the
  index. Always delete the manifest list (the tagged version) first, which cascades.

---

## Gotchas

- **`delete:packages` scope is irreversible** — there is no recycle bin. Once deleted, an image
  digest is gone permanently. Double-check your retention predicates in dry-run mode first.

- **GHCR enforces a minimum age** — you cannot delete a version that was pushed in the last
  24 hours via the API (returns 422). The `min-versions-to-keep` guard in the Actions action
  handles this; in the Worker, add an `ageDays > 1` floor.

- **Packages API pagination** — the list endpoint returns up to 100 versions per page. A busy
  repository can have thousands; always paginate fully before deciding what to delete.

- **Fine-grained PATs do not support `delete:packages`** — as of 2026, the "Packages (write)"
  permission on fine-grained PATs covers push but **not** deletion. Use a classic PAT with
  `delete:packages` + `read:packages`, or a GitHub App with `packages:write`.

- **org vs user packages** — images pushed under a user namespace use `/user/packages/…` endpoints;
  org-scoped images use `/orgs/{org}/packages/…`. Make sure you target the right scope.

---

## Verification

```bash
# List all versions of an image (requires read:packages)
gh api \
  "orgs/acme-corp/packages/container/build-env/versions?per_page=10" \
  --jq '.[] | {id, tags: .metadata.container.tags, updated: .updated_at}'

# Confirm deletion (expect 404 after successful delete)
VERSION_ID=12345678
gh api --method DELETE \
  "orgs/acme-corp/packages/container/build-env/versions/$VERSION_ID" \
  && echo "deleted" || echo "failed"

# Count remaining versions
gh api "orgs/acme-corp/packages/container/build-env/versions" \
  --jq 'length'
```

---

## Related

- `github-packages-container-registry-ghcr.md` — GHCR push/pull basics
- `github-packages-container-provenance-attestation.md` — provenance for retained images
- `github-actions-artifact-size-audit.md` — artifact storage management
- `github-actions-docker-build-push.md` — image build and push pipeline

---

## Sources

- https://docs.github.com/en/rest/packages/packages#list-package-versions-for-a-package-owned-by-an-organization
- https://docs.github.com/en/rest/packages/packages#delete-package-version-for-an-organization
- https://github.com/actions/delete-package-versions
- https://docs.github.com/en/packages/learn-github-packages/introduction-to-github-packages#authenticating-to-github-packages
