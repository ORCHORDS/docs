# D1 JSON Column Injection Prevention

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your D1 schema stores semi-structured data in TEXT columns using JSON (SQLite's built-in JSON functions: `json_extract`, `json_patch`, `json_set`). A user-controlled value is passed into a JSON path expression or serialized into a JSON blob and stored, then queried with `json_extract`. Without careful handling, an attacker can escape the JSON structure, inject SQL through a malformed path argument, or poison the stored JSON to extract or overwrite sibling fields belonging to other tenants.

## Context

SQLite (D1's engine) has native JSON1 extension functions: `json()`, `json_extract()`, `json_set()`, `json_patch()`, `json_insert()`, `json_replace()`, `json_each()`, `json_tree()`. These functions accept path expressions using `$.field` syntax. Path arguments are strings and, unlike SQL parameters, are not automatically escaped when interpolated into query strings — they are a secondary injection surface distinct from classic SQL injection.

Additionally, storing user-supplied JSON blobs verbatim and later extracting sub-fields with `json_extract` can allow an attacker who can write one field to overwrite a different field if JSON merge semantics are misused.

---

## 1. Classic JSON Path Injection via String Interpolation

**Vulnerable pattern:**
```typescript
// NEVER DO THIS
async function getUserPreference(userId: string, path: string, env: Env) {
  // path is user-controlled: "$.theme" could become "$.theme') OR 1=1 --"
  const result = await env.DB.prepare(
    `SELECT json_extract(preferences, '${path}') FROM users WHERE id = ?`
  ).bind(userId).first();
  return result;
}
```

**Safe pattern — validate path before use:**
```typescript
const SAFE_JSON_PATH = /^\$(\.[a-zA-Z_][a-zA-Z0-9_]*(\[\d+\])?)+$/;

async function getUserPreference(
  userId: string,
  path: string,
  env: Env,
): Promise<unknown> {
  if (!SAFE_JSON_PATH.test(path)) {
    throw new Error("Invalid JSON path expression");
  }
  // Path is validated; still use parameterized binding for the user value
  const row = await env.DB.prepare(
    "SELECT json_extract(preferences, ?) AS val FROM users WHERE id = ?",
  ).bind(path, userId).first<{ val: unknown }>();
  return row?.val ?? null;
}
```

SQLite3/D1 does accept the path as a bound parameter — always prefer binding over interpolation.

---

## 2. JSON Blob Storage — Sanitizing Before Insert

Never store raw user-supplied JSON. Parse, validate schema, and re-serialize to ensure canonical structure:

```typescript
import { z } from "zod";

const PreferencesSchema = z.object({
  theme: z.enum(["light", "dark", "system"]),
  language: z.string().regex(/^[a-z]{2}(-[A-Z]{2})?$/),
  notifications: z.object({
    email: z.boolean(),
    push: z.boolean(),
  }),
}).strict(); // reject unknown keys

type Preferences = z.infer<typeof PreferencesSchema>;

async function setUserPreferences(
  userId: string,
  raw: unknown,
  env: Env,
): Promise<void> {
  const preferences = PreferencesSchema.parse(raw); // throws ZodError on invalid input
  const json = JSON.stringify(preferences);         // canonical, no extra keys

  await env.DB.prepare(
    "UPDATE users SET preferences = json(?) WHERE id = ?",
  ).bind(json, userId).run();
  // json() validates the string is valid JSON before writing; D1 returns error otherwise
}
```

`json()` in the SQL call acts as a server-side validation step — D1 rejects malformed JSON at the database level.

---

## 3. Preventing JSON Merge Patch Privilege Escalation

`json_patch()` performs RFC 7396 merge patch. If you allow partial updates, a malicious patch can overwrite fields the caller should not control (e.g., a `role` field stored inside the same JSON blob).

```typescript
// DANGEROUS: caller can escalate role by including {"role":"admin"} in patch
async function patchPreferencesUnsafe(userId: string, patch: unknown, env: Env) {
  await env.DB.prepare(
    "UPDATE users SET preferences = json_patch(preferences, json(?)) WHERE id = ?",
  ).bind(JSON.stringify(patch), userId).run();
}

// SAFE: strip privileged fields from the patch before applying
const ALLOWED_PATCH_KEYS = new Set(["theme", "language", "notifications"]);

function sanitizePatch(patch: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(patch).filter(([k]) => ALLOWED_PATCH_KEYS.has(k)),
  );
}

async function patchPreferences(
  userId: string,
  rawPatch: unknown,
  env: Env,
): Promise<void> {
  if (typeof rawPatch !== "object" || rawPatch === null || Array.isArray(rawPatch)) {
    throw new TypeError("Patch must be a plain object");
  }
  const safePatch = sanitizePatch(rawPatch as Record<string, unknown>);
  await env.DB.prepare(
    "UPDATE users SET preferences = json_patch(preferences, json(?)) WHERE id = ?",
  ).bind(JSON.stringify(safePatch), userId).run();
}
```

---

## 4. Multi-Tenant JSON Row Isolation

When one column stores per-tenant JSON and rows are shared (e.g., a `settings` table with `tenant_id`), always include the tenant predicate in every `json_extract` query to prevent cross-tenant leakage:

```typescript
async function getTenantSetting(
  tenantId: string,
  settingKey: string,
  env: Env,
): Promise<string | null> {
  // Validate key to prevent path injection
  if (!/^[a-zA-Z_][a-zA-Z0-9_.]{0,63}$/.test(settingKey)) return null;

  const path = `$.${settingKey}`;
  const row = await env.DB.prepare(
    `SELECT json_extract(config, ?) AS val
     FROM tenant_settings
     WHERE tenant_id = ?`,
  ).bind(path, tenantId).first<{ val: string | null }>();

  return row?.val ?? null;
}
```

Never build a path from two user-controlled strings concatenated — always construct the `$.` prefix in application code.

---

## 5. json_each / json_tree Enumeration Guard

`json_each()` and `json_tree()` expand JSON into virtual table rows. Passing user-controlled JSON to these functions in a subquery can allow an attacker to probe the JSON structure of other rows.

```typescript
// Safely iterate a user-supplied list with strict type + size limit
async function processTagList(
  userId: string,
  tagsJson: unknown,
  env: Env,
): Promise<void> {
  // Validate before passing to DB
  const tags = z.array(z.string().max(64)).max(20).parse(tagsJson);
  const canonical = JSON.stringify(tags);

  // Use json_each only on the validated, serialized value — never on raw input
  await env.DB.prepare(
    `INSERT OR IGNORE INTO user_tags (user_id, tag)
     SELECT ?, value FROM json_each(json(?))
     WHERE typeof(value) = 'text'`,
  ).bind(userId, canonical).run();
}
```

The `WHERE typeof(value) = 'text'` guard prevents non-string array elements (injected objects or numbers) from reaching the INSERT.

---

## Anti-patterns

- **String-interpolating JSON path expressions** — always bind path as a parameter; SQLite path injection is less well-known than SQL injection but equally dangerous.
- **Storing raw user JSON without parsing** — malformed or oversized JSON can crash extractors or bloat the column silently.
- **Using `json_patch` on blobs containing privilege fields** — merge patch replaces entire subtrees; separate privileged fields into their own columns rather than co-locating them in a user-patchable blob.
- **`SELECT *` from `json_each(user_input)`** — never expand arbitrary user JSON into a virtual table without first validating the JSON schema and size.
- **Trusting `json_valid()` alone as a security gate** — `json_valid()` only checks syntactic correctness; it does not validate the schema or bound the size.

## Gotchas

- D1 enforces a 1 MB row size limit; a user who can write unbounded JSON can inflate a row to hit that limit and cause D1 to reject future updates — always cap JSON column size in application code before INSERT/UPDATE.
- `json_extract()` returns `NULL` for both a missing key and a key whose value is explicitly `null` — distinguish the two cases with `json_type(col, path)` if your logic cares.
- SQLite JSON path is case-sensitive for object keys: `$.Theme` and `$.theme` are different — normalize key casing server-side to avoid confusion.
- `json_patch()` with a `null` value for a key deletes that key (RFC 7396 §2) — a caller can silently remove fields by sending `{"fieldName": null}` in the patch.

## Verification

```bash
# Attempt path injection and confirm it is rejected
curl -X GET "https://api.example.com/prefs?path=$.theme')%20OR%201%3D1--" \
  -H "Authorization: Bearer <token>"
# Expected: 400 {"error":"Invalid JSON path expression"}

# Confirm json() guard rejects malformed JSON
wrangler d1 execute DB --command \
  "SELECT json('{\"broken\":}');"
# Expected: Runtime error: malformed JSON

# Confirm patch strips undeclared keys
curl -X PATCH https://api.example.com/prefs \
  -H "Content-Type: application/json" \
  -d '{"theme":"dark","role":"admin"}' \
  -H "Authorization: Bearer <token>"
# After patch, role must remain unchanged:
wrangler d1 execute DB --command \
  "SELECT json_extract(preferences, '$.role') FROM users WHERE id='<uid>';"
```

## Related

- `sql-injection-prevention-d1-workers.md`
- `d1-row-level-security-tenant-isolation.md`
- `api-schema-validation-openapi-zod-workers.md`
- `mass-assignment-prevention.md`

## Sources

- SQLite JSON1 extension — https://www.sqlite.org/json1.html
- RFC 7396 — JSON Merge Patch
- OWASP Testing Guide — Testing for SQL Injection (OTG-INPVAL-005)
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
