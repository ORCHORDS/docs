# Contract Testing Workers OpenAPI Schema Drift

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker exposes a JSON REST API. The OpenAPI spec (`openapi.yaml`) was accurate when first written but has since drifted from the Worker's actual responses: optional fields became required, enum values changed, new properties appeared undocumented. Consumers (mobile apps, third-party integrations) break silently because the spec claimed compatibility. You need a CI gate that detects schema drift between the live Worker responses and the declared OpenAPI document before a deployment ships.

## Context

Schema drift happens in two directions:
- **Spec-ahead drift**: The spec documents a change that the Worker hasn't implemented yet (consumers integrate against air).
- **Implementation-ahead drift**: The Worker silently changes its response shape; the spec still describes the old shape; downstream consumers fail at runtime.

The strategy here catches implementation-ahead drift by treating the OpenAPI spec as the source of truth for consumers and running `@readme/openapi-parser` + `ajv` validation against recorded Worker responses. A secondary pass using `openapi-diff` or `oasdiff` catches breaking changes between spec versions in CI.

## 1. Dependencies

```bash
npm install --save-dev \
  @readme/openapi-parser \
  ajv \
  ajv-formats \
  openapi-typescript \
  oasdiff \          # CLI for spec-to-spec diff
  vitest \
  miniflare
```

## 2. Load and Dereference the Spec

```typescript
// test/helpers/schema-loader.ts
import SwaggerParser from "@readme/openapi-parser";
import type { OpenAPIV3 } from "openapi-types";

let cached: OpenAPIV3.Document | null = null;

export async function loadSpec(): Promise<OpenAPIV3.Document> {
  if (cached) return cached;
  // Dereferences $ref chains so schemas are self-contained for AJV
  cached = (await SwaggerParser.dereference(
    new URL("../../openapi.yaml", import.meta.url).pathname
  )) as OpenAPIV3.Document;
  return cached;
}

export function getResponseSchema(
  doc: OpenAPIV3.Document,
  path: string,
  method: "get" | "post" | "put" | "patch" | "delete",
  statusCode: string
): OpenAPIV3.SchemaObject | null {
  const operation = doc.paths?.[path]?.[method];
  if (!operation) return null;
  const mediaType = operation.responses?.[statusCode];
  if (!mediaType || !("content" in mediaType)) return null;
  return (mediaType as OpenAPIV3.ResponseObject).content?.["application/json"]
    ?.schema as OpenAPIV3.SchemaObject ?? null;
}
```

## 3. AJV Validator Factory

```typescript
// test/helpers/validator.ts
import Ajv from "ajv";
import addFormats from "ajv-formats";
import type { OpenAPIV3 } from "openapi-types";

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);

export function compileSchema(schema: OpenAPIV3.SchemaObject) {
  return ajv.compile(schema);
}
```

## 4. Miniflare Worker Fixture

```typescript
// test/helpers/worker.ts
import { Miniflare } from "miniflare";

let _mf: Miniflare | null = null;

export async function getWorker(): Promise<Miniflare> {
  if (_mf) return _mf;
  _mf = new Miniflare({
    scriptPath: "./dist/worker.js",
    modules: true,
    d1Databases: ["DB"],
    kvNamespaces: ["CACHE"],
  });
  await _mf.ready;
  return _mf;
}

export async function disposeWorker(): Promise<void> {
  if (_mf) {
    await _mf.dispose();
    _mf = null;
  }
}
```

## 5. Schema Drift Tests for Core Endpoints

```typescript
// test/schema-drift.test.ts
import { describe, it, beforeAll, afterAll, expect } from "vitest";
import { loadSpec, getResponseSchema } from "./helpers/schema-loader";
import { compileSchema } from "./helpers/validator";
import { getWorker, disposeWorker } from "./helpers/worker";
import type { OpenAPIV3 } from "openapi-types";
import type Miniflare from "miniflare";

let doc: OpenAPIV3.Document;
let mf: Miniflare;

beforeAll(async () => {
  [doc, mf] = await Promise.all([loadSpec(), getWorker()]);
});
afterAll(() => disposeWorker());

function assertConformsToSpec(
  data: unknown,
  schema: OpenAPIV3.SchemaObject | null,
  context: string
) {
  if (!schema) throw new Error(`No schema found for ${context}`);
  const validate = compileSchema(schema);
  const valid = validate(data);
  if (!valid) {
    throw new Error(
      `Schema drift detected at ${context}:\n` +
        (validate.errors ?? [])
          .map((e) => `  ${e.instancePath} ${e.message}`)
          .join("\n")
    );
  }
}

describe("GET /api/users/{id} → 200", () => {
  it("response body conforms to openapi.yaml#/paths/~1api~1users~1{id}/get/responses/200", async () => {
    // Seed a user in the D1 fixture
    const db = await mf.getD1Database("DB");
    await db.exec(`INSERT OR IGNORE INTO users (id, email, role) VALUES ('u1', 'alice@example.com', 'member')`);

    const res = await mf.dispatchFetch("http://worker/api/users/u1");
    expect(res.status).toBe(200);
    const body = await res.json();

    const schema = getResponseSchema(doc, "/api/users/{id}", "get", "200");
    assertConformsToSpec(body, schema, "GET /api/users/{id} 200");
  });

  it("404 response body conforms to error schema", async () => {
    const res = await mf.dispatchFetch("http://worker/api/users/nonexistent");
    expect(res.status).toBe(404);
    const body = await res.json();

    const schema = getResponseSchema(doc, "/api/users/{id}", "get", "404");
    assertConformsToSpec(body, schema, "GET /api/users/{id} 404");
  });
});

describe("POST /api/posts → 201", () => {
  it("created post conforms to response schema", async () => {
    const res = await mf.dispatchFetch("http://worker/api/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Hello", body: "World", authorId: "u1" }),
    });
    expect(res.status).toBe(201);
    const body = await res.json();

    const schema = getResponseSchema(doc, "/api/posts", "post", "201");
    assertConformsToSpec(body, schema, "POST /api/posts 201");
  });
});
```

## 6. Breaking-Change Gate with oasdiff

Run this in CI on every PR that touches the spec or Worker routes. It exits non-zero when breaking changes are detected.

```typescript
// scripts/check-spec-drift.ts
import { execSync } from "child_process";
import { existsSync } from "fs";

const BASE_SPEC = process.env.BASE_SPEC ?? "openapi.baseline.yaml";
const HEAD_SPEC = "openapi.yaml";

if (!existsSync(BASE_SPEC)) {
  console.log("No baseline spec found — skipping breaking-change check.");
  process.exit(0);
}

try {
  const output = execSync(
    `npx oasdiff breaking ${BASE_SPEC} ${HEAD_SPEC} --format text`,
    { encoding: "utf8" }
  );
  if (output.trim()) {
    console.error("Breaking API changes detected:\n", output);
    process.exit(1);
  }
  console.log("No breaking changes between specs.");
} catch (err: unknown) {
  if (err instanceof Error && "stdout" in err) {
    console.error((err as { stdout: string }).stdout);
  }
  process.exit(1);
}
```

```yaml
# .github/workflows/schema-drift.yml
name: Schema Drift
on: [pull_request]
jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: npm ci
      - name: Build worker
        run: npx wrangler build --dry-run --outdir dist
      - name: Validate response bodies against spec
        run: npx vitest run test/schema-drift.test.ts
      - name: Check for breaking spec changes
        run: |
          git show origin/main:openapi.yaml > openapi.baseline.yaml || true
          BASE_SPEC=openapi.baseline.yaml npx tsx scripts/check-spec-drift.ts
```

## Anti-patterns

- **Asserting only HTTP status codes**: Status codes don't catch field renames, type changes, or removed required fields.
- **Validating against the raw (non-dereferenced) spec**: `$ref` chains in AJV's `definitions` must be resolved; otherwise AJV can't find the referenced schemas.
- **Running schema drift tests only in staging**: By the time staging is deployed, the PR has already merged. Run in CI on every PR against a Miniflare instance so no production deployment ships a drift.
- **Treating `additionalProperties: true` as safe**: An undocumented field in the response today becomes a consumer dependency tomorrow. Set `additionalProperties: false` in the spec and treat new fields as a spec update.
- **Skipping 4xx schema validation**: Error shapes are part of the contract. Consumers parse error `code` and `message` fields; an undocumented change in error shape is a breaking change.

## Gotchas

- `openapi-typescript` generates static types from the spec, but it doesn't validate runtime responses. You need AJV or an equivalent JSON Schema validator for that.
- AJV v8 treats `nullable: true` (OpenAPI 3.0 extension) differently from `type: ["string", "null"]` (JSON Schema draft-07). Use `ajv-openapi` or set `nullable` handling explicitly.
- oasdiff only compares two YAML/JSON files; it cannot compare a live Worker response against the spec. It's purely a spec-to-spec diff tool.
- When your Worker returns dates as ISO 8601 strings, add `ajv-formats` and declare `format: date-time` in the spec — otherwise AJV won't validate the string format.
- `SwaggerParser.dereference` mutates the input if called without options. Store the result separately from the raw parsed doc if you need both.

## Verification

```bash
# Run schema drift unit tests
npx vitest run test/schema-drift.test.ts --reporter=verbose

# Simulate a breaking change: rename a field in openapi.yaml and check
npx tsx scripts/check-spec-drift.ts
# → Should print "Breaking API changes detected" and exit 1
```

## Related

- `contract-testing-workers-d1-schema-validation.md` — database schema vs. Worker response validation
- `api-contract-testing-schema-validation.md` — generic JSON Schema validation patterns
- `zod-api-contract-testing-vitest.md` — Zod-driven runtime validation as alternative to AJV
- `hono-workers-api-snapshot-testing.md` — snapshot-locking of full response bodies

## Sources

- OpenAPI 3.0 spec: https://spec.openapis.org/oas/v3.0.3
- oasdiff breaking change detection: https://github.com/Tufin/oasdiff
- AJV JSON Schema validator: https://ajv.js.org/
- @readme/openapi-parser: https://github.com/readmeio/openapi-parser
