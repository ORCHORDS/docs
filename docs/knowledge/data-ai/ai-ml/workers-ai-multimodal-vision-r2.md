# Workers AI Multimodal Vision with R2 Image Storage

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to automatically analyse images stored in R2 — extracting structured metadata such as detected objects, dominant colours, and quality scores — and persist the results to a D1 `image_analyses` table for downstream querying. Pulling the image from R2, encoding it as base64, and calling the Workers AI vision model in a single Worker request keeps the entire pipeline on the Cloudflare network with no third-party egress.

---

## Context

`@cf/llava-hf/llava-1.5-7b-hf` is a multimodal model on Workers AI that accepts a `messages` array where image content is provided as a base64-encoded data URI alongside a text prompt. The model returns a text description; to get structured output you pair the vision call with a JSON extraction prompt. Results are stored in D1 with the R2 object key as a foreign key so you can later query analysed images without re-running inference. The Worker is triggered by an R2 event notification (or an HTTP webhook) whenever a new image is uploaded.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "vision-analysis-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[ai]
binding = "AI"

[[r2_buckets]]
binding = "IMAGES"
bucket_name = "product-images"

[[d1_databases]]
binding = "DB"
database_name = "vision_db"
database_id = "YOUR_D1_DATABASE_ID"
```

```sql
-- Run once to set up D1
CREATE TABLE IF NOT EXISTS image_analyses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  r2_key TEXT NOT NULL UNIQUE,
  analysed_at TEXT NOT NULL,
  description TEXT,
  objects TEXT,          -- JSON array of detected object labels
  dominant_colors TEXT,  -- JSON array of hex strings
  quality_score REAL,    -- 0.0 – 1.0
  raw_response TEXT      -- full model text for audit
);

CREATE INDEX IF NOT EXISTS idx_r2_key ON image_analyses (r2_key);
```

## Section 2 — Worker implementation

```typescript
import { Ai } from "@cloudflare/workers-types";

export interface Env {
  AI: Ai;
  IMAGES: R2Bucket;
  DB: D1Database;
}

const VISION_MODEL = "@cf/llava-hf/llava-1.5-7b-hf";

/** Fetch image from R2, return as base64 data URI */
async function r2ToDataUri(bucket: R2Bucket, key: string): Promise<string> {
  const object = await bucket.get(key);
  if (!object) throw new Error(`R2 object not found: ${key}`);

  const contentType = object.httpMetadata?.contentType ?? "image/jpeg";
  const arrayBuffer = await object.arrayBuffer();

  // Convert ArrayBuffer → base64
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const base64 = btoa(binary);

  return `data:${contentType};base64,${base64}`;
}

/** Run vision model and return raw text */
async function describeImage(ai: Ai, dataUri: string): Promise<string> {
  const result = (await ai.run(VISION_MODEL, {
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image_url",
            image_url: { url: dataUri },
          },
          {
            type: "text",
            text: [
              "Analyse this image and respond with a JSON object containing:",
              '"description": a one-sentence summary,',
              '"objects": array of up to 10 detected object labels (strings),',
              '"dominant_colors": array of up to 5 hex color codes (e.g. "#3a7bd5"),',
              '"quality_score": float 0.0–1.0 representing overall image clarity.',
              "Respond with ONLY the JSON object, no markdown fences.",
            ].join(" "),
          },
        ],
      },
    ],
  })) as { response: string };

  return result.response;
}

interface ImageAnalysis {
  description: string;
  objects: string[];
  dominant_colors: string[];
  quality_score: number;
}

/** Parse and coerce the model's text response into a structured object */
function parseAnalysis(raw: string): ImageAnalysis {
  // Strip potential markdown fences the model might still emit
  const cleaned = raw
    .replace(/^```(?:json)?\n?/i, "")
    .replace(/\n?```$/, "")
    .trim();

  const parsed = JSON.parse(cleaned) as Partial<ImageAnalysis>;

  return {
    description: String(parsed.description ?? ""),
    objects: Array.isArray(parsed.objects)
      ? parsed.objects.slice(0, 10).map(String)
      : [],
    dominant_colors: Array.isArray(parsed.dominant_colors)
      ? parsed.dominant_colors.slice(0, 5).map(String)
      : [],
    quality_score: Math.min(
      1,
      Math.max(0, Number(parsed.quality_score ?? 0))
    ),
  };
}

async function analyseAndStore(
  env: Env,
  r2Key: string
): Promise<ImageAnalysis> {
  const dataUri = await r2ToDataUri(env.IMAGES, r2Key);
  const rawResponse = await describeImage(env.AI, dataUri);
  const analysis = parseAnalysis(rawResponse);

  await env.DB.prepare(
    `INSERT INTO image_analyses
       (r2_key, analysed_at, description, objects, dominant_colors, quality_score, raw_response)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(r2_key) DO UPDATE SET
       analysed_at = excluded.analysed_at,
       description = excluded.description,
       objects = excluded.objects,
       dominant_colors = excluded.dominant_colors,
       quality_score = excluded.quality_score,
       raw_response = excluded.raw_response`
  )
    .bind(
      r2Key,
      new Date().toISOString(),
      analysis.description,
      JSON.stringify(analysis.objects),
      JSON.stringify(analysis.dominant_colors),
      analysis.quality_score,
      rawResponse
    )
    .run();

  return analysis;
}
```

## Section 3 — Request handler (HTTP webhook + direct lookup)

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /analyse — trigger analysis for a given R2 key
    if (request.method === "POST" && url.pathname === "/analyse") {
      const { r2_key } = (await request.json()) as { r2_key?: string };
      if (!r2_key) {
        return Response.json({ error: "Missing r2_key" }, { status: 400 });
      }

      try {
        const analysis = await analyseAndStore(env, r2_key);
        return Response.json({ r2_key, analysis });
      } catch (err) {
        return Response.json(
          { error: (err as Error).message },
          { status: 500 }
        );
      }
    }

    // GET /analysis?key=<r2_key> — retrieve cached analysis from D1
    if (request.method === "GET" && url.pathname === "/analysis") {
      const key = url.searchParams.get("key");
      if (!key) {
        return Response.json({ error: "Missing key param" }, { status: 400 });
      }

      const row = await env.DB.prepare(
        "SELECT * FROM image_analyses WHERE r2_key = ?"
      )
        .bind(key)
        .first();

      if (!row) {
        return Response.json({ error: "Not found" }, { status: 404 });
      }

      return Response.json(row);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Loading large images without size checks** — A 20 MB R2 object will exceed memory limits; add a `size` check on `object.size` before calling `arrayBuffer()` and reject oversized inputs.
- **Storing raw base64 in D1** — The data URI is transient; only the model's text output and parsed metadata belong in D1. R2 is the source of truth for the binary.
- **No idempotency on re-analysis** — Use `ON CONFLICT … DO UPDATE` (upsert) so re-running analysis for the same key overwrites stale results instead of throwing a unique constraint error.
- **Trusting the model's color codes without validation** — Hex values may be malformed; validate with a `/^#[0-9a-f]{6}$/i` regex before storing.

---

## Gotchas

- `btoa` works in the Workers runtime but is synchronous and CPU-heavy for large images; for files over ~2 MB consider streaming the R2 object through a `TransformStream` to avoid long CPU ticks.
- LLaVA 1.5 may include its own markdown fencing or preamble text before the JSON; always strip `` ``` `` fences before parsing.
- R2 `httpMetadata.contentType` can be `undefined` if the uploader did not set it; always fall back to `"image/jpeg"` or sniff the magic bytes.
- Workers AI vision models count image tokens against the context limit; very high-resolution images are automatically downsampled by the runtime but the exact behaviour is model-specific.

---

## Verification

```bash
# Upload a test image to R2
npx wrangler r2 object put product-images/test-shoe.jpg \
  --file ./test-shoe.jpg --content-type image/jpeg

# Start dev server
npx wrangler dev --remote

# Trigger analysis
curl -X POST http://localhost:8787/analyse \
  -H 'Content-Type: application/json' \
  -d '{"r2_key": "test-shoe.jpg"}'

# Retrieve cached result
curl 'http://localhost:8787/analysis?key=<redacted-secret>

# Inspect D1 directly
npx wrangler d1 execute vision_db --remote \
  --command "SELECT r2_key, quality_score, objects FROM image_analyses LIMIT 5"
```

---

## Related

- `workers-ai-structured-output-json-schema.md`
- `workers-ai-embeddings-semantic-search-vectorize.md`

---

## Sources

- Cloudflare Workers AI models — https://developers.cloudflare.com/workers-ai/models/
- Cloudflare R2 documentation — https://developers.cloudflare.com/r2/
- LLaVA model card — https://huggingface.co/llava-hf/llava-1.5-7b-hf
