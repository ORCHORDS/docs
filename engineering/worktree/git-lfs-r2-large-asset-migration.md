# Migrating Git LFS Large Assets to Cloudflare R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers project stores large binary assets—training datasets, Wasm binaries, video fixtures, large SQLite snapshots—in git LFS. LFS bills per bandwidth and storage, clone times balloon on CI, and LFS locks serialize concurrent work across worktrees. Migrating to Cloudflare R2 removes the LFS dependency: Worker code fetches assets directly from R2 at runtime, CI pulls only what each job needs, and costs shift from per-seat LFS quotas to per-request R2 pricing (free tier covers most CI volumes).

## Context

Git LFS stores pointer files in the repo (`.gitattributes` `filter=lfs` entries) that reference blob objects on an LFS server. When migrated, pointer files become URLs or asset IDs, the LFS objects are uploaded to R2, and Workers use the R2 binding or public bucket URL to retrieve them. The migration has three phases: upload existing LFS objects to R2, rewrite the repo to replace LFS pointers with R2 references, and update Worker code and CI pipelines to pull from R2 instead of LFS.

---

## Phase 1 — Inventory LFS Objects

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== LFS Tracked Paths ==="
git lfs track

echo ""
echo "=== LFS Objects in HEAD ==="
git lfs ls-files --long

echo ""
echo "=== Total LFS Disk Usage ==="
git lfs ls-files --size | awk '{sum += $NF} END {print sum " bytes"}'

echo ""
echo "=== LFS Objects in All Refs (for complete migration) ==="
git lfs ls-files --all --long | wc -l
echo "objects across all refs"
```

Generate a manifest that maps LFS OID to the intended R2 key:

```typescript
// scripts/lfs-inventory.ts
import { execSync } from "child_process";
import * as fs from "fs";

interface LfsObject {
  oid: string;
  size: number;
  path: string;
  r2Key: string;
}

const lines = execSync("git lfs ls-files --long --all", { encoding: "utf8" })
  .trim()
  .split("\n")
  .filter(Boolean);

const objects: LfsObject[] = lines.map((line) => {
  // Format: "<oid> * <path>"
  const [oid, , ...pathParts] = line.split(" ");
  const path = pathParts.join(" ");
  return {
    oid,
    size: 0, // populated below
    path,
    r2Key: `lfs-migration/${oid.slice(0, 2)}/${oid.slice(2, 4)}/${oid}`,
  };
});

fs.writeFileSync("lfs-migration-manifest.json", JSON.stringify(objects, null, 2));
console.log(`Manifest written: ${objects.length} objects`);
```

## Phase 2 — Upload LFS Objects to R2

```bash
#!/usr/bin/env bash
# Uses wrangler r2 object put to upload each LFS object
BUCKET="my-worker-assets"
MANIFEST="lfs-migration-manifest.json"
LFS_CACHE=".git/lfs/objects"

# Pull all LFS objects locally first
git lfs fetch --all

jq -c '.[]' "$MANIFEST" | while IFS= read -r entry; do
  OID=$(echo "$entry" | jq -r '.oid')
  R2_KEY=$(echo "$entry" | jq -r '.r2Key')
  LOCAL_PATH="${LFS_CACHE}/${OID:0:2}/${OID:2:2}/${OID}"

  if [[ ! -f "$LOCAL_PATH" ]]; then
    echo "WARNING: LFS object not found locally: $OID"
    continue
  fi

  echo "Uploading $OID → r2://$BUCKET/$R2_KEY"
  wrangler r2 object put "$BUCKET/$R2_KEY" \
    --file="$LOCAL_PATH" \
    --content-type="application/octet-stream"
done

echo "Upload complete."
```

For large-scale migrations, use the AWS S3-compatible R2 endpoint with `aws s3 cp` for parallel uploads:

```bash
#!/usr/bin/env bash
# R2 S3-compatible endpoint (replace with your account ID)
R2_ENDPOINT="https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
BUCKET="my-worker-assets"

# Export credentials from wrangler config
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

git lfs fetch --all

find .git/lfs/objects -type f | while read -r obj; do
  OID=$(basename "$obj")
  R2_KEY="lfs-migration/${OID:0:2}/${OID:2:2}/${OID}"
  aws s3 cp "$obj" "s3://$BUCKET/$R2_KEY" \
    --endpoint-url "$R2_ENDPOINT" \
    --no-progress
done
```

## Phase 3 — Rewrite Repo to Remove LFS Pointers

After all objects are uploaded, use `git lfs migrate export` to rewrite commits, replacing LFS pointer files with their actual content (which can then be deleted from the repo and served via R2 URL references):

```bash
#!/usr/bin/env bash
# Rewrite LFS tracked files to plain git objects (removes LFS dependency)
# WARNING: this rewrites history — coordinate with all team members

git lfs migrate export \
  --include="*.wasm,*.sqlite,*.bin,fixtures/**" \
  --everything

# After migration, verify no LFS pointer files remain
git lfs ls-files
# Should return empty

# Remove .gitattributes LFS filters
sed -i '/filter=lfs/d' .gitattributes
git add .gitattributes
git commit -m "chore: remove git LFS tracking (migrated to R2)"
```

## Phase 4 — Update Workers to Fetch from R2

Replace hardcoded asset file reads with R2 binding calls in Worker code:

```typescript
// workers/my-worker/src/assets.ts
// BEFORE: read from bundled file (only worked for small assets)
// import wasmBinary from "./model.wasm";

// AFTER: fetch from R2 at runtime
export interface Env {
  ASSETS: R2Bucket;
}

const WASM_KEY = "lfs-migration/ab/cd/abcd1234..."; // from migration manifest

let cachedModule: WebAssembly.Module | null = null;

export async function getWasmModule(env: Env): Promise<WebAssembly.Module> {
  if (cachedModule) return cachedModule;

  const object = await env.ASSETS.get(WASM_KEY);
  if (!object) {
    throw new Error(`Asset not found in R2: ${WASM_KEY}`);
  }

  const buffer = await object.arrayBuffer();
  cachedModule = await WebAssembly.compile(buffer);
  return cachedModule;
}
```

```toml
# wrangler.toml — bind the R2 bucket
[[r2_buckets]]
binding = "ASSETS"
bucket_name = "my-worker-assets"
```

## Phase 5 — Update CI to Skip LFS Pull

Remove `git lfs pull` from CI pipelines and replace with targeted R2 fetches:

```yaml
# .github/workflows/ci.yml
- name: Checkout (no LFS)
  uses: actions/checkout@v4
  with:
    lfs: false   # previously: lfs: true

- name: Pull test fixtures from R2
  env:
    R2_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
    R2_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
    R2_ACCOUNT_ID: ${{ secrets.R2_ACCOUNT_ID }}
  run: |
    # Fetch only the fixtures needed for this job
    node scripts/pull-r2-fixtures.mjs \
      --keys "test-fixtures/payments-snapshot.sqlite,test-fixtures/auth-wasm.wasm" \
      --out-dir test/fixtures/
```

```typescript
// scripts/pull-r2-fixtures.mjs
import { S3Client, GetObjectCommand } from "@aws-sdk/client-s3";
import { writeFile } from "fs/promises";
import { parseArgs } from "util";

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    keys: { type: "string" },
    "out-dir": { type: "string" },
  },
});

const client = new S3Client({
  endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  region: "auto",
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID!,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
  },
});

for (const key of values.keys!.split(",")) {
  const { Body } = await client.send(
    new GetObjectCommand({ Bucket: "my-worker-assets", Key: key.trim() })
  );
  const bytes = await Body!.transformToByteArray();
  const filename = `${values["out-dir"]}/${key.split("/").pop()}`;
  await writeFile(filename, bytes);
  console.log(`Fetched ${key} → ${filename}`);
}
```

---

## Anti-patterns

- **Deleting LFS history before verifying all objects are in R2.** Run a checksum comparison between `.git/lfs/objects` and R2 object ETags before pruning anything.
- **Using public R2 buckets for private test fixtures.** Enable R2 bucket access controls and use pre-signed URLs or Workers with access validation for sensitive test data.
- **Bundling large R2 assets into the Worker itself.** Workers have a 10 MB (free) / 50 MB (paid) script size limit. Large assets must be fetched at runtime, not bundled.
- **Not caching R2 responses.** R2 egress is free between R2 and Workers in the same account, but repeated fetches per request add latency. Cache at the Worker level using `caches.default` or an in-memory module-scoped variable.

## Gotchas

- `git lfs migrate export` rewrites history. Every team member must `git clone --no-local` the rewritten repo. Communicate with a freeze window.
- R2 object keys are case-sensitive. Ensure the upload and fetch scripts use the same casing.
- `wrangler r2 object put` has a 300 MB single-object limit via CLI. For larger objects, use multipart uploads through the S3-compatible API.
- Git LFS locks are per-file, per-user. Verify all locks are cleared before migrating: `git lfs locks` and `git lfs unlock --force <path>`.

## Verification

```bash
# 1. Confirm no LFS pointer files remain in HEAD
git lfs ls-files  # expect empty output

# 2. Spot-check an R2 object exists with correct size
wrangler r2 object get my-worker-assets/lfs-migration/ab/cd/abcd1234 \
  --file /tmp/verify-asset.bin
ls -lh /tmp/verify-asset.bin

# 3. Test Worker asset fetch locally
wrangler dev --env staging
curl http://localhost:8787/internal/asset-health  # should return 200

# 4. Confirm CI pipeline no longer pulls LFS
gh run view --log $(gh run list --limit 1 --json databaseId -q '.[0].databaseId') \
  | grep -i "lfs"  # expect no LFS pull output
```

## Related

- `git-lfs-2026.md`
- `git-lfs-partial-clone-alternatives.md`
- `workers-kv-r2-d1-storage-selection.md`
- `turborepo-remote-cache-cloudflare-r2-backend.md`
- `git-shallow-clone-ci-optimization.md`

## Sources

- Git LFS documentation: https://git-lfs.com/
- Cloudflare R2 S3 API compatibility: https://developers.cloudflare.com/r2/api/s3/api/
- Wrangler R2 CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#r2
- Cloudflare R2 pricing: https://developers.cloudflare.com/r2/pricing/
