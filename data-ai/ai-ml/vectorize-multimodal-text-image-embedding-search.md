# Vectorize Multimodal Text-Image Embedding Search

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need a search endpoint that accepts either a text query or an image and returns
results that may be text documents, images, or mixed. Users type "red running shoes"
and get both product descriptions and product photos ranked together. Or they upload
a photo of a shoe and get similar images plus matching text descriptions — all from
one Vectorize index.

---

## Context

Cloudflare Workers AI exposes `@cf/openai/clip-vit-base-patch32` (CLIP), which maps
text and images into the **same 512-dimensional embedding space**. Because both
modalities share a common latent space, cosine similarity between a text vector and
an image vector is meaningful. Vectorize holds all vectors regardless of source
modality; metadata carries a `type` field (`"text"` | `"image"`) so the UI can render
results correctly. The ingestion path is two separate Workers (one for images via R2,
one for text documents), both writing to the same Vectorize index.

Architecture overview:

```
Text doc → text-ingest Worker  ─────────────────────────────┐
Image URL → image-ingest Worker (R2 fetch → base64) ────────┼─→ vectorize index
                                                             │
query Worker (text or image) ──────────────────────────────→ vectorize.query()
```

---

## 1 · Ingest Text Documents

```typescript
// workers/text-ingest.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
}

interface TextDoc {
  id: string;
  content: string;
  title: string;
  url: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

    const doc: TextDoc = await request.json();

    // CLIP text embeddings — same space as image embeddings
    const result = await env.AI.run("@cf/openai/clip-vit-base-patch32", {
      text: [doc.content.slice(0, 77)], // CLIP token limit
    });

    const vector = result.data?.[0];
    if (!Array.isArray(vector)) {
      return new Response(JSON.stringify({ error: "embedding failed" }), { status: 502 });
    }

    await env.VECTORIZE.upsert([
      {
        id: `text:${doc.id}`,
        values: vector as number[],
        metadata: {
          type: "text",
          title: doc.title,
          url: doc.url,
          snippet: doc.content.slice(0, 200),
        },
      },
    ]);

    return new Response(JSON.stringify({ ok: true, id: `text:${doc.id}` }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 2 · Ingest Images from R2

```typescript
// workers/image-ingest.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  IMAGE_BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

    const { id, r2Key, altText }: { id: string; r2Key: string; altText?: string } =
      await request.json();

    const obj = await env.IMAGE_BUCKET.get(r2Key);
    if (!obj) return new Response("Image not found in R2", { status: 404 });

    const arrayBuffer = await obj.arrayBuffer();
    const base64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
    const mimeType = obj.httpMetadata?.contentType ?? "image/jpeg";

    // CLIP image embeddings — same latent space as text
    const result = await env.AI.run("@cf/openai/clip-vit-base-patch32", {
      image: base64,
    });

    const vector = result.data?.[0];
    if (!Array.isArray(vector)) {
      return new Response(JSON.stringify({ error: "image embedding failed" }), { status: 502 });
    }

    await env.VECTORIZE.upsert([
      {
        id: `image:${id}`,
        values: vector as number[],
        metadata: {
          type: "image",
          r2Key,
          altText: altText ?? "",
          mimeType,
        },
      },
    ]);

    return new Response(JSON.stringify({ ok: true, id: `image:${id}` }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 3 · Unified Query Worker

```typescript
// workers/multimodal-search.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
}

type QueryMode = "text" | "image";

interface SearchResult {
  id: string;
  score: number;
  type: "text" | "image";
  metadata: Record<string, string>;
}

async function embedText(env: Env, query: string): Promise<number[]> {
  const result = await env.AI.run("@cf/openai/clip-vit-base-patch32", {
    text: [query.slice(0, 77)],
  });
  return result.data?.[0] as number[];
}

async function embedImage(env: Env, base64: string): Promise<number[]> {
  const result = await env.AI.run("@cf/openai/clip-vit-base-patch32", {
    image: base64,
  });
  return result.data?.[0] as number[];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const mode = (url.searchParams.get("mode") ?? "text") as QueryMode;
    const topK = Math.min(parseInt(url.searchParams.get("k") ?? "10", 10), 50);
    const filterType = url.searchParams.get("type"); // "text" | "image" | null (all)

    let queryVector: number[];

    if (mode === "text") {
      const q = url.searchParams.get("q");
      if (!q) return new Response("Missing ?q", { status: 400 });
      queryVector = await embedText(env, q);
    } else {
      // image query: body is raw image bytes
      const arrayBuffer = await request.arrayBuffer();
      const base64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
      queryVector = await embedImage(env, base64);
    }

    const queryOpts: VectorizeQueryOptions = {
      topK,
      returnMetadata: "all",
      returnValues: false,
    };

    if (filterType === "text" || filterType === "image") {
      queryOpts.filter = { type: { $eq: filterType } };
    }

    const matches = await env.VECTORIZE.query(queryVector, queryOpts);

    const results: SearchResult[] = matches.matches.map((m) => ({
      id: m.id,
      score: m.score,
      type: (m.metadata?.type as "text" | "image") ?? "text",
      metadata: (m.metadata ?? {}) as Record<string, string>,
    }));

    return new Response(JSON.stringify({ results }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 4 · wrangler.toml Binding

```toml
name = "multimodal-search"
main = "workers/multimodal-search.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[vectorize]]
binding = "VECTORIZE"
index_name = "multimodal-index"

[[r2_buckets]]
binding = "IMAGE_BUCKET"
bucket_name = "product-images"
```

Create the index with dimension 512 and cosine similarity:

```bash
npx wrangler vectorize create multimodal-index \
  --dimensions=512 \
  --metric=cosine
```

---

## 5 · Result Renderer (Edge HTML)

```typescript
// Minimal HTML renderer — attach to the search worker or a separate Worker
function renderResults(results: SearchResult[]): string {
  const rows = results
    .map((r) => {
      if (r.type === "image") {
        return `<li>🖼 <strong>${r.metadata.altText || r.id}</strong>
          (score: ${r.score.toFixed(3)})</li>`;
      }
      return `<li>📄 <a >${r.metadata.title}</a>
        — ${r.metadata.snippet} (score: ${r.score.toFixed(3)})</li>`;
    })
    .join("\n");
  return `<ul>${rows}</ul>`;
}
```

---

## Anti-patterns

- **Separate indexes per modality** — defeats cross-modal ranking; keep one shared index.
- **Different embedding models per modality** — CLIP must be used for both sides or vectors are
  not comparable. Mixing `@cf/baai/bge-base-en-v1.5` for text and CLIP for images produces
  garbage rankings.
- **Truncating image dimensions** — CLIP outputs exactly 512 floats; do not slice or pad.
- **Storing raw base64 in Vectorize metadata** — metadata has a 10 KB limit per vector;
  store the R2 key instead and reconstruct the image URL at query time.
- **Querying without topK cap** — large topK with `returnValues: true` on a 512-dim index
  has meaningful egress cost; always cap at 50 and omit `returnValues` in production.

---

## Gotchas

- CLIP text input is capped at 77 tokens (≈ 60–70 English words). Longer text must be
  summarized first with another Workers AI model before embedding.
- `btoa` in Workers fails on binary data larger than ~2 MB — for large images, resize to
  ≤ 512×512 or use a streaming base64 approach before calling the model.
- `returnMetadata: "all"` is needed to get every metadata field back; `returnMetadata: "indexed"`
  returns only fields listed in the index configuration.
- Vectorize cosine similarity scores are in [0, 1]; a score below 0.20 for cross-modal
  (text → image) queries usually means the query concept has no visual analog in your index.
- The CLIP model on Workers AI is the ViT-B/32 variant — 512 dims, not 768.

---

## Verification

```bash
# Ingest a text doc
curl -X POST https://text-ingest.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"id":"doc1","content":"red running shoes","title":"Nike Air Max","url":"https://example.com/p/1"}'

# Text query
curl "https://multimodal-search.workers.dev?q=running+shoes&k=5"

# Image query (cross-modal: photo → text+images ranked together)
curl -X POST "https://multimodal-search.workers.dev?mode=image&k=5" \
  --data-binary @shoe.jpg

# Filter to images only
curl "https://multimodal-search.workers.dev?q=red+shoe&k=5&type=image"
```

Expected: text query returns both `text:` and `image:` ids ranked by cosine similarity.
Cross-modal image query returns text documents about visually similar products.

---

## Related

- `embedding-models-vector-search-cloudflare.md`
- `workers-ai-multimodal-image-text-classification.md`
- `vectorize-metadata-filtering-complex-predicates.md`
- `multimodal-embeddings-clip.md`
- `vectorize-approximate-nearest-neighbor-tuning.md`

---

## Sources

- Cloudflare Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- CLIP paper (Radford et al., 2021): https://arxiv.org/abs/2103.00020
- Vectorize metadata filtering: https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
