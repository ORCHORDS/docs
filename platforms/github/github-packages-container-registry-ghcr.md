# GitHub Packages Container Registry (GHCR) — Build, Push, and Pull Docker Images

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your team builds Docker images in CI and needs a registry that:
- lives in the same GitHub org (no separate DockerHub account or IAM policies)
- enforces the same team-permission model as the source repo
- is accessible to GitHub Actions with zero extra credential setup
- supports granular visibility (public images for OSS, private for enterprise workloads)

GitHub Container Registry (`ghcr.io`) satisfies all four. It is distinct from the older `docker.pkg.github.com` Packages endpoint and has been the recommended path since 2021.

---

## Context

GHCR is part of GitHub Packages but uses a separate namespace: `ghcr.io/<owner>/<image>:<tag>`.
Key facts as of 2026:

| Property | Detail |
|---|---|
| Registry host | `ghcr.io` |
| Auth token in Actions | `secrets.GITHUB_TOKEN` (no PAT needed for same-repo images) |
| Visibility | Public / Private / Internal (Enterprise) |
| Storage billing | Free for public; counts toward Packages storage for private |
| Supported formats | OCI image, Docker image manifest v2, multi-arch manifests |
| Retention | Images persist until deleted; no automatic TTL |

The `GITHUB_TOKEN` granted to a workflow has `packages: write` only if the job explicitly requests it.

---

## Authenticating to GHCR in GitHub Actions

The canonical login step uses `docker/login-action`:

```yaml
jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write   # required to push to ghcr.io

    steps:
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```

`github.actor` is the identity that triggered the run (a human user or `github-actions[bot]` for schedule/push triggers). GHCR accepts `GITHUB_TOKEN` for images owned by the **same** organisation or user account as the repo.

For cross-org pulls (e.g., a consumer repo pulling from a library org), you need a scoped PAT (`read:packages`) stored as a repository secret.

---

## Building and Pushing a Multi-Arch Image

```yaml
name: Build & Push Container

on:
  push:
    branches: [main]
    tags: ["v*.*.*"]
  pull_request:
    branches: [main]

env:
  IMAGE: ghcr.io/${{ github.repository }}   # e.g. ghcr.io/myorg/myapp

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up QEMU (for cross-compilation)
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha,prefix=sha-,format=short
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

Notes:
- `docker/metadata-action` auto-generates OCI standard labels (`org.opencontainers.image.*`) from repo metadata.
- Login is skipped on PRs so forks cannot push.
- `cache-from/to: type=gha` wires Docker layer cache through Actions Cache — no separate registry needed.
- `platforms: linux/amd64,linux/arm64` produces a single manifest list pointing at two platform-specific digests.

---

## Controlling Image Visibility and Access

### Making an image public

By default images inherit the repo's visibility. To make a private repo's image public (useful for publishing base images separately):

1. Navigate to **Packages** on your org page → select the image → **Package settings**.
2. Under **Danger Zone** → **Change package visibility** → Public.

Via API (GitHub CLI):

```bash
gh api \
  --method PATCH \
  /user/packages/container/myimage/versions \
  -f visibility=public
```

### Linking a package to a repository

GHCR images pushed by `GITHUB_TOKEN` are automatically linked to the source repo. For images pushed by a PAT or an external system, link manually:

```bash
gh api \
  --method PUT \
  /user/packages/container/myimage \
  -f repository_id=<repo_id>
```

Linking is required for the package to inherit repository team permissions.

### Org-level read access for all members

Under **Org Settings → Packages → Package Creation** you can restrict who may create packages and whether internal packages are visible to all org members automatically.

---

## Deleting Old Image Versions (Retention Policy)

GitHub has no built-in TTL. Automate cleanup with a workflow:

```yaml
name: Prune old container versions

on:
  schedule:
    - cron: "0 3 * * 0"   # weekly, Sunday 03:00 UTC

jobs:
  prune:
    runs-on: ubuntu-latest
    permissions:
      packages: write

    steps:
      - name: Delete untagged versions older than 30 days
        uses: actions/delete-package-versions@v5
        with:
          package-name: myapp
          package-type: container
          min-versions-to-keep: 5
          delete-only-untagged-versions: true
          token: ${{ secrets.GITHUB_TOKEN }}
```

`actions/delete-package-versions` respects `min-versions-to-keep` so you never wipe everything. Run in a separate org-level workflow if you manage many images.

---

## Anti-patterns

- **Pushing from PRs.** PRs from forks run with read-only `GITHUB_TOKEN`. If your job unconditionally calls `docker push` it fails with 403. Always gate push behind `if: github.event_name != 'pull_request'`.

- **Using `latest` as the only tag.** `latest` gives no traceability. Tag with git SHA and/or semver; use `latest` as an alias only.

- **Storing GHCR credentials in repository secrets.** For same-org images the `GITHUB_TOKEN` is always sufficient. A PAT secret is only needed for cross-org pulls, and it must be rotated manually. Prefer a GitHub App installation token for cross-org automation.

- **Omitting `permissions: packages: write`.** The default `GITHUB_TOKEN` grants `packages: read` only. Without the explicit permission declaration the push fails silently on newly created repos that have restrictive default permission settings.

- **Pulling inside a downstream job without specifying the digest.** Tags are mutable. Pin critical deploy jobs to the image digest (`ghcr.io/org/app@sha256:abc...`) instead of a tag to prevent silent image swaps.

---

## Gotchas

- **Package namespace vs. repo namespace.** The image name is `ghcr.io/<owner>/<image>` — `<owner>` is the org or user, not the repo. If your repo is `myorg/backend-api` and you push `ghcr.io/myorg/myapp`, the package name is `myapp`, not `backend-api/myapp`.

- **Deleted images cannot be restored.** There is no recycle bin. Always keep at least `min-versions-to-keep: 5` in cleanup workflows.

- **`GITHUB_TOKEN` expiry.** Tokens expire when the workflow job ends. If a downstream deployment workflow needs to pull the image hours later it must use its own `GITHUB_TOKEN` (which is fresh per job) or a PAT.

- **Visibility of multi-arch manifests.** Pushing a manifest list does not automatically make the constituent platform blobs public. The entire package visibility setting must be public; per-blob control is not available.

- **Enterprise GHCR network policy.** On GitHub Enterprise Server (GHES) the GHCR hostname differs: `docker.<hostname>`. Adjust all `registry:` references accordingly.

---

## Verification

```bash
# Confirm image is present and tagged correctly
gh api /orgs/myorg/packages/container/myapp/versions \
  --jq '.[] | {id: .id, tags: .metadata.container.tags, created: .created_at}' \
  | head -20

# Pull and inspect locally
docker pull ghcr.io/myorg/myapp:latest
docker inspect ghcr.io/myorg/myapp:latest \
  --format '{{json .Config.Labels}}' | jq .

# Verify multi-arch manifest
docker buildx imagetools inspect ghcr.io/myorg/myapp:latest
```

Expected output from `imagetools inspect` includes `Manifests:` with separate digest entries for `linux/amd64` and `linux/arm64`.

---

## Related

- `github-packages-npm-registry.md` — npm packages on the same Packages platform
- `github-actions-security-hardening.md` — minimise `GITHUB_TOKEN` scope
- `github-actions-artifact-attestations.md` — sign container images with Sigstore
- `github-sbom-generation.md` — attach SBOM to container images
- `github-actions-oidc-cloudflare.md` — token-less credential patterns (comparable approach)

---

## Sources

- GitHub Docs: "Working with the Container registry" — https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- docker/login-action v3 — https://github.com/docker/login-action
- docker/metadata-action v5 — https://github.com/docker/metadata-action
- docker/build-push-action v6 — https://github.com/docker/build-push-action
- actions/delete-package-versions — https://github.com/actions/delete-package-versions
- GitHub Docs: "About permissions for GitHub Packages" — https://docs.github.com/en/packages/learn-github-packages/about-permissions-for-github-packages
