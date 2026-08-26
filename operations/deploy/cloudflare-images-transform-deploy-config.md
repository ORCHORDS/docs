# Cloudflare Images Variant Configuration Deploy Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Image transform settings (named variants) are configured manually in the Cloudflare dashboard, causing drift between environments and blocking reproducible deploys. A developer deletes a variant, a new PoP serves broken `imagedelivery.net` URLs, and there is no audit trail. You need to version-control variant definitions and apply them as part of your CI/CD pipeline alongside your Worker deploys.

## Context

Cloudflare Images variants define named presets (`thumbnail`, `hero`, `avatar`) that apply width, height, fit, and quality transforms to images served via `imagedelivery.net`. Variants are **account-scoped**, not Worker-scoped — they must be managed separately from `wrangler deploy`. The Cloudflare REST API (`/accounts/{id}/images/v1/variants`) provides full CRUD; combining it with a declarative JSON config in your repo enables GitOps-style variant management with diff previews on PRs and automated apply on merge.

## 1. Declaring Variants as Code

```json
// images/variants.json — single source of truth for all transform presets
{
  "thumbnail": {
    "options": {
      "width": 320,
      "height": 240,
      "fit": "cover",
      "quality": 80,
      "metadata": "none"
    },
    "neverRequireSignedURLs": false
  },
  "hero": {
    "options": {
      "width": 1440,
      "fit": "scale-down",
      "quality": 85,
      "format": "auto",
      "metadata": "none"
    },
    "neverRequireSignedURLs": true
  },
  "avatar": {
    "options": {
      "width": 128,
      "height": 128,
      "fit": "cover",
      "gravity": "face",
      "quality": 90,
      "metadata": "none"
    },
    "neverRequireSignedURLs": false
  }
}
```

## 2. Sync Script — Upsert Variants via API

```typescript
// scripts/sync-image-variants.ts
import { readFile } from "fs/promises";

const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const BASE = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/images/v1/variants`;

interface VariantOptions {
  width?: number; height?: number; fit?: string;
  quality?: number; metadata?: string; format?: string; gravity?: string;
}
interface VariantDef { options: VariantOptions; neverRequireSignedURLs: boolean; }

async function cfFetch(method: string, url: string, body?: unknown) {
  const res = await fetch(url, {
    method,
    headers: { Authorization: `Bearer ${CF_API_TOKEN}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json() as { success: boolean; errors: { message: string }[] };
  if (!json.success) throw new Error(json.errors.map(e => e.message).join(", "));
  return json;
}

async function listVariants(): Promise<string[]> {
  const data = await cfFetch("GET", BASE) as { result: { variants: Record<string, unknown> } };
  return Object.keys(data.result.variants);
}

async function upsertVariant(name: string, def: VariantDef): Promise<void> {
  const existing = await listVariants();
  if (existing.includes(name)) {
    await cfFetch("PATCH", `${BASE}/${name}`, def);
    console.log(`  updated: ${name}`);
  } else {
    await cfFetch("POST", BASE, { id: name, ...def });
    console.log(`  created: ${name}`);
  }
}

const variants: Record<string, VariantDef> = JSON.parse(
  await readFile("images/variants.json", "utf8")
);
for (const [name, def] of Object.entries(variants)) {
  await upsertVariant(name, def);
}
console.log("Image variant sync complete.");
```

## 3. Dry-run Diff Before Apply

```typescript
// scripts/diff-image-variants.ts — shows what would change without applying
import { readFile } from "fs/promises";

async function diffVariants(): Promise<void> {
  const remoteRes = await cfFetch("GET", BASE) as {
    result: { variants: Record<string, { options: VariantOptions; neverRequireSignedURLs: boolean }> }
  };
  const remote = remoteRes.result.variants;
  const local: Record<string, VariantDef> = JSON.parse(
    await readFile("images/variants.json", "utf8")
  );

  for (const [name, def] of Object.entries(local)) {
    if (!remote[name]) {
      console.log(`[+] ${name} — will be CREATED`);
    } else {
      const changed = JSON.stringify(remote[name]) !== JSON.stringify(def);
      console.log(changed ? `[~] ${name} — will be UPDATED` : `[=] ${name} — no change`);
    }
  }
  // Detect orphaned remote variants not in local config
  const orphans = Object.keys(remote).filter(n => !local[n] && n !== "public");
  for (const name of orphans) {
    console.log(`[-] ${name} — remote-only (not in variants.json) — manual cleanup needed`);
  }
}

await diffVariants();
```

## 4. Post-Sync Verification via Test Image

```typescript
// scripts/verify-image-variants.ts — fetch a known test image through each variant
const TEST_IMAGE_ID = process.env.TEST_IMAGE_ID!;
const ACCOUNT_HASH = process.env.CF_IMAGES_ACCOUNT_HASH!;
const variants = ["thumbnail", "hero", "avatar"];

for (const variant of variants) {
  const url = `https://imagedelivery.net/${ACCOUNT_HASH}/${TEST_IMAGE_ID}/${variant}`;
  const res = await fetch(url, { method: "HEAD" });
  if (!res.ok) throw new Error(`Variant ${variant} returned HTTP ${res.status}`);
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.startsWith("image/")) throw new Error(`Variant ${variant} unexpected content-type: ${ct}`);
  const cacheStatus = res.headers.get("cf-cache-status") ?? "UNKNOWN";
  console.log(`  ${variant}: OK (${ct}, cache=${cacheStatus})`);
}
```

## 5. CI Integration (GitHub Actions)

```yaml
# .github/workflows/deploy-images-variants.yml
name: Sync Cloudflare Images Variants
on:
  push:
    branches: [main]
    paths: ["images/variants.json"]
  pull_request:
    paths: ["images/variants.json"]

jobs:
  diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npx tsx scripts/diff-image-variants.ts
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN_IMAGES_READ }}

  sync:
    runs-on: ubuntu-latest
    needs: diff
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npx tsx scripts/sync-image-variants.ts
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN_IMAGES_EDIT }}
      - run: npx tsx scripts/verify-image-variants.ts
        env:
          CF_IMAGES_ACCOUNT_HASH: ${{ secrets.CF_IMAGES_ACCOUNT_HASH }}
          TEST_IMAGE_ID: ${{ secrets.IMAGES_TEST_IMAGE_ID }}
```

## Anti-patterns

- Configuring variants only in the dashboard — no audit trail, no DR plan, drift guaranteed after manual edits.
- Using a single broad API token for both read diff and write sync; separate token scopes by job (Images:Read vs. Images:Edit).
- Auto-deleting orphan remote variants in the sync script — downstream `imagedelivery.net` URLs break immediately for any consumer that has not yet deployed.
- Setting `neverRequireSignedURLs: true` for private media without auditing all consumers — anyone with the URL can fetch the full-quality original.

## Gotchas

- The `public` variant is built-in and cannot be deleted or renamed via the API; always skip it in diff output to avoid false positives.
- `gravity: "face"` requires the Cloudflare Images face-detection add-on; an account without it silently falls back to center gravity with no error.
- Variant **name changes** are destructive — the old name returns 404 immediately on rename; deploy a redirect or alias Worker before decommissioning the old name.
- The account hash for `imagedelivery.net` URLs differs from the account ID; retrieve it from `GET /accounts/{id}/images/v1/keys`.
- `PATCH` accepts only the fields you want to change; sending `width: undefined` may zero out the field rather than leave it unchanged — only include keys you intend to modify.

## Verification

```bash
# List remote variants
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/images/v1/variants" \
  | jq '.result.variants | keys'

# Smoke-test a variant
curl -I "https://imagedelivery.net/$CF_IMAGES_ACCOUNT_HASH/$TEST_IMAGE_ID/thumbnail"
# Expect: HTTP/2 200, content-type: image/*, cf-cache-status: HIT on second request
```

## Related

- `r2-bucket-cors-configuration-deploy.md`
- `workers-assets-deploy-static-hybrid.md`
- `wrangler-assets-deploy-cache-busting-strategy.md`
- `cloudflare-smart-placement-deploy-optimization.md`

## Sources

- https://developers.cloudflare.com/images/cloudflare-images/api-crud/
- https://developers.cloudflare.com/images/cloudflare-images/transform/named-variants/
- https://developers.cloudflare.com/fundamentals/api/
- https://developers.cloudflare.com/images/cloudflare-images/serve-images/
