# GitHub Actions – Artifact Upload and Download via Cloudflare R2

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

GitHub's built-in artifact storage has a 90-day (free) or 400-day (paid) retention cap,
a per-file 2 GB limit, and costs scale with storage consumed per org seat. Cross-org
artifact sharing requires public repositories or manual download-and-re-upload steps.
You want a pipeline that uploads build outputs directly to Cloudflare R2 — either
replacing GitHub artifacts entirely or augmenting them — so that artifacts are accessible
via pre-signed URLs, survive indefinitely, can be shared across organizations, and cost
only R2 egress (free to Cloudflare services, $0.09/GB elsewhere).

## Context

R2 exposes an S3-compatible API. GitHub Actions runners can use the AWS CLI or any S3
SDK to talk to R2 by pointing `AWS_ENDPOINT_URL` at the account-specific R2 endpoint:
`https://<account-id>.r2.cloudflarestorage.com`. For download by external systems or
browsers, a Cloudflare Worker generates pre-signed URLs with a bounded TTL using
WebCrypto (R2 does not support S3 pre-signed URLs natively; use a Worker or R2's built-in
presigned URL support via the API). This article covers both the CI upload path and the
Worker-side download path.

## 1. R2 Bucket and R2 Token Setup

```bash
# Create the artifact bucket
wrangler r2 bucket create ci-artifacts

# Create an R2 API token (not the account API token) with Object Read & Write
# In the Cloudflare dashboard: R2 → Manage R2 API tokens → Create API token
# Scope: ci-artifacts bucket, permissions: Object Read & Write
# Note the Access Key ID and Secret Access Key
```

Store credentials in GitHub Actions secrets:

| Secret name              | Value                                          |
|--------------------------|------------------------------------------------|
| `R2_ACCESS_KEY_ID`       | R2 API token Access Key ID                    |
| `R2_SECRET_ACCESS_KEY`   | R2 API token Secret Access Key                |
| `CF_ACCOUNT_ID`          | Cloudflare Account ID (variable, not secret)  |

## 2. Upload Job Using AWS CLI

```yaml
# .github/workflows/build-and-upload-artifact.yml
name: Build and Upload Artifact to R2

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      artifact_key: ${{ steps.upload.outputs.artifact_key }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci && npm run build

      - name: Package build output
        run: |
          tar -czf build-${{ github.sha }}.tar.gz -C dist .
          echo "ARTIFACT_FILE=build-${{ github.sha }}.tar.gz" >> "$GITHUB_ENV"

      - name: Upload to R2
        id: upload
        run: |
          KEY="builds/${{ github.repository }}/${{ github.sha }}/build.tar.gz"

          aws s3 cp "$ARTIFACT_FILE" "s3://ci-artifacts/$KEY" \
            --metadata "commit=${{ github.sha }},ref=${{ github.ref }},workflow=${{ github.workflow }}" \
            --endpoint-url "https://${{ vars.CF_ACCOUNT_ID }}.r2.cloudflarestorage.com" \
            --region auto

          echo "artifact_key=$KEY" >> "$GITHUB_OUTPUT"
          echo "Uploaded to R2 key: $KEY"
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Download artifact from R2
        run: |
          KEY="${{ needs.build.outputs.artifact_key }}"
          aws s3 cp "s3://ci-artifacts/$KEY" build.tar.gz \
            --endpoint-url "https://${{ vars.CF_ACCOUNT_ID }}.r2.cloudflarestorage.com" \
            --region auto
          tar -xzf build.tar.gz -C dist/
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}

      - name: Deploy
        run: npx wrangler@3 deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_DEPLOY_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
```

## 3. R2 Key Naming Convention

Establish a consistent key schema to allow lifecycle rules and cross-job lookup:

```typescript
// src/artifact-keys.ts — shared by Worker and CI scripts
export function buildArtifactKey(params: {
  repo: string;   // "owner/name"
  sha: string;
  name: string;   // e.g. "build.tar.gz", "coverage.json"
}): string {
  const [owner, name] = params.repo.split("/");
  // builds/owner/name/sha/artifact-name
  return `builds/${owner}/${name}/${params.sha}/${params.name}`;
}

export function prArtifactKey(params: {
  repo: string;
  prNumber: number;
  name: string;
}): string {
  const [owner, name] = params.repo.split("/");
  return `pr-artifacts/${owner}/${name}/pr-${params.prNumber}/${params.name}`;
}
```

## 4. Worker – Serve Pre-signed Download URLs

R2's Workers binding generates temporary pre-signed URLs without exposing bucket
credentials to the client:

```typescript
// src/artifact-download-worker.ts
interface Env {
  CI_ARTIFACTS: R2Bucket;
  DOWNLOAD_SECRET: string;   // HMAC key for request authentication
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "GET") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const url = new URL(request.url);
    const key = url.searchParams.get("key");
    const sig = url.searchParams.get("sig");
    const exp = url.searchParams.get("exp");

    if (!key || !sig || !exp) {
      return new Response("Missing parameters", { status: 400 });
    }

    // Verify the request has not expired
    if (Date.now() > parseInt(exp, 10)) {
      return new Response("Link expired", { status: 410 });
    }

    // Verify HMAC signature to prevent unauthorized key enumeration
    const valid = await verifySignature(
      `${key}:${exp}`,
      sig,
      env.DOWNLOAD_SECRET
    );
    if (!valid) {
      return new Response("Invalid signature", { status: 403 });
    }

    const object = await env.CI_ARTIFACTS.get(key);
    if (!object) {
      return new Response("Artifact not found", { status: 404 });
    }

    const filename = key.split("/").pop() ?? "artifact";
    return new Response(object.body, {
      headers: {
        "Content-Type": object.httpMetadata?.contentType ?? "application/octet-stream",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "private, max-age=0",
        "X-R2-Key": key,
      },
    });
  },
};

async function verifySignature(
  message: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const sigBytes = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0));
  return crypto.subtle.verify("HMAC", key, sigBytes, new TextEncoder().encode(message));
}
```

## 5. Generate Signed Download URL from CI

```typescript
// scripts/sign-artifact-url.ts — run in CI to produce a share link
async function signArtifactUrl(params: {
  key: string;
  secret: string;
  workerUrl: string;
  ttlSeconds: number;
}): Promise<string> {
  const exp = Date.now() + params.ttlSeconds * 1000;
  const message = `${params.key}:${exp}`;

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(params.secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sigBytes = await crypto.subtle.sign(
    "HMAC",
    cryptoKey,
    new TextEncoder().encode(message)
  );
  const sig = btoa(String.fromCharCode(...new Uint8Array(sigBytes)));

  const url = new URL(`${params.workerUrl}/download`);
  url.searchParams.set("key", params.key);
  url.searchParams.set("sig", sig);
  url.searchParams.set("exp", String(exp));
  return url.toString();
}
```

## Anti-patterns

- **Using the global Cloudflare API token for R2 uploads from CI.** Create a dedicated
  R2 API token scoped to the specific bucket. If the CI token is compromised, the blast
  radius is limited to that bucket.
- **Storing artifact keys in GitHub commit messages or PR titles.** Use job outputs
  (`$GITHUB_OUTPUT`) to pass keys between jobs; they are not visible in the public
  timeline.
- **Uploading compressed files with `--content-encoding gzip`.** This sets an HTTP
  header that causes browsers to auto-decompress on download, producing a corrupt file.
  Use `.tar.gz` as a content-type-transparent container; do not set `Content-Encoding`.
- **No lifecycle rules on the bucket.** Add a lifecycle rule to expire PR artifacts
  after 30 days and branch builds after 90 days to control storage costs.

## Gotchas

- `--region auto` is required for R2 S3-compatible API calls. The AWS CLI default of
  `us-east-1` triggers a redirect that breaks the upload.
- R2 S3 API requires `AWS_ENDPOINT_URL` (not `--endpoint-url` on some older CLI
  versions). Use CLI v2 and prefer the flag form to avoid environment variable leakage.
- Object metadata values set via `--metadata` have a 2 KB total size limit across all
  keys combined.
- The Workers `R2Bucket.get()` method streams the body. Do not buffer it into memory for
  large files — pipe `object.body` directly to the `Response` constructor.

## Verification

```bash
# List recent build artifacts in R2
aws s3 ls "s3://ci-artifacts/builds/" \
  --recursive --endpoint-url "https://<account-id>.r2.cloudflarestorage.com" \
  --region auto | head -20

# Confirm metadata on a specific artifact
aws s3api head-object \
  --bucket ci-artifacts \
  --key "builds/owner/repo/<sha>/build.tar.gz" \
  --endpoint-url "https://<account-id>.r2.cloudflarestorage.com" \
  --region auto
```

## Related

- `github-actions-artifact-upload.md`
- `github-actions-release-asset-r2-distribution.md`
- `github-actions-docker-layer-cache-r2-backend.md`
- `github-actions-d1-snapshot-artifacts.md`
- `github-apps-installation-token-workers-api-client.md`

## Sources

- Cloudflare R2 – S3-compatible API: https://developers.cloudflare.com/r2/api/s3/api/
- Cloudflare R2 – Workers binding: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- AWS CLI v2 – endpoint-url: https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html
- GitHub Actions – job outputs: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/passing-information-between-jobs
