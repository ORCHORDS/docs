# Remix on Cloudflare Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Running Full-Stack Remix at the Edge

Remix's `@remix-run/cloudflare` adapter lets you deploy the entire request/response lifecycle—loaders, actions, and asset serving—inside a Cloudflare Worker. Unlike a Node.js deployment, every request is handled inside a V8 isolate: no cold starts beyond first-boot, sub-millisecond warm latency, and direct access to Workers bindings (D1, R2, KV, Durable Objects) without a network hop.

The adapter exposes a `createRequestHandler` function that accepts a Remix `build` object and returns a standard `ExportedHandler`. Wrangler v3 generates the Worker entry point automatically when you scaffold with `create-cloudflare`, but understanding the wiring is essential when customising middleware, streaming behaviour, or binding injection.

Resource routes and server-side data loading run in the same isolate as asset serving. This eliminates the round-trip you'd have in a split architecture (CDN + API origin) and lets loaders read from D1 with single-digit millisecond latency anywhere in Cloudflare's network.

## Context

Cloudflare Workers runtime is not Node.js. APIs like `fs`, `path`, `crypto.createHash` (legacy form), and Node streams are unavailable unless polyfilled via `nodejs_compat`. Remix's cloudflare adapter wraps the Web `Request`/`Response` pair natively, so loaders and actions receive a standard `LoaderFunctionArgs` with `context.cloudflare` carrying the `env` bindings object and the `waitUntil` / `passThroughOnException` helpers.

## Adapter Bootstrap

```toml
# wrangler.toml
name = "my-remix-app"
main = "build/worker/index.js"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "prod"
database_id = "xxxx-yyyy-zzzz"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "uploads"

[[kv_namespaces]]
binding = "SESSIONS"
id = "aaaa-bbbb-cccc"
```

```typescript
// workers/app.ts
import { createRequestHandler } from "@remix-run/cloudflare";
import * as build from "../build/server";

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    const handler = createRequestHandler(build, "production");
    return handler(request, { cloudflare: { env, ctx } });
  },
} satisfies ExportedHandler<Env>;
```

## D1 Data Loading in Loaders

```typescript
// app/routes/products.$id.tsx
import type { LoaderFunctionArgs } from "@remix-run/cloudflare";
import { json } from "@remix-run/cloudflare";
import { useLoaderData } from "@remix-run/react";

interface Env {
  DB: D1Database;
}

export async function loader({ params, context }: LoaderFunctionArgs) {
  const env = context.cloudflare.env as Env;
  const result = await env.DB.prepare(
    "SELECT id, name, price FROM products WHERE id = ?"
  )
    .bind(params.id)
    .first<{ id: string; name: string; price: number }>();

  if (!result) throw new Response("Not Found", { status: 404 });
  return json(result);
}

export default function ProductPage() {
  const product = useLoaderData<typeof loader>();
  return (
    <article>
      <h1>{product.name}</h1>
      <p>${product.price}</p>
    </article>
  );
}
```

## R2 File Uploads via Actions

```typescript
// app/routes/upload.tsx
import type { ActionFunctionArgs } from "@remix-run/cloudflare";
import { unstable_parseMultipartFormData } from "@remix-run/cloudflare";

interface Env {
  BUCKET: R2Bucket;
}

export async function action({ request, context }: ActionFunctionArgs) {
  const env = context.cloudflare.env as Env;

  const formData = await unstable_parseMultipartFormData(
    request,
    async ({ name, data, filename, contentType }) => {
      if (name !== "file" || !filename) return undefined;
      const key = `uploads/${crypto.randomUUID()}/${filename}`;
      const chunks: Uint8Array[] = [];
      for await (const chunk of data) chunks.push(chunk);
      const body = new Uint8Array(
        chunks.reduce((acc, c) => acc + c.byteLength, 0)
      );
      let offset = 0;
      for (const chunk of chunks) {
        body.set(chunk, offset);
        offset += chunk.byteLength;
      }
      await env.BUCKET.put(key, body, {
        httpMetadata: { contentType },
      });
      return key;
    }
  );

  const key = formData.get("file") as string;
  return new Response(JSON.stringify({ key }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

## KV Session Storage

```typescript
// app/sessions.server.ts
import { createWorkersKVSessionStorage } from "@remix-run/cloudflare";
import type { Env } from "~/types/env";

export function getSessionStorage(env: Env) {
  return createWorkersKVSessionStorage({
    kv: env.SESSIONS,
    cookie: {
      name: "__session",
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      secrets: [env.SESSION_SECRET],
      maxAge: 60 * 60 * 24 * 30,
    },
  });
}

// Usage in loader
export async function loader({ request, context }: LoaderFunctionArgs) {
  const env = context.cloudflare.env as Env;
  const { getSession } = getSessionStorage(env);
  const session = await getSession(request.headers.get("Cookie"));
  const userId = session.get("userId");
  if (!userId) throw redirect("/login");
  return json({ userId });
}
```

## Streaming Responses via ReadableStream

```typescript
// app/routes/stream.tsx
export async function loader({ context }: LoaderFunctionArgs) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const items = ["first", "second", "third"];
      for (const item of items) {
        await new Promise((r) => setTimeout(r, 200));
        controller.enqueue(encoder.encode(`data: ${item}\n\n`));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
```

## Anti-patterns

- Importing Node.js built-ins (`path`, `fs`, `os`) without `nodejs_compat` flag — fails silently at build time but throws at runtime.
- Storing large binary blobs in KV — KV values cap at 25 MB; use R2 for anything file-like.
- Using `process.env` in loaders — bindings live on `context.cloudflare.env`, not `process.env`; the latter is undefined in production.
- Calling `unstable_parseMultipartFormData` without consuming the entire async iterator — the stream stays open and the Worker hangs.

## Gotchas

- `createWorkersKVSessionStorage` requires the KV namespace to be created in Wrangler config **before** first deploy; missing bindings cause a 500 with an opaque "binding not found" message.
- Remix's `defer()` with `<Await>` works on Cloudflare Workers only when the Worker runtime supports streaming — ensure `compatibility_date >= 2023-03-14`.
- The `ctx.waitUntil` pattern for fire-and-forget analytics must be called inside the `fetch` handler, not inside a loader; loaders do not have access to `ExecutionContext` unless you pass it through `context`.
- D1 `.first()` returns `null` (not `undefined`) when no row is found — always null-check before destructuring.

## Verification

```bash
# local dev with real bindings via wrangler
npx wrangler dev --remote

# run D1 migrations
npx wrangler d1 migrations apply prod --remote

# tail live logs
npx wrangler tail
```

## Related

- `feature-flags-cloudflare-workers-kv-edge-config.md`
- `react-query-optimistic-mutations-cloudflare-workers.md`
- `streaming-html-workers-react-rendertopipeablestream.md`
- `websocket-durable-objects-realtime-ui.md`

## Sources

- https://remix.run/docs/en/main/guides/cloudflare
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/kv/
