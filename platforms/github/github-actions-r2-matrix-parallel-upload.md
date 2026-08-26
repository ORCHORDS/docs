# GitHub Actions Matrix Fan-out for Parallel R2 Multi-Bucket Uploads

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A release pipeline must distribute build artifacts to multiple Cloudflare R2 buckets — for example, region-segregated buckets (`us-assets`, `eu-assets`, `apac-assets`), environment-specific buckets (`staging-assets`, `production-assets`), or per-tenant buckets in a Workers for Platforms deployment. Uploading them serially doubles or triples pipeline time. You want concurrent uploads using a GitHub Actions matrix, each job uploading to a single bucket in parallel.

## Context

GitHub Actions matrix strategy spawns independent jobs for each entry. Wrangler's `r2 object put` and the AWS S3-compatible Cloudflare R2 API both support scriptable uploads. By expressing target buckets as a matrix dimension, all uploads run concurrently (limited by the account's concurrent job cap). This pattern is distinct from `github-actions-artifact-r2-upload-download.md` (which covers artifact archiving to a single bucket) — here the goal is **fan-out replication or multi-region distribution** of the same build output.

## Step 1 — Build Once, Upload Many (needs + artifact handoff)

```yaml
# .github/workflows/release-r2-fan-out.yml
name: Release – parallel R2 distribution
on:
  release:
    types: [published]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci
      - run: npm run build -- --outdir dist/

      - name: Upload dist as workflow artifact
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
          retention-days: 1
          compression-level: 0  # already minified; skip compression overhead
```

## Step 2 — Define the Bucket Matrix

```yaml
  upload:
    needs: build
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false  # continue other buckets if one fails
      matrix:
        bucket:
          - name: us-east-assets
            region: us-east
            secret_suffix: US_EAST
          - name: eu-west-assets
            region: eu-west
            secret_suffix: EU_WEST
          - name: apac-assets
            region: apac
            secret_suffix: APAC
          - name: staging-assets
            region: us-east
            secret_suffix: STAGING

    steps:
      - name: Download dist artifact
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
```

## Step 3 — Upload with Wrangler r2 object put (Recursive)

```yaml
      - name: Install Wrangler
        run: npm install -g wrangler

      - name: Upload to R2 bucket ${{ matrix.bucket.name }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets[format('CF_R2_TOKEN_{0}', matrix.bucket.secret_suffix)] }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          # Wrangler does not support recursive directory upload natively;
          # use a shell loop over the dist tree
          find dist/ -type f | while IFS= read -r file; do
            OBJECT_KEY="${file#dist/}"
            echo "Uploading ${OBJECT_KEY} to ${{ matrix.bucket.name }}"
            wrangler r2 object put "${{ matrix.bucket.name }}/${OBJECT_KEY}" \
              --file "${file}" \
              --content-type "$(npx --yes mime-types "${file}" 2>/dev/null || echo 'application/octet-stream')"
          done
```

## Step 4 — Alternative: AWS S3-Compatible API with Parallel Transfers

```typescript
// scripts/r2-sync.ts
// Uses S3 client for parallel multipart uploads — faster for large files
import {
  S3Client,
  PutObjectCommand,
  CreateMultipartUploadCommand,
  UploadPartCommand,
  CompleteMultipartUploadCommand,
} from "@aws-sdk/client-s3";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { lookup } from "mime-types";

const client = new S3Client({
  region: "auto",
  endpoint: `https://${process.env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID!,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
  },
});

async function uploadFile(localPath: string, bucket: string, key: string): Promise<void> {
  const body = readFileSync(localPath);
  const contentType = (lookup(localPath) || "application/octet-stream") as string;
  await client.send(
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      Body: body,
      ContentType: contentType,
      CacheControl: key.includes("immutable") ? "public, max-age=31536000, immutable" : "no-cache",
    })
  );
}

function walkDir(dir: string): string[] {
  const entries: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) entries.push(...walkDir(full));
    else entries.push(full);
  }
  return entries;
}

const bucket = process.env.R2_BUCKET!;
const distDir = process.env.DIST_DIR ?? "dist";
const files = walkDir(distDir);

// Upload in batches of 10 concurrently
const CONCURRENCY = 10;
for (let i = 0; i < files.length; i += CONCURRENCY) {
  const batch = files.slice(i, i + CONCURRENCY);
  await Promise.all(
    batch.map((f) => uploadFile(f, bucket, relative(distDir, f)))
  );
  console.log(`Uploaded batch ${Math.ceil(i / CONCURRENCY) + 1}/${Math.ceil(files.length / CONCURRENCY)}`);
}
console.log(`Done: ${files.length} files → ${bucket}`);
```

```yaml
      - name: Upload via S3-compatible API
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          R2_BUCKET: ${{ matrix.bucket.name }}
          R2_ACCESS_KEY_ID: ${{ secrets[format('R2_ACCESS_KEY_{0}', matrix.bucket.secret_suffix)] }}
          R2_SECRET_ACCESS_KEY: ${{ secrets[format('R2_SECRET_{0}', matrix.bucket.secret_suffix)] }}
          DIST_DIR: dist
        run: npx tsx scripts/r2-sync.ts
```

## Step 5 — Aggregate Upload Status and Fail Loudly

```yaml
  verify-uploads:
    needs: upload
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Check all matrix jobs succeeded
        run: |
          if [[ "${{ needs.upload.result }}" != "success" ]]; then
            echo "::error::One or more R2 bucket uploads failed. Check matrix job logs."
            exit 1
          fi
          echo "All R2 uploads succeeded."
```

## Anti-patterns

- **Using `fail-fast: true` on the upload matrix**: One region failing will cancel all in-flight uploads, leaving some buckets with the old version and others with the new — an inconsistent state. Always use `fail-fast: false` for distribution fan-out.
- **Storing separate long-lived API tokens per bucket in repository secrets**: Prefer one API token with **R2:Edit** on all buckets, or use R2 access keys scoped per bucket per environment. Minimise the secret surface.
- **Uploading from the build job directly**: If the build job is re-run, the artifact is regenerated and uploads diverge from the original. Build once, upload many using `actions/upload-artifact` + `actions/download-artifact`.
- **Not setting `Cache-Control` on uploaded objects**: Objects served from R2 via Workers or a custom domain default to no cache headers; set `immutable` on content-addressed assets and `no-cache` on HTML entry points.

## Gotchas

- `wrangler r2 object put` requires `CLOUDFLARE_API_TOKEN` (API token); the S3-compatible API requires R2 access key ID + secret (not the same credential). Create R2 access keys in the dashboard under R2 > Manage API tokens.
- R2 object key names are case-sensitive and support `/` as a delimiter but have no real directory concept. Ensure `find` output relative paths use forward slashes on all runners.
- The `format()` expression in `secrets[format(...)]` works in `env:` blocks but **not** in `with:` blocks on `uses:` steps. Use `env:` to pass dynamically-named secrets to actions.
- GitHub Actions concurrent job limits (20 for free, 60 for Team, 500 for Enterprise) apply across the entire account; a 4-element matrix occupies 4 slots simultaneously.
- Large files (> 100 MB) benefit from multipart upload via the S3 client. Wrangler's `r2 object put` sends a single PUT — use the S3 approach for binaries.

## Verification

```bash
# List objects in a target bucket to confirm upload
wrangler r2 object list us-east-assets --prefix "assets/"

# Or via S3 API
aws s3 ls s3://us-east-assets/ \
  --endpoint-url "https://${CF_ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --recursive | head -20
```

## Related

- `github-actions-artifact-r2-upload-download.md`
- `github-actions-release-asset-r2-distribution.md`
- `github-actions-docker-layer-cache-r2-backend.md`
- `github-actions-turborepo-remote-cache-cloudflare-r2.md`
- `github-actions-matrix-strategy-workers.md`

## Sources

- https://developers.cloudflare.com/r2/api/s3/api/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/workers/wrangler/commands/#r2-object-put
- https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/accessing-contextual-information-about-workflow-runs#format
