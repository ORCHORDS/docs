# Workers AI Entity Extraction with Structured Output Stored in D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You receive unstructured text — user reviews, support tickets, news articles — and need to
extract named entities (people, organizations, locations, dates, product names, prices) as
structured records, then store them in D1 for downstream querying and analytics. The output
must be deterministic JSON, not prose, so it can be inserted into D1 without post-processing.

---

## Context

Workers AI provides two complementary approaches:

1. **JSON-mode constrained generation** (`@cf/meta/llama-3.1-8b-instruct` with `response_format`)
   — sends a JSON Schema and forces the model to emit valid JSON matching that schema.
2. **Dedicated NER model** (`@cf/dslim/bert-base-NER`) — fast, low-latency entity tagging
   (PERSON, ORG, LOC, MISC) without an LLM token budget.

This article covers the LLM JSON-mode path because it supports arbitrary entity types and
confidence scores. The BERT-NER path is covered in `named-entity-recognition-content-moderation.md`.

Pipeline:

```
Incoming text  →  Workers AI (JSON-mode LLM)  →  Zod validation
                                                        ↓
                                              D1 INSERT (entities table)
                                                        ↓
                                              Response: { entities, documentId }
```

---

## 1 · D1 Schema

```sql
-- Apply: wrangler d1 execute ENTITY_DB --file=schema.sql
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  source_text TEXT NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS entities (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id TEXT    NOT NULL REFERENCES documents(id),
  entity_type TEXT    NOT NULL,   -- PERSON | ORG | LOCATION | DATE | PRODUCT | PRICE
  entity_text TEXT    NOT NULL,
  start_char  INTEGER,
  end_char    INTEGER,
  confidence  REAL    NOT NULL DEFAULT 1.0,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_entities_doc   ON entities(document_id);
CREATE INDEX IF NOT EXISTS idx_entities_type  ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_text  ON entities(entity_text);
```

---

## 2 · Entity Schema Definition (Zod + JSON Schema)

```typescript
// lib/entity-schema.ts
import { z } from "zod";

export const EntityTypeEnum = z.enum([
  "PERSON",
  "ORG",
  "LOCATION",
  "DATE",
  "PRODUCT",
  "PRICE",
]);

export const ExtractedEntitySchema = z.object({
  entity_type: EntityTypeEnum,
  entity_text: z.string().min(1).max(500),
  start_char: z.number().int().nonnegative().optional(),
  end_char: z.number().int().nonnegative().optional(),
  confidence: z.number().min(0).max(1),
});

export const ExtractionResultSchema = z.object({
  entities: z.array(ExtractedEntitySchema).max(100),
});

export type ExtractedEntity = z.infer<typeof ExtractedEntitySchema>;
export type ExtractionResult = z.infer<typeof ExtractionResultSchema>;

// JSON Schema for Workers AI response_format
export const EXTRACTION_JSON_SCHEMA = {
  type: "object",
  properties: {
    entities: {
      type: "array",
      items: {
        type: "object",
        properties: {
          entity_type: {
            type: "string",
            enum: ["PERSON", "ORG", "LOCATION", "DATE", "PRODUCT", "PRICE"],
          },
          entity_text: { type: "string" },
          start_char: { type: "integer" },
          end_char: { type: "integer" },
          confidence: { type: "number", minimum: 0, maximum: 1 },
        },
        required: ["entity_type", "entity_text", "confidence"],
      },
    },
  },
  required: ["entities"],
};
```

---

## 3 · Extraction Worker

```typescript
// workers/extract.ts
import { Ai } from "@cloudflare/ai";
import { z } from "zod";
import {
  ExtractionResultSchema,
  EXTRACTION_JSON_SCHEMA,
  ExtractedEntity,
} from "../lib/entity-schema";

export interface Env {
  AI: Ai;
  ENTITY_DB: D1Database;
}

const SYSTEM_PROMPT = `You are an expert named-entity recognition system.
Extract all entities from the provided text. For each entity provide:
- entity_type: one of PERSON, ORG, LOCATION, DATE, PRODUCT, PRICE
- entity_text: the exact text span as it appears in the input
- start_char: zero-based index of the first character
- end_char: zero-based index after the last character
- confidence: your confidence score (0.0–1.0)

Return a JSON object with an "entities" array. Include duplicates only once
(deduplicate by entity_text + entity_type).`;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const {
      text,
      documentId,
      minConfidence = 0.7,
    }: { text: string; documentId: string; minConfidence?: number } =
      await request.json();

    if (!text?.trim() || !documentId?.trim()) {
      return new Response(
        JSON.stringify({ error: "text and documentId are required" }),
        { status: 400 }
      );
    }

    // Trim to model context budget (~3 500 chars leaves room for prompt + output)
    const inputText = text.slice(0, 3500);

    // Workers AI JSON-mode extraction
    const aiResult = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: inputText },
      ],
      response_format: {
        type: "json_schema",
        json_schema: { name: "entity_extraction", schema: EXTRACTION_JSON_SCHEMA },
      },
      max_tokens: 1024,
      temperature: 0,
    });

    // Parse and validate with Zod
    let parsed: z.infer<typeof ExtractionResultSchema>;
    try {
      const raw = JSON.parse((aiResult as { response: string }).response);
      parsed = ExtractionResultSchema.parse(raw);
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "Extraction output failed validation", detail: String(err) }),
        { status: 422 }
      );
    }

    // Filter by confidence threshold
    const entities: ExtractedEntity[] = parsed.entities.filter(
      (e) => e.confidence >= minConfidence
    );

    // Persist to D1 in a transaction
    await persistEntities(env.ENTITY_DB, documentId, inputText, entities);

    return new Response(
      JSON.stringify({ documentId, entityCount: entities.length, entities }),
      { headers: { "Content-Type": "application/json" } }
    );
  },
};

async function persistEntities(
  db: D1Database,
  documentId: string,
  sourceText: string,
  entities: ExtractedEntity[]
): Promise<void> {
  const stmts: D1PreparedStatement[] = [];

  // Upsert document
  stmts.push(
    db.prepare(
      "INSERT OR IGNORE INTO documents (id, source_text) VALUES (?, ?)"
    ).bind(documentId, sourceText)
  );

  // Insert entities
  for (const ent of entities) {
    stmts.push(
      db
        .prepare(
          `INSERT INTO entities
             (document_id, entity_type, entity_text, start_char, end_char, confidence)
           VALUES (?, ?, ?, ?, ?, ?)`
        )
        .bind(
          documentId,
          ent.entity_type,
          ent.entity_text,
          ent.start_char ?? null,
          ent.end_char ?? null,
          ent.confidence
        )
    );
  }

  // D1 batch — all or nothing
  await db.batch(stmts);
}
```

---

## 4 · Query Endpoint

```typescript
// workers/query-entities.ts
export interface Env {
  ENTITY_DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const entityType = url.searchParams.get("type");
    const documentId = url.searchParams.get("document");
    const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "50", 10), 200);

    let query = "SELECT * FROM entities WHERE 1=1";
    const bindings: unknown[] = [];

    if (entityType) {
      query += " AND entity_type = ?";
      bindings.push(entityType.toUpperCase());
    }
    if (documentId) {
      query += " AND document_id = ?";
      bindings.push(documentId);
    }

    query += " ORDER BY created_at DESC LIMIT ?";
    bindings.push(limit);

    const { results } = await env.ENTITY_DB.prepare(query)
      .bind(...bindings)
      .all();

    return new Response(JSON.stringify({ results, count: results.length }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 5 · wrangler.toml

```toml
name = "entity-extraction"
main = "workers/extract.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[d1_databases]]
binding = "ENTITY_DB"
database_name = "entity-store"
database_id = "<YOUR_D1_DB_ID>"
```

---

## Anti-patterns

- **Parsing entity positions from model output without verification** — the model may hallucinate
  character offsets. Verify `entity_text === sourceText.slice(start_char, end_char)` before
  storing; drop mismatches rather than blindly trusting them.
- **Inserting entities one by one** — use `db.batch()` to send all inserts in a single round trip.
- **No confidence threshold** — without filtering, garbage low-confidence entities flood D1
  and degrade downstream analytics.
- **Returning raw model JSON to callers** — always validate through Zod before returning;
  the model may emit extra fields or wrong types.
- **Sending full multi-MB documents to the model** — chunk long documents and run extraction
  per chunk, then merge and deduplicate by `(entity_type, entity_text)`.

---

## Gotchas

- `response_format` with `json_schema` is supported in Workers AI as of late 2024 but only
  for instruction-tuned LLMs, not for BERT-family models.
- D1 `batch()` has a per-batch statement limit of 100; split into multiple batches for
  documents with more than ~95 entities.
- Zod's `.parse()` throws on invalid input — wrap in try/catch and return 422, not 500.
- D1 `INTEGER PRIMARY KEY AUTOINCREMENT` does not support `INSERT OR IGNORE` on the same
  primary key (it increments regardless); use a composite unique index on
  `(document_id, entity_type, entity_text)` if you need idempotent ingestion.
- `response_format` temperature should be 0 for structured extraction; non-zero temperatures
  increase JSON malformation rate.

---

## Verification

```bash
# Extract entities from a support ticket
curl -X POST https://entity-extraction.workers.dev \
  -H "Content-Type: application/json" \
  -d '{
    "documentId": "ticket-001",
    "text": "Hi, I am Sarah Chen from Acme Corp in San Francisco. My order #A-4421 for the UltraRun X5 (priced at $129.99) was placed on August 20, 2026.",
    "minConfidence": 0.7
  }'

# Expected
{
  "documentId": "ticket-001",
  "entityCount": 6,
  "entities": [
    { "entity_type": "PERSON",   "entity_text": "Sarah Chen",       "confidence": 0.97 },
    { "entity_type": "ORG",      "entity_text": "Acme Corp",        "confidence": 0.95 },
    { "entity_type": "LOCATION", "entity_text": "San Francisco",    "confidence": 0.99 },
    { "entity_type": "PRODUCT",  "entity_text": "UltraRun X5",      "confidence": 0.92 },
    { "entity_type": "PRICE",    "entity_text": "$129.99",          "confidence": 0.99 },
    { "entity_type": "DATE",     "entity_text": "August 20, 2026",  "confidence": 0.98 }
  ]
}

# Query all ORG entities
curl "https://entity-extraction.workers.dev/query?type=ORG&limit=20"
```

---

## Related

- `named-entity-recognition-content-moderation.md`
- `workers-ai-json-schema-constrained-generation.md`
- `llm-structured-extraction-zod-workers.md`
- `llm-structured-output-json-mode.md`
- `workers-ai-question-answering-d1-knowledge-base.md`

---

## Sources

- Workers AI JSON mode: https://developers.cloudflare.com/workers-ai/features/json-mode/
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Zod documentation: https://zod.dev/
- Workers AI LLaMA 3.1: https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
