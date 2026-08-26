# Workers AI SQL Query Generation for D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to let users query a D1 database using plain English ("show me top 10 customers by revenue last month") without writing SQL. Workers AI translates the natural-language query into a safe, parameterized SQL statement that D1 then executes, with the result formatted back as prose or structured JSON.

## Context

Workers AI hosts code-generation models (e.g. `@cf/defog/sqlcoder-7b-2`, `@cf/mistral/mistral-7b-instruct-v0.1`) that can produce SQL from a schema description + user intent. The pipeline is: (1) inject schema, (2) generate SQL, (3) validate/sanitize, (4) execute on D1, (5) format response. All steps run inside a single Worker with zero cold-start penalty for AI inference.

---

## Schema Introspection

Retrieve the live schema from D1 at startup or via a cached KV snapshot so the model always has accurate table/column names.

```typescript
// schema-loader.ts
export async function loadSchema(db: D1Database, kv: KVNamespace): Promise<string> {
  const cached = await kv.get("schema:v1");
  if (cached) return cached;

  const { results } = await db
    .prepare("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    .all<{ name: string; sql: string }>();

  const schema = results.map(r => r.sql).join("\n\n");
  await kv.put("schema:v1", schema, { expirationTtl: 3600 });
  return schema;
}
```

---

## SQL Generation Prompt

Structure the prompt so the model emits only a SELECT statement with no preamble.

```typescript
// sql-generator.ts
export async function generateSQL(
  ai: Ai,
  schema: string,
  userQuery: string
): Promise<string> {
  const systemPrompt = `You are an expert SQL assistant for SQLite/D1.
Given the schema below, generate a single valid SELECT statement that answers the user question.
Rules:
- Output ONLY the SQL statement, no explanations.
- Use parameterized placeholders ($1, $2 …) when user values appear in WHERE clauses.
- Never use DROP, INSERT, UPDATE, DELETE, CREATE, ALTER, or ATTACH.
- Limit results to 100 rows unless the user specifies otherwise.

SCHEMA:
${schema}`;

  const response = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userQuery }
    ],
    max_tokens: 256,
    temperature: 0
  });

  return (response as { response: string }).response.trim();
}
```

---

## SQL Validation and Sanitization

Block any statement that isn't a SELECT before it reaches D1.

```typescript
// sql-validator.ts
const FORBIDDEN = /^\s*(DROP|INSERT|UPDATE|DELETE|CREATE|ALTER|ATTACH|PRAGMA|VACUUM)/i;
const SELECT_ONLY = /^\s*SELECT\b/i;

export function validateSQL(sql: string): { ok: boolean; error?: string } {
  if (FORBIDDEN.test(sql)) return { ok: false, error: "Mutation statements are not allowed." };
  if (!SELECT_ONLY.test(sql)) return { ok: false, error: "Only SELECT statements are permitted." };
  if (sql.length > 2000) return { ok: false, error: "Generated query too long." };
  return { ok: true };
}
```

---

## D1 Execution and Result Formatting

Execute the validated SQL, then use Workers AI to turn the result set into a human-readable answer.

```typescript
// query-executor.ts
export async function runQuery(
  db: D1Database,
  sql: string,
  params: unknown[] = []
): Promise<{ rows: Record<string, unknown>[]; meta: D1Meta }> {
  const stmt = db.prepare(sql);
  const result = params.length ? await stmt.bind(...params).all() : await stmt.all();
  return { rows: result.results as Record<string, unknown>[], meta: result.meta };
}

export async function formatAnswer(
  ai: Ai,
  userQuery: string,
  rows: Record<string, unknown>[]
): Promise<string> {
  if (rows.length === 0) return "No records matched your query.";

  const data = JSON.stringify(rows.slice(0, 20));
  const { response } = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    messages: [
      { role: "system", content: "Summarize the following query results concisely in plain English." },
      { role: "user", content: `Question: ${userQuery}\n\nResults (JSON): ${data}` }
    ],
    max_tokens: 256,
    temperature: 0.3
  }) as { response: string };
  return response;
}
```

---

## Worker Entry Point

```typescript
// worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query } = await req.json<{ query: string }>();
    if (!query?.trim()) return new Response("Missing query", { status: 400 });

    const schema = await loadSchema(env.DB, env.KV);
    const sql = await generateSQL(env.AI, schema, query);

    const validation = validateSQL(sql);
    if (!validation.ok) return Response.json({ error: validation.error }, { status: 422 });

    const { rows } = await runQuery(env.DB, sql);
    const answer = await formatAnswer(env.AI, query, rows);

    return Response.json({ sql, rowCount: rows.length, answer });
  }
};
```

---

## Anti-patterns

- **Executing raw LLM output directly** — always validate before executing; models do occasionally emit DML.
- **Omitting row limits** — without a LIMIT guard, an adversarial query can dump an entire table.
- **Using schema introspection on every request** — cache the schema in KV; D1 metadata calls add latency.
- **Showing generated SQL to untrusted users** — it reveals schema details; log it server-side only.
- **Trusting model-emitted parameters** — if the model inlines literal values instead of placeholders, strip and re-parameterize or reject.

## Gotchas

- SQLite has no `ILIKE`; use `LOWER(col) LIKE LOWER(?)` in your system prompt examples.
- D1 `stmt.all()` returns at most 1,000 rows; document this to users.
- `sqlcoder-7b-2` is better at SQL accuracy; `mistral-7b-instruct` is faster and cheaper for simpler schemas — benchmark both.
- Multi-table JOIN queries sometimes alias columns identically; instruct the model to use `AS` aliases.
- Schema caching must be invalidated on migrations; hook your migration script to `kv.delete("schema:v1")`.

## Verification

```bash
# End-to-end smoke test
curl -X POST https://your-worker.workers.dev/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How many users signed up last week?"}'

# Expected: { "sql": "SELECT COUNT(*) AS count FROM users WHERE ...", "rowCount": 1, "answer": "..." }

# Reject mutation attempt
curl -X POST https://your-worker.workers.dev/query \
  -d '{"query": "delete all users"}'
# Expected: { "error": "Only SELECT statements are permitted." }
```

## Related

- `workers-ai-question-answering-d1-knowledge-base.md`
- `workers-ai-structured-output-parallel-tool-calls.md`
- `llm-function-calling-tool-use-patterns.md`
- `workers-ai-entity-extraction-structured-output-d1.md`
- `llm-prompt-injection-defense-workers.md`

## Sources

- Cloudflare Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- D1 query API: https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- Defog SQLCoder model: https://huggingface.co/defog/sqlcoder-7b-2
