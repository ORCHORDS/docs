# Workers AI Image Classification with Vision Models

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to classify user-uploaded images automatically — for a content moderation pipeline, product tagging, or asset management system. Workers AI's `@cf/microsoft/resnet-50` model accepts raw image bytes and returns ranked label/score pairs that you can act on without any external ML infrastructure.

---

## Context

Images are stored in R2 as the source of truth. At classification time the Worker retrieves the object from R2, converts the `ArrayBuffer` to a `number[]` of uint8 values (the format Workers AI vision models expect), and calls `env.AI.run` with `{ image: uint8Array }`. The model returns up to 1000 ImageNet labels ranked by confidence score. The top-5 results are persisted in D1 alongside the R2 object key for later querying. A content moderation gate checks if any of the top labels belong to a blocklist; flagged images are moved to a quarantine R2 prefix and the upload is rejected with HTTP 422.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "image-classifier"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[ai]
binding = "AI"

[[r2_buckets]]
binding = "UPLOADS"
bucket_name = "user-uploads"

[[d1_databases]]
binding = "DB"
database_name = "image-meta"
database_id = "<your-d1-id>"
```

---

## Section 2 — D1 Schema and Classification Logic

```typescript
// src/schema.sql  (run via: wrangler d1 execute image-meta --file=src/schema.sql)
// CREATE TABLE IF NOT EXISTS image_classifications (
//   id          TEXT PRIMARY KEY,
//   r2_key      TEXT NOT NULL,
//   label_1     TEXT,  score_1 REAL,
//   label_2     TEXT,  score_2 REAL,
//   label_3     TEXT,  score_3 REAL,
//   label_4     TEXT,  score_4 REAL,
//   label_5     TEXT,  score_5 REAL,
//   flagged     INTEGER DEFAULT 0,
//   created_at  TEXT DEFAULT (datetime('now'))
// );

// src/classifier.ts
import type { Env } from "./index";

export interface ClassificationResult {
  label: string;
  score: number;
}

const BLOCKLIST = new Set([
  "projectile",
  "rifle",
  "revolver",
  "assault rifle",
  "brassiere",
  "bikini",
  // extend with domain-specific labels
]);

export async function classifyFromR2(
  r2Key: string,
  env: Env
): Promise<{ results: ClassificationResult[]; flagged: boolean }> {
  // 1. Fetch image bytes from R2
  const object = await env.UPLOADS.get(r2Key);
  if (!object) throw new Error(`R2 key not found: ${r2Key}`);

  const buffer = await object.arrayBuffer();
  const uint8 = Array.from(new Uint8Array(buffer));

  // 2. Run ResNet-50 classification
  const response = (await env.AI.run("@cf/microsoft/resnet-50", {
    image: uint8,
  })) as ClassificationResult[];

  // 3. Take top-5 by score
  const top5 = response
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  // 4. Moderation check
  const flagged = top5.some((r) => BLOCKLIST.has(r.label.toLowerCase()));

  return { results: top5, flagged };
}

export async function persistClassification(
  id: string,
  r2Key: string,
  results: ClassificationResult[],
  flagged: boolean,
  env: Env
): Promise<void> {
  const row = results.slice(0, 5);
  const pad = Array(5 - row.length).fill({ label: null, score: null });
  const all = [...row, ...pad];

  await env.DB.prepare(
    `INSERT INTO image_classifications
     (id, r2_key, label_1, score_1, label_2, score_2, label_3, score_3,
      label_4, score_4, label_5, score_5, flagged)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      id,
      r2Key,
      all[0].label, all[0].score,
      all[1].label, all[1].score,
      all[2].label, all[2].score,
      all[3].label, all[3].score,
      all[4].label, all[4].score,
      flagged ? 1 : 0
    )
    .run();
}
```

---

## Section 3 — Worker Entry Point with Moderation Gate

```typescript
// src/index.ts
import { classifyFromR2, persistClassification } from "./classifier";

export interface Env {
  AI: Ai;
  UPLOADS: R2Bucket;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /classify  {"r2Key": "uploads/user123/photo.jpg"}
    if (request.method === "POST" && url.pathname === "/classify") {
      const { r2Key } = await request.json<{ r2Key: string }>();

      const id = crypto.randomUUID();
      const { results, flagged } = await classifyFromR2(r2Key, env);

      await persistClassification(id, r2Key, results, flagged, env);

      if (flagged) {
        // Move flagged image to quarantine prefix
        const obj = await env.UPLOADS.get(r2Key);
        if (obj) {
          const quarantineKey = `quarantine/${r2Key}`;
          await env.UPLOADS.put(quarantineKey, obj.body, {
            httpMetadata: obj.httpMetadata,
          });
          await env.UPLOADS.delete(r2Key);
        }
        return Response.json(
          { error: "Image rejected: content policy violation", id },
          { status: 422 }
        );
      }

      return Response.json({ id, r2Key, top5: results });
    }

    // GET /classifications?r2Key=uploads/user123/photo.jpg
    if (request.method === "GET" && url.pathname === "/classifications") {
      const r2Key = url.searchParams.get("r2Key");
      if (!r2Key) return new Response("Missing r2Key", { status: 400 });

      const { results } = await env.DB.prepare(
        "SELECT * FROM image_classifications WHERE r2_key = ? ORDER BY created_at DESC LIMIT 10"
      )
        .bind(r2Key)
        .all();

      return Response.json(results);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Passing a base64 string instead of `number[]`** — Workers AI vision models require a plain array of uint8 integers, not a base64-encoded string or a `Uint8Array` typed-array object.
- **Classifying inside the upload handler synchronously on large files** — for images over ~2 MB consider offloading classification to a Queue consumer to avoid hitting Worker CPU time limits.
- **Hard-coding blocklist labels without normalising case** — ResNet-50 labels use mixed case (`assault rifle`, `projectile`); always `.toLowerCase()` before comparison.
- **Not handling R2 `null` returns** — `env.UPLOADS.get()` returns `null` for missing keys; fail fast with a clear error rather than letting the `arrayBuffer()` call throw.

---

## Gotchas

- ResNet-50 is trained on ImageNet-1000; it excels at objects and animals but has limited vocabulary for human-generated content moderation — combine with a dedicated NSFW model for production pipelines.
- Large PNG files decode to much larger `uint8` arrays than the file size suggests; a 1 MB PNG may expand to 12 MB of raw pixels, approaching Worker memory limits.
- D1 `INTEGER` columns store booleans as `0`/`1`; cast back to `boolean` in application code with `!!row.flagged`.
- Quarantine-prefix moves are not atomic — if the `put` succeeds but `delete` fails, the image exists in both locations; add a cleanup cron or use a `flagged = 1` query to find duplicates.

---

## Verification

```bash
# Create D1 table
npx wrangler d1 execute image-meta --file=src/schema.sql

# Deploy
npx wrangler deploy

# Upload a test image to R2
npx wrangler r2 object put user-uploads/test/cat.jpg --file=./fixtures/cat.jpg

# Classify it
curl -sX POST https://image-classifier.<account>.workers.dev/classify \
  -H 'Content-Type: application/json' \
  -d '{"r2Key": "test/cat.jpg"}' | jq .top5

# Query stored classifications
curl -s "https://image-classifier.<account>.workers.dev/classifications?r2Key=test/cat.jpg" | jq .
```

---

## Related

- `workers-ai-rag-chunking-vectorize.md`
- `workers-ai-sentiment-batch-analytics.md`

---

## Sources

- Cloudflare ResNet-50 model card — https://developers.cloudflare.com/workers-ai/models/resnet-50/
- Cloudflare R2 Workers binding — https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
