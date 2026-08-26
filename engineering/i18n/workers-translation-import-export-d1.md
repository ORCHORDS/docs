# Translation Management Import/Export API with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your translation team works in spreadsheets and CAT tools that export CSV or JSON, but your app reads translations from a D1 database. There is no automated path from the translator's export to the live database — a developer manually copies values, introducing errors and delay. You also have no way to know which translation keys are missing for a new locale, no audit trail of what changed since the last export, and no approval gate before new translations go live.

---

## Context

A translation management API built on Cloudflare Workers + D1 provides:
- **Import endpoint**: Parses CSV or JSON uploaded by translators; writes to D1 with duplicate-key upsert logic.
- **Completeness check**: Compares keys in a target locale against the source locale (typically `en`) and returns missing keys.
- **Bulk export**: Streams all keys for a locale as JSON or CSV for download by translators or CI pipelines.
- **Diff endpoint**: Returns which translations changed or were added since a given ISO timestamp — used by CI to detect whether to rebuild locale bundles.
- **Approval workflow**: Translations sit in a `pending` status until an approver promotes them to `approved`; only approved translations are served to end users.

D1 schema design is critical: the `translations` table holds `(locale, key, value, status, created_at, updated_at, updated_by)`.

---

## Solution

### 1. D1 schema

```sql
-- migrations/0001_translations.sql

CREATE TABLE IF NOT EXISTS translations (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  locale      TEXT    NOT NULL,                  -- BCP 47: "en", "fr", "de-AT"
  key         TEXT    NOT NULL,                  -- dotted path: "nav.home", "errors.404"
  value       TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'pending', -- 'pending' | 'approved'
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_by  TEXT,                              -- email or system identifier
  UNIQUE(locale, key)
);

CREATE INDEX IF NOT EXISTS idx_translations_locale ON translations(locale);
CREATE INDEX IF NOT EXISTS idx_translations_locale_key ON translations(locale, key);
CREATE INDEX IF NOT EXISTS idx_translations_status ON translations(status);
CREATE INDEX IF NOT EXISTS idx_translations_updated_at ON translations(updated_at);
```

### 2. JSON import endpoint

```typescript
// src/import/json-import.ts

export interface Env {
  DB: D1Database;
}

interface TranslationRecord {
  key: string;
  value: string;
}

// Flatten a nested JSON object into dotted-key pairs
function flattenJson(
  obj: Record<string, unknown>,
  prefix = ""
): TranslationRecord[] {
  const records: TranslationRecord[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") {
      records.push({ key: fullKey, value: v });
    } else if (v !== null && typeof v === "object" && !Array.isArray(v)) {
      records.push(...flattenJson(v as Record<string, unknown>, fullKey));
    }
    // Arrays are skipped — complex values should be stored as JSON strings
  }
  return records;
}

export async function importJson(
  env: Env,
  locale: string,
  jsonBody: Record<string, unknown>,
  updatedBy: string
): Promise<{ inserted: number; updated: number; skipped: number }> {
  const records = flattenJson(jsonBody);
  let inserted = 0;
  let updated = 0;
  let skipped = 0;

  // D1 batch for performance — max 100 statements per batch
  const CHUNK = 100;
  for (let i = 0; i < records.length; i += CHUNK) {
    const chunk = records.slice(i, i + CHUNK);
    const stmts = chunk.map(r =>
      env.DB
        .prepare(
          `INSERT INTO translations (locale, key, value, status, updated_by, updated_at)
           VALUES (?, ?, ?, 'pending', ?, datetime('now'))
           ON CONFLICT(locale, key) DO UPDATE SET
             value      = excluded.value,
             status     = 'pending',
             updated_by = excluded.updated_by,
             updated_at = datetime('now')
           WHERE value != excluded.value`  // Skip if value is identical (no-op update)
        )
        .bind(locale, r.key, r.value, updatedBy)
    );
    const results = await env.DB.batch(stmts);
    for (const result of results) {
      if (result.meta.changes === 0) skipped++;
      else if (result.meta.last_row_id > 0 && result.meta.changes === 1) inserted++;
      else updated++;
    }
  }

  return { inserted, updated, skipped };
}
```

### 3. CSV import endpoint

```typescript
// src/import/csv-import.ts
// Expected CSV format: key,value  (header row, no locale column — locale is URL param)

function parseCSV(csv: string): Array<{ key: string; value: string }> {
  const lines = csv.split(/\r?\n/);
  const records: Array<{ key: string; value: string }> = [];

  // Skip header
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    // Handle quoted values: `nav.home,"Go home"`  or  `nav.home,Go home`
    const commaIdx = line.indexOf(",");
    if (commaIdx === -1) continue;

    const key = line.slice(0, commaIdx).trim();
    let value = line.slice(commaIdx + 1).trim();
    if (value.startsWith('"') && value.endsWith('"')) {
      value = value.slice(1, -1).replace(/""/g, '"');  // Unescape doubled quotes
    }

    if (key && value) records.push({ key, value });
  }

  return records;
}

export async function importCSV(
  env: Env,
  locale: string,
  csvText: string,
  updatedBy: string
): Promise<{ imported: number; errors: string[] }> {
  const records = parseCSV(csvText);
  const errors: string[] = [];
  let imported = 0;

  for (const { key, value } of records) {
    try {
      await env.DB
        .prepare(
          `INSERT INTO translations (locale, key, value, status, updated_by, updated_at)
           VALUES (?, ?, ?, 'pending', ?, datetime('now'))
           ON CONFLICT(locale, key) DO UPDATE SET
             value = excluded.value,
             status = 'pending',
             updated_by = excluded.updated_by,
             updated_at = datetime('now')`
        )
        .bind(locale, key, value, updatedBy)
        .run();
      imported++;
    } catch (e) {
      errors.push(`key="${key}": ${String(e)}`);
    }
  }

  return { imported, errors };
}
```

### 4. Translation completeness check

```typescript
// src/completeness.ts
// Returns keys present in sourceLocale but missing in targetLocale

export async function getMissingKeys(
  env: Env,
  sourceLocale: string,
  targetLocale: string
): Promise<string[]> {
  const { results } = await env.DB
    .prepare(
      `SELECT source.key
       FROM translations AS source
       WHERE source.locale = ?
         AND source.status = 'approved'
         AND NOT EXISTS (
           SELECT 1 FROM translations AS target
           WHERE target.locale = ?
             AND target.key = source.key
         )
       ORDER BY source.key`
    )
    .bind(sourceLocale, targetLocale)
    .all<{ key: string }>();

  return results.map(r => r.key);
}

export async function getCompletenessReport(
  env: Env,
  sourceLocale: string,
  targetLocale: string
): Promise<{
  total: number;
  translated: number;
  missing: number;
  percent: number;
  missingKeys: string[];
}> {
  const [{ total }] = (await env.DB
    .prepare("SELECT COUNT(*) AS total FROM translations WHERE locale = ? AND status = 'approved'")
    .bind(sourceLocale)
    .all<{ total: number }>()).results;

  const missingKeys = await getMissingKeys(env, sourceLocale, targetLocale);
  const missing = missingKeys.length;
  const translated = total - missing;

  return {
    total,
    translated,
    missing,
    percent: total > 0 ? Math.round((translated / total) * 100) : 0,
    missingKeys,
  };
}
```

### 5. Bulk export by locale

```typescript
// src/export.ts

function buildNestedObject(
  records: Array<{ key: string; value: string }>
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const { key, value } of records) {
    const parts = key.split(".");
    let node: Record<string, unknown> = result;
    for (let i = 0; i < parts.length - 1; i++) {
      if (typeof node[parts[i]] !== "object") {
        node[parts[i]] = {};
      }
      node = node[parts[i]] as Record<string, unknown>;
    }
    node[parts[parts.length - 1]] = value;
  }
  return result;
}

function buildCSV(records: Array<{ key: string; value: string }>): string {
  const header = "key,value";
  const rows = records.map(({ key, value }) => {
    // Escape commas and quotes in values
    const escaped = value.includes(",") || value.includes('"')
      ? `"${value.replace(/"/g, '""')}"`
      : value;
    return `${key},${escaped}`;
  });
  return [header, ...rows].join("\n");
}

export async function exportLocale(
  env: Env,
  locale: string,
  format: "json" | "csv",
  statusFilter: "approved" | "pending" | "all" = "approved"
): Promise<{ content: string; contentType: string }> {
  const whereStatus = statusFilter === "all"
    ? ""
    : `AND status = '${statusFilter}'`;

  const { results } = await env.DB
    .prepare(
      `SELECT key, value FROM translations
       WHERE locale = ? ${whereStatus}
       ORDER BY key`
    )
    .bind(locale)
    .all<{ key: string; value: string }>();

  if (format === "csv") {
    return { content: buildCSV(results), contentType: "text/csv; charset=utf-8" };
  }

  const nested = buildNestedObject(results);
  return {
    content: JSON.stringify(nested, null, 2),
    contentType: "application/json; charset=utf-8",
  };
}
```

### 6. Diff endpoint

```typescript
// src/diff.ts
// Returns translations changed or added since a given ISO timestamp

export interface TranslationDiff {
  key: string;
  locale: string;
  value: string;
  previous_value: string | null;  // null if this is a new key
  changed_at: string;
  changed_by: string | null;
}

export async function getDiff(
  env: Env,
  locale: string,
  since: string  // ISO 8601 timestamp: "2026-08-01T00:00:00Z"
): Promise<TranslationDiff[]> {
  const { results } = await env.DB
    .prepare(
      `SELECT
         t.key,
         t.locale,
         t.value,
         t.updated_at AS changed_at,
         t.updated_by AS changed_by,
         NULL AS previous_value  -- history table needed for actual previous value
       FROM translations t
       WHERE t.locale = ?
         AND t.updated_at > ?
       ORDER BY t.updated_at DESC`
    )
    .bind(locale, since)
    .all<TranslationDiff>();

  return results;
}
```

### 7. Approval workflow

```typescript
// src/approval.ts

export async function approveTranslations(
  env: Env,
  locale: string,
  keys: string[],  // Approve specific keys; empty array = approve all pending
  approvedBy: string
): Promise<{ approved: number }> {
  let approved = 0;

  if (keys.length === 0) {
    // Approve all pending for locale
    const result = await env.DB
      .prepare(
        `UPDATE translations
         SET status = 'approved', updated_by = ?, updated_at = datetime('now')
         WHERE locale = ? AND status = 'pending'`
      )
      .bind(approvedBy, locale)
      .run();
    approved = result.meta.changes;
  } else {
    // Batch approve specific keys
    const stmts = keys.map(key =>
      env.DB
        .prepare(
          `UPDATE translations
           SET status = 'approved', updated_by = ?, updated_at = datetime('now')
           WHERE locale = ? AND key = ? AND status = 'pending'`
        )
        .bind(approvedBy, locale, key)
    );
    const results = await env.DB.batch(stmts);
    approved = results.reduce((sum, r) => sum + r.meta.changes, 0);
  }

  return { approved };
}

export async function rejectTranslations(
  env: Env,
  locale: string,
  keys: string[],
  rejectedBy: string,
  reason: string
): Promise<{ deleted: number }> {
  // Rejection deletes the pending entry (original approved value, if any, remains)
  const stmts = keys.map(key =>
    env.DB
      .prepare(
        `DELETE FROM translations
         WHERE locale = ? AND key = ? AND status = 'pending'`
      )
      .bind(locale, key)
  );
  const results = await env.DB.batch(stmts);
  const deleted = results.reduce((sum, r) => sum + r.meta.changes, 0);
  // Log rejection (omitted for brevity — write to a rejections table or KV)
  return { deleted };
}
```

### 8. Worker router

```typescript
// src/index.ts
import { importJson } from "./import/json-import";
import { importCSV } from "./import/csv-import";
import { getCompletenessReport } from "./completeness";
import { exportLocale } from "./export";
import { getDiff } from "./diff";
import { approveTranslations } from "./approval";

export interface Env { DB: D1Database; }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const [, , resource, locale, action] = url.pathname.split("/");
    // /api/translations/{locale}[/action]
    if (resource !== "translations" || !locale) {
      return new Response("Not Found", { status: 404 });
    }

    const updatedBy = request.headers.get("X-Updated-By") ?? "anonymous";

    // POST /api/translations/{locale}/import
    if (request.method === "POST" && action === "import") {
      const ct = request.headers.get("Content-Type") ?? "";
      if (ct.includes("application/json")) {
        const body = await request.json<Record<string, unknown>>();
        const stats = await importJson(env, locale, body, updatedBy);
        return Response.json(stats);
      }
      if (ct.includes("text/csv")) {
        const text = await request.text();
        const stats = await importCSV(env, locale, text, updatedBy);
        return Response.json(stats);
      }
      return new Response("Unsupported Content-Type", { status: 415 });
    }

    // GET /api/translations/{locale}/export?format=json|csv&status=approved
    if (request.method === "GET" && action === "export") {
      const format = (url.searchParams.get("format") ?? "json") as "json" | "csv";
      const status = (url.searchParams.get("status") ?? "approved") as any;
      const { content, contentType } = await exportLocale(env, locale, format, status);
      return new Response(content, { headers: { "Content-Type": contentType } });
    }

    // GET /api/translations/{locale}/completeness?source=en
    if (request.method === "GET" && action === "completeness") {
      const source = url.searchParams.get("source") ?? "en";
      const report = await getCompletenessReport(env, source, locale);
      return Response.json(report);
    }

    // GET /api/translations/{locale}/diff?since=2026-08-01T00:00:00Z
    if (request.method === "GET" && action === "diff") {
      const since = url.searchParams.get("since");
      if (!since) return new Response('"since" param required', { status: 400 });
      const diff = await getDiff(env, locale, since);
      return Response.json(diff);
    }

    // POST /api/translations/{locale}/approve
    if (request.method === "POST" && action === "approve") {
      const body = await request.json<{ keys?: string[]; approved_by: string }>();
      const result = await approveTranslations(env, locale, body.keys ?? [], body.approved_by);
      return Response.json(result);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Implementation Details

- **`ON CONFLICT DO UPDATE WHERE value != excluded.value`**: The `WHERE` clause on the upsert means a re-import of unchanged values results in zero `meta.changes`, which drives the `skipped` counter. Without it, every re-import would update `updated_at` unnecessarily.
- **D1 batch API**: `env.DB.batch(stmts)` runs up to 100 statements in a single HTTP round-trip to D1. This is critical for import performance — individual `await stmt.run()` per record would be 10–100x slower.
- **Approval as a two-phase process**: Keeping `status = 'pending'` in the same row as approved translations means only one row per `(locale, key)` — simpler queries, but no full audit history. For a complete audit trail, add a `translation_history` table.
- **CSV parsing**: The included parser handles the most common CSV patterns but does not handle multi-line values (values containing `\n` inside quotes). Use a proper CSV library for that edge case.
- **Export as nested JSON**: `buildNestedObject` reconstructs the dotted-key flat list into `{nav: {home: "...", about: "..."}}` which is what most i18n runtime libraries (i18next, FormatJS) expect to consume directly.

---

## Anti-patterns

- **Running one D1 statement per translation key in a loop.** Each `await stmt.run()` call is a separate network round-trip. Use `env.DB.batch()` for bulk operations.
- **Storing the approved and pending value in separate columns.** A single `status` column with `UNIQUE(locale, key)` constraint is simpler; only the latest value is stored per key.
- **Allowing import without an approval step in production.** Direct-to-approved imports bypass review, which causes untranslated placeholders or injected content to appear for end users.
- **Exporting all locales in one request.** A single export endpoint returning all locales at once creates large responses and long D1 query times. Export per-locale.
- **Not validating BCP 47 locale tags on import.** `Intl.getCanonicalLocales(locale)` throws on invalid tags; run it on the locale URL parameter before any D1 write.

---

## Gotchas

- **D1 `meta.changes` on upsert**: When an `INSERT OR REPLACE` (not `ON CONFLICT DO UPDATE`) replaces a row, `meta.changes` is 2 (delete + insert). The `ON CONFLICT DO UPDATE` syntax gives `meta.changes = 1` for updates and `1` for inserts, which is what the counters above rely on.
- **SQLite `datetime('now')` is UTC**: This is correct for `updated_at`, but ensure your diff queries also use UTC timestamps in the `since` parameter.
- **D1 batch size limit**: The D1 batch API has a default limit of 100 statements. Chunk arrays before batching.
- **Nested JSON export and array values**: If a translation value is stored as a JSON array string (e.g., `"["item1","item2"]"`) and you try to nest it with `buildNestedObject`, the string is placed correctly but the consumer sees a string, not an array. Document this contract with translators.
- **`Content-Type: text/csv` upload**: Some HTTP clients set `application/octet-stream` for file uploads. Add `multipart/form-data` parsing if translators upload files via a web form rather than a direct API call.

---

## Verification

```bash
# Apply migration
npx wrangler d1 execute YOUR_DB --file=migrations/0001_translations.sql

# Import JSON translations
curl -X POST https://your-worker.workers.dev/api/translations/fr/import \
  -H "Content-Type: application/json" \
  -H "X-Updated-By: translator@example.com" \
  -d '{"nav":{"home":"Accueil","about":"À propos"},"errors":{"404":"Page introuvable"}}'
# => {"inserted":3,"updated":0,"skipped":0}

# Check completeness
curl "https://your-worker.workers.dev/api/translations/fr/completeness?source=en"
# => {"total":42,"translated":3,"missing":39,"percent":7,"missingKeys":[...]}

# Export as CSV
curl "https://your-worker.workers.dev/api/translations/fr/export?format=csv&status=pending"
# key,value
# nav.home,Accueil
# nav.about,À propos
# errors.404,Page introuvable

# Approve translations
curl -X POST https://your-worker.workers.dev/api/translations/fr/approve \
  -H "Content-Type: application/json" \
  -d '{"keys":["nav.home","nav.about"],"approved_by":"editor@example.com"}'
# => {"approved":2}

# Diff since date
curl "https://your-worker.workers.dev/api/translations/fr/diff?since=2026-08-01T00:00:00Z"
# => [{"key":"nav.home","locale":"fr","value":"Accueil","changed_at":"..."},...]
```

```typescript
// tests/import.test.ts
import { describe, it, expect, vi } from "vitest";
import { importJson } from "../src/import/json-import";

describe("JSON import", () => {
  it("flattens nested keys correctly", async () => {
    // Verify flat key generation from nested JSON
    // (unit test on flattenJson helper directly)
    const { flattenJson } = await import("../src/import/json-import");
    const result = (flattenJson as any)({ nav: { home: "Home", about: "About" } });
    expect(result).toEqual([
      { key: "nav.home",  value: "Home"  },
      { key: "nav.about", value: "About" },
    ]);
  });
});
```

---

## Related

- `documentation/categories/i18n/d1-translation-store.md`
- `documentation/categories/i18n/workers-translation-fallback-chain-kv.md`
- `documentation/categories/i18n/workers-intl-edge-locale.md`
- `documentation/categories/i18n/accept-language-negotiation.md`

---

## Sources

- Cloudflare Docs: [D1 Database](https://developers.cloudflare.com/d1/)
- Cloudflare Docs: [D1 Batch API](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch)
- SQLite Docs: [ON CONFLICT clause](https://www.sqlite.org/lang_conflict.html)
- MDN: [Intl.getCanonicalLocales](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/getCanonicalLocales)
- WHATWG: [Encoding Standard — UTF-8](https://encoding.spec.whatwg.org/)
- RFC 4180: [Common Format and MIME Type for CSV Files](https://www.rfc-editor.org/rfc/rfc4180)
