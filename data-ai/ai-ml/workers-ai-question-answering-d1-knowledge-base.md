# Workers AI Question Answering over a D1 Knowledge Base

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a structured D1 database — product catalog, FAQ table, policy documents — and want
users to ask plain-English questions and get accurate, cited answers without hallucination.
Unlike Vectorize RAG, here the source of truth is relational rows, not free-form chunks.
The pipeline translates natural-language questions into SQL, executes the query, and feeds
verified rows to an LLM for answer synthesis.

---

## Context

This pattern is sometimes called **NL2SQL + answer synthesis**. It differs from classic RAG:

| Aspect           | Vectorize RAG              | D1 QA (this article)         |
|------------------|----------------------------|------------------------------|
| Data shape       | Unstructured text chunks   | Structured relational rows   |
| Retrieval method | ANN vector search          | SQL executed against D1      |
| Hallucination risk | Context drift            | SQL error or wrong join      |
| Grounding proof  | Chunk text in context      | Exact row values in context  |

The Worker uses `@cf/meta/llama-3.1-8b-instruct` (or any instruction model) twice:
once to generate SQL, once to synthesize the final answer from the returned rows.

---

## 1 · D1 Schema Setup

```sql
-- schema.sql (apply via: wrangler d1 execute KB_DB --file=schema.sql)
CREATE TABLE IF NOT EXISTS products (
  id       INTEGER PRIMARY KEY,
  name     TEXT    NOT NULL,
  category TEXT    NOT NULL,
  price    REAL    NOT NULL,
  in_stock INTEGER NOT NULL DEFAULT 1,  -- boolean
  description TEXT
);

CREATE TABLE IF NOT EXISTS faqs (
  id       INTEGER PRIMARY KEY,
  question TEXT NOT NULL,
  answer   TEXT NOT NULL,
  category TEXT NOT NULL
);

-- Seed example
INSERT INTO products (name, category, price, in_stock, description) VALUES
  ('UltraRun X5', 'Running Shoes', 129.99, 1, 'Lightweight mesh upper, carbon plate'),
  ('TrailBlazer Pro', 'Hiking Boots', 189.99, 0, 'Waterproof, Vibram sole');
```

---

## 2 · Schema Introspection Helper

The LLM needs to know the schema to write correct SQL. Build a compact schema string at
startup (or cache in KV with a TTL).

```typescript
// workers/schema-cache.ts
export interface Env {
  KB_DB: D1Database;
  SCHEMA_KV: KVNamespace;
}

const SCHEMA_KEY = "db_schema_v1";
const SCHEMA_TTL = 3600; // 1 hour

export async function getSchemaString(env: Env): Promise<string> {
  const cached = await env.SCHEMA_KV.get(SCHEMA_KEY);
  if (cached) return cached;

  // SQLite master table lists all tables and their CREATE statements
  const { results } = await env.KB_DB.prepare(
    "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
  ).all<{ name: string; sql: string }>();

  const schema = results.map((r) => r.sql).join(";\n\n");
  await env.SCHEMA_KV.put(SCHEMA_KEY, schema, { expirationTtl: SCHEMA_TTL });
  return schema;
}
```

---

## 3 · NL2SQL Generation

```typescript
// workers/nl2sql.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  KB_DB: D1Database;
  SCHEMA_KV: KVNamespace;
}

const SQL_SYSTEM = `You are an expert SQLite query generator.
Given the schema and a user question, output ONLY a single valid SQL SELECT query.
Rules:
- Use only tables and columns that exist in the schema.
- Never use DELETE, INSERT, UPDATE, DROP, or CREATE.
- If the question cannot be answered with SQL, output: SELECT 'UNANSWERABLE' AS reason;
- Do not add markdown fences. Output raw SQL only.`;

export async function generateSQL(
  env: Env,
  schema: string,
  question: string
): Promise<string> {
  const prompt = `Schema:\n${schema}\n\nQuestion: ${question}`;

  const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: SQL_SYSTEM },
      { role: "user", content: prompt },
    ],
    max_tokens: 256,
    temperature: 0,  // deterministic SQL generation
  });

  const sql = (result as { response: string }).response.trim();

  // Safety: block any non-SELECT statement
  if (!/^\s*SELECT\b/i.test(sql)) {
    throw new Error(`LLM generated non-SELECT SQL: ${sql.slice(0, 80)}`);
  }

  return sql;
}
```

---

## 4 · Answer Synthesis

```typescript
// workers/synthesize.ts
import { Ai } from "@cloudflare/ai";

const ANSWER_SYSTEM = `You are a helpful assistant. You will be given a user question
and rows from a database query. Answer the question concisely based ONLY on the
provided data. If the data does not contain enough information, say so honestly.
Always cite the relevant row values in your answer.`;

export async function synthesizeAnswer(
  env: { AI: Ai },
  question: string,
  rows: unknown[],
  sql: string
): Promise<string> {
  if (rows.length === 0) {
    return "No matching records were found in the database for your question.";
  }

  const dataContext = JSON.stringify(rows, null, 2).slice(0, 4000); // budget guard

  const result = await (env.AI as Ai).run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: ANSWER_SYSTEM },
      {
        role: "user",
        content: `Question: ${question}\n\nDatabase rows (from: ${sql}):\n${dataContext}`,
      },
    ],
    max_tokens: 512,
    temperature: 0.2,
  });

  return (result as { response: string }).response.trim();
}
```

---

## 5 · Main QA Worker

```typescript
// workers/qa.ts
import { Ai } from "@cloudflare/ai";
import { getSchemaString } from "./schema-cache";
import { generateSQL } from "./nl2sql";
import { synthesizeAnswer } from "./synthesize";

export interface Env {
  AI: Ai;
  KB_DB: D1Database;
  SCHEMA_KV: KVNamespace;
}

interface QAResponse {
  answer: string;
  sql: string;
  rowCount: number;
  rows?: unknown[];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const { question, debug = false }: { question: string; debug?: boolean } =
      await request.json();

    if (!question?.trim()) {
      return new Response(JSON.stringify({ error: "question is required" }), { status: 400 });
    }

    // Step 1: get schema
    const schema = await getSchemaString(env);

    // Step 2: generate SQL
    let sql: string;
    try {
      sql = await generateSQL(env, schema, question);
    } catch (err) {
      return new Response(
        JSON.stringify({ error: "SQL generation failed", detail: String(err) }),
        { status: 422 }
      );
    }

    // Step 3: execute SQL against D1 (read-only enforced by SELECT guard in nl2sql)
    let rows: unknown[];
    try {
      const stmt = env.KB_DB.prepare(sql);
      const result = await stmt.all();
      rows = result.results ?? [];
    } catch (err) {
      // SQL syntax error — return transparent error; do NOT retry automatically
      return new Response(
        JSON.stringify({ error: "SQL execution failed", sql, detail: String(err) }),
        { status: 422 }
      );
    }

    // Step 4: synthesize natural language answer
    const answer = await synthesizeAnswer(env, question, rows, sql);

    const response: QAResponse = {
      answer,
      sql,
      rowCount: rows.length,
      ...(debug ? { rows } : {}),
    };

    return new Response(JSON.stringify(response), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 6 · wrangler.toml

```toml
name = "d1-qa"
main = "workers/qa.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[d1_databases]]
binding = "KB_DB"
database_name = "knowledge-base"
database_id = "<YOUR_D1_DB_ID>"

[[kv_namespaces]]
binding = "SCHEMA_KV"
id = "<YOUR_KV_NAMESPACE_ID>"
```

---

## Anti-patterns

- **Skipping the SELECT-only guard** — an LLM will occasionally emit `DROP TABLE` when
  adversarially prompted; the guard in `generateSQL` must be present in production.
- **Sending the full D1 result set to the LLM** — D1 can return thousands of rows; always
  add `LIMIT 20` enforcement or check row count before synthesis.
- **Caching answers** — SQL answers are data-sensitive; cache the schema, not the QA output.
- **One model call for both SQL and synthesis** — splitting into two calls lets you independently
  tune temperature (0 for SQL, 0.2 for prose) and isolate failures.
- **Trusting user-supplied table names in the prompt** — always derive schema from `sqlite_master`,
  not from user input, to prevent prompt-injection that references shadow tables.

---

## Gotchas

- D1 `prepare().all()` returns `{ results: D1Result[] }` — the rows are in `.results`, not
  the root object.
- SQLite's `INTEGER` stores booleans as 0/1; include a note in the schema string so the LLM
  does not write `WHERE in_stock = true` (which evaluates correctly in SQLite but is confusing
  to future developers).
- `sqlite_master` includes indexes and triggers in addition to tables; filter with
  `WHERE type='table'` to avoid feeding the LLM non-table DDL.
- Workers AI has a per-request token limit (~2048 input tokens for smaller models);
  if the schema is very large, summarize it to only the tables likely relevant to your domain.
- D1 is eventually consistent across regions — avoid QA over recently-inserted rows in
  globally distributed setups unless the Worker is pinned to a region.

---

## Verification

```bash
# Ask a product question
curl -X POST https://d1-qa.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"question": "Which running shoes cost under $150 and are in stock?", "debug": true}'

# Expected response shape
{
  "answer": "The UltraRun X5 is a running shoe priced at $129.99 and is currently in stock.",
  "sql": "SELECT name, price, description FROM products WHERE category = 'Running Shoes' AND price < 150 AND in_stock = 1 LIMIT 20;",
  "rowCount": 1,
  "rows": [{ "name": "UltraRun X5", "price": 129.99, "description": "..." }]
}
```

---

## Related

- `retrieval-augmented-generation-d1-vectorize.md`
- `workers-ai-json-schema-constrained-generation.md`
- `llm-structured-output-json-mode.md`
- `ai-content-recommendation-collaborative-filtering-d1.md`
- `llm-prompt-injection-defense-workers.md`

---

## Sources

- Cloudflare D1 Workers binding: https://developers.cloudflare.com/d1/worker-api/
- Workers AI LLaMA 3.1: https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- Text2SQL survey (Katsogiannis-Meimarakis & Koutrika, 2023): https://arxiv.org/abs/2208.13629
- SQLite master table: https://www.sqlite.org/schematab.html
