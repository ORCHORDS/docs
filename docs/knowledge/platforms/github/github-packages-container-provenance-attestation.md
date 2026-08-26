# GitHub Packages Container Image Provenance Attestation (GHCR + SLSA)

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A container image pulled from GHCR cannot be traced back to the exact commit, workflow
run, and actor that built it.  Without signed provenance, supply chain audits fail and
automated policy gates (OPA, Kyverno, Sigstore) cannot enforce "only CI-built images
run in production."

## Context

GitHub Actions and GHCR together support SLSA Level 2 provenance out of the box via
the `actions/attest-build-provenance` action (GA in 2024).  The action:

1. Generates a SLSA provenance predicate describing the build inputs.
2. Signs it with a Sigstore bundle anchored to the GitHub OIDC token.
3. Uploads the attestation to a GitHub-hosted Rekor-compatible transparency log.
4. Associates the attestation with the image digest in GHCR (via `referrers` API).

Consumers can verify the attestation with `gh attestation verify` without any external
PKI or key management.

---

## 1. Building and Attesting a Container Image

```yaml
# .github/workflows/build-and-attest.yml
name: Build, Push, and Attest Container

on:
  push:
    branches: [main]
    tags: ["v*"]

permissions:
  contents: read
  packages: write
  id-token: write        # required: Sigstore OIDC signing
  attestations: write    # required: upload attestation bundle

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image-digest: ${{ steps.push.outputs.digest }}

    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=semver,pattern={{version}}
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - name: Build and push
        id: push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Attest build provenance
        uses: actions/attest-build-provenance@v1
        with:
          subject-name: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          subject-digest: ${{ steps.push.outputs.digest }}
          push-to-registry: true    # uploads attestation as OCI referrer to GHCR
```

---

## 2. Attaching a Custom SBOM Attestation

Beyond build provenance, attach a CycloneDX SBOM so consumers know exactly which
packages are inside the image.

```yaml
      - name: Generate SBOM (Syft)
        uses: anchore/sbom-action@v0
        with:
          image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.push.outputs.digest }}
          format: cyclonedx-json
          output-file: sbom.cyclonedx.json

      - name: Attest SBOM
        uses: actions/attest-sbom@v1
        with:
          subject-name: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          subject-digest: ${{ steps.push.outputs.digest }}
          sbom-path: sbom.cyclonedx.json
          push-to-registry: true
```

---

## 3. Verifying Attestation Before Deployment

In a separate deploy job or workflow, verify the attestation before pulling the image
into a production environment.

```yaml
  deploy:
    runs-on: ubuntu-latest
    needs: build
    environment: production
    steps:
      - name: Verify build provenance
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh attestation verify \
            oci://${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.image-digest }} \
            --owner ${{ github.repository_owner }} \
            --format json \
            | jq '.[] | {verificationResult: .verificationResult, signerRepo: .verificationResult.signature.certificate.sourceRepositoryURI}'

      - name: Deploy to Cloudflare (verified image only)
        run: |
          # Only reached if attestation verification above passes (exit 0)
          pnpm wrangler deploy --image ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ needs.build.outputs.image-digest }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## 4. Programmatic Attestation Lookup via API

Fetch attestation bundles for a digest using the GitHub Attestations API.

```typescript
// workers/attestation-check/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { owner, repo, digest } = await request.json<{
      owner: string;
      repo: string;
      digest: string;  // sha256:abc123...
    }>();

    const res = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/attestations/${digest}`,
      {
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          "X-GitHub-Api-Version": "2022-11-28",
        },
      }
    );

    if (!res.ok) {
      return Response.json({ verified: false, reason: await res.text() }, { status: 502 });
    }

    const { attestations } = await res.json<{ attestations: unknown[] }>();
    return Response.json({
      verified: attestations.length > 0,
      count: attestations.length,
    });
  },
};
```

---

## 5. Enforcing Attestation in Kubernetes / OPA Gatekeeper

For services running containers pulled from GHCR, add a policy that rejects unattested
images.  The `gh attestation verify` CLI can be called from an admission webhook.

```bash
#!/usr/bin/env bash
# /usr/local/bin/verify-attestation.sh — called by admission webhook sidecar
set -euo pipefail

IMAGE_REF="$1"   # e.g. ghcr.io/org/repo@sha256:abc123

gh attestation verify "oci://${IMAGE_REF}" \
  --owner "${GITHUB_ORG}" \
  --predicate-type https://slsa.dev/provenance/v1 \
  --deny-self-hosted-runners

echo "Attestation verified for $IMAGE_REF"
```

---

## Anti-patterns

- Attesting the image *tag* (`latest`) rather than the digest — tags are mutable; the
  attestation must reference the immutable `sha256:` digest.
- Setting `push-to-registry: false` on the attest action — the attestation is only
  stored in GitHub's database, not as a GHCR referrer, so OCI clients cannot discover
  it via the standard referrers API.
- Skipping `id-token: write` permission — the Sigstore signing step fails silently and
  the action uploads an unsigned bundle.
- Using the attest action on a self-hosted runner without setting `--deny-self-hosted-runners` in downstream verify commands — a compromised self-hosted runner can forge provenance.

## Gotchas

- `actions/attest-build-provenance` is pinned to a SHA internally; always check the
  action's own pinning with `gh repo view actions/attest-build-provenance --json defaultBranchRef`.
- The attestation is uploaded to `ghcr.io` *separately* from the image layers as an OCI
  referrer artifact; `docker pull` does not download attestations by default — use
  `gh attestation verify` or `cosign verify-attestation`.
- GitHub's Rekor-backed transparency log is GitHub-operated; for air-gapped or
  compliance-sensitive environments, configure an alternative Rekor instance via
  `SIGSTORE_REKOR_URL`.
- Attestations for images in private repositories require `read:packages` scope on the
  token used by `gh attestation verify`.

## Verification

```bash
# Verify attestation for a specific digest
gh attestation verify \
  oci://ghcr.io/{owner}/{repo}@sha256:{digest} \
  --owner {owner}

# List all attestations for a repository
gh api repos/{owner}/{repo}/attestations \
  | jq '.attestations[] | {bundle_url: .bundle.dsseEnvelope.payload | @base64d | fromjson | .predicateType}'

# Inspect referrers on the image (OCI spec)
oras discover ghcr.io/{owner}/{repo}@sha256:{digest} --artifact-type application/vnd.dev.sigstore.bundle.v0.3+json
```

## Related

- `github-actions-artifact-attestations.md`
- `github-packages-container-registry-ghcr.md`
- `github-sbom-generation.md`
- `github-advanced-security-sarif-workers-upload.md`
- `github-actions-oidc-cloudflare.md`

## Sources

- https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds
- https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/verifying-artifact-attestations
- https://slsa.dev/spec/v1.0/provenance
- https://github.com/actions/attest-build-provenance
