# Type-Safe wrangler.toml Configuration with TypeScript

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You reference `env.MY_KV` in your Worker code, but `wrangler.toml` uses `MY_KV_NAMESPACE` as the binding name. TypeScript accepts it because your `Env` interface is hand-maintained and has drifted from the actual config. At runtime the binding is `undefined`, and the Worker crashes in production. Meanwhile, your editor offers no autocomplete for binding names and no compile-time error when you add a new Queue binding but forget to declare it in the interface.

## Context

Applies when:
- Wrangler 3.x (`wrangler types` command available)
- TypeScript strict mode enabled
- Bindings include KV namespaces, D1 databases, R2 buckets, Queues, AI, Service bindings, or Durable Objects
- Using `ExportedHandler<Env>` pattern (not the legacy `addEventListener` pattern)

Wrangler 3 can introspect `wrangler.toml` and emit a `worker-configuration.d.ts` file containing a generated `Env` interface that exactly mirrors your bindings. Combining this with TypeScript module augmentation and strict compilation options eliminates the entire class of binding-name mismatch errors.

## Solution

### Step 1 — Generate the initial type file

```bash
wrangler types
```

This creates `worker-configuration.d.ts` in the project root with content like:

```typescript
// worker-configuration.d.ts  (GENERATED — do not edit manually)
interface Env {
  SESSIONS_KV: KVNamespace;
  ANALYTICS_DB: D1Database;
  UPLOADS_BUCKET: R2Bucket;
  JOBS_QUEUE: Queue;
  AI: Ai;
  AUTH_SERVICE: Fetcher;
}
```

### Step 2 — Add type generation to your build process

In `package.json`:

```json
{
  "scripts": {
    "types": "wrangler types",
    "build": "pnpm run types && tsc --noEmit && wrangler deploy --dry-run",
    "dev": "pnpm run types && wrangler dev"
  }
}
```

### Step 3 — Reference the generated `Env` in your Worker

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // env.SESSIONS_KV is now KVNamespace — fully typed
    const session = await env.SESSIONS_KV.get(request.headers.get('cf-session-id') ?? '');

    if (!session) {
      return new Response('Unauthorized', { status: 401 });
    }

    // env.ANALYTICS_DB is D1Database — typed queries
    const stmt = env.ANALYTICS_DB.prepare(
      'SELECT COUNT(*) as total FROM requests WHERE path = ?'
    ).bind(new URL(request.url).pathname);
    const { results } = await stmt.all<{ total: number }>();

    return Response.json({ session: JSON.parse(session), requests: results[0]?.total ?? 0 });
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

### Full `wrangler.toml` with all binding types

```toml
# wrangler.toml
name = "my-api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[kv_namespaces]]
binding = "SESSIONS_KV"
id = "abc123def456"
preview_id = "preview_abc123"

[[d1_databases]]
binding = "ANALYTICS_DB"
database_name = "analytics"
database_id = "d1-database-uuid"

[[r2_buckets]]
binding = "UPLOADS_BUCKET"
bucket_name = "my-uploads"
preview_bucket_name = "my-uploads-preview"

[[queues.producers]]
binding = "JOBS_QUEUE"
queue = "my-jobs-queue"

[[queues.consumers]]
queue = "my-jobs-queue"
max_batch_size = 10
max_batch_timeout = 30

[ai]
binding = "AI"

[[services]]
binding = "AUTH_SERVICE"
service = "auth-worker"

[vars]
ENVIRONMENT = "production"
MAX_RETRY_ATTEMPTS = "3"

[env.staging]
vars = { ENVIRONMENT = "staging", MAX_RETRY_ATTEMPTS = "5" }
```

### Augmenting the generated `Env` for variables

String vars appear in the generated `Env` as `string`, but you can narrow their types in a separate augmentation file — never edit `worker-configuration.d.ts` directly because `wrangler types` overwrites it:

```typescript
// src/env.d.ts  (hand-authored, safe to edit)
declare global {
  // Narrow string vars to literal union types
  interface Env {
    ENVIRONMENT: 'production' | 'staging' | 'development';
    MAX_RETRY_ATTEMPTS: `${number}`; // still a string at runtime
  }
}

export {}; // make this a module
```

### Using typed bindings in a queue consumer

```typescript
// src/queue-consumer.ts
interface JobPayload {
  userId: string;
  action: 'send-email' | 'resize-image' | 'generate-report';
  params: Record<string, unknown>;
}

export default {
  async fetch(_request: Request, _env: Env): Promise<Response> {
    return new Response('Queue worker — no HTTP interface');
  },

  async queue(batch: MessageBatch<JobPayload>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const { userId, action, params } = message.body;

      try {
        switch (action) {
          case 'send-email':
            await processEmail(userId, params, env);
            break;
          case 'resize-image':
            await processImage(userId, params, env.UPLOADS_BUCKET);
            break;
          case 'generate-report':
            await processReport(userId, params, env.ANALYTICS_DB);
            break;
        }
        message.ack();
      } catch (err) {
        message.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function processImage(
  userId: string,
  params: Record<string, unknown>,
  bucket: R2Bucket
): Promise<void> {
  const key = `users/${userId}/images/${params['filename'] as string}`;
  const existing = await bucket.get(key);
  if (!existing) throw new Error(`Image not found: ${key}`);
  // ... resize logic
}

async function processEmail(
  userId: string,
  params: Record<string, unknown>,
  env: Env
): Promise<void> {
  // env.AUTH_SERVICE is Fetcher — call the auth worker
  const userResp = await env.AUTH_SERVICE.fetch(`https://auth/users/${userId}`);
  const user = await userResp.json<{ email: string }>();
  // ... send email
}

async function processReport(
  userId: string,
  params: Record<string, unknown>,
  db: D1Database
): Promise<void> {
  const rows = await db
    .prepare('SELECT * FROM events WHERE user_id = ? AND created_at > ?')
    .bind(userId, params['since'])
    .all();
  // ... generate report from rows.results
}
```

### Typed AI binding with Workers AI models

```typescript
// src/ai-handler.ts
type TextGenerationInput = Parameters<Ai['run']>[1];

export async function generateSummary(text: string, env: Env): Promise<string> {
  const response = await env.AI.run('@cf/meta/llama-3-8b-instruct', {
    prompt: `Summarize the following text in 2 sentences:\n\n${text}`,
    max_tokens: 256,
  });

  // Workers AI run() returns different shapes depending on the model
  if ('response' in response && typeof response.response === 'string') {
    return response.response;
  }
  throw new Error('Unexpected AI response shape');
}
```

### Strict `tsconfig.json` for Workers

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ES2022",
    "moduleResolution": "bundler",
    "types": ["@cloudflare/workers-types/2023-07-01"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "noFallthroughCasesInSwitch": true,
    "noEmit": true
  },
  "include": [
    "src/**/*.ts",
    "worker-configuration.d.ts"
  ]
}
```

## Anti-patterns

**Do not** hand-write and maintain the `Env` interface in your source code. Every binding change in `wrangler.toml` must be manually mirrored. Use `wrangler types` to generate it.

**Do not** use `any` for the `env` parameter:

```typescript
// BAD
async fetch(request: Request, env: any) {
  env.MY_KV.get('key'); // no type safety, no autocomplete
}

// GOOD
async fetch(request: Request, env: Env) {
  env.SESSIONS_KV.get('key'); // typed, autocompleted, refactorable
}
```

**Do not** import `Env` from another file. The generated `worker-configuration.d.ts` uses a global `interface Env` declaration (no `export`). It is available globally across all files in the compilation unit without importing.

**Do not** commit `worker-configuration.d.ts` to version control if you generate it as part of every build. Either commit it (simpler for IDEs without local Wrangler) or gitignore it and enforce generation in `prebuild`. Pick one strategy per team.

## Gotchas

**`wrangler types` must be run after every `wrangler.toml` change**. It is not a watch process. If you add a binding and forget to regenerate types, TypeScript will report that `env.NEW_BINDING` does not exist on type `Env` — which is the correct, desirable behaviour, but can surprise developers who edit `wrangler.toml` directly.

**Preview IDs matter for `wrangler dev`**. If `preview_id` is missing from a KV namespace, Wrangler falls back to a local emulated namespace. The generated type is `KVNamespace` either way, but behaviour differs. Specify `preview_id` for production-parity local development.

**Queue bindings appear twice in `wrangler.toml`** (under `queues.producers` for sending and `queues.consumers` for receiving). The `Env` interface only includes the producer binding as `Queue<Body>`. The consumer method signature comes from `ExportedHandler<Env>` — the `queue` method receives `MessageBatch<Body>`, not an `Env` property.

**`satisfies ExportedHandler<Env>`** is preferred over `: ExportedHandler<Env>` because `satisfies` checks conformance while preserving the literal type of the export for tree-shaking. If you accidentally add a typo method like `feetch`, `satisfies` will error; `: ExportedHandler<Env>` silently ignores it.

## Verification

```bash
# Generate types and immediately type-check
wrangler types && tsc --noEmit

# Introduce a deliberate binding name mismatch to confirm the check works
# In src/index.ts, change env.SESSIONS_KV to env.SESSION_KV (typo)
# Then run:
tsc --noEmit
# Expected: error TS2339: Property 'SESSION_KV' does not exist on type 'Env'.

# Confirm the generated file matches wrangler.toml
cat worker-configuration.d.ts
# Cross-reference binding names with [kv_namespaces], [d1_databases] etc. in wrangler.toml
```

## Related

- `workers-lefthook-git-hooks-monorepo.md` — running `wrangler types` as a pre-commit hook
- `workers-openapi-codegen-hono-zod.md` — typed route handlers that consume this `Env` interface
- `workers-turbo-remote-cache-r2.md` — R2 binding usage patterns from this guide

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://developers.cloudflare.com/workers/languages/typescript/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
- https://github.com/cloudflare/workers-types
