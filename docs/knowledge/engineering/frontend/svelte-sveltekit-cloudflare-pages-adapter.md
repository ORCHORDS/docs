# SvelteKit on Cloudflare Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to deploy a SvelteKit application to Cloudflare Pages with full server-side rendering, accessing D1 and KV from load functions and form actions, streaming deferred data with `defer`, and enforcing security headers via a `_headers` file without a separate middleware layer.

---

## Context
`@sveltejs/adapter-cloudflare` packages each SvelteKit route into a Cloudflare Pages Function and surfaces Cloudflare bindings through the `platform.env` object injected into `event.platform` in `+page.server.ts` and `+server.ts` files. Workers KV can back session storage for form actions: write a signed session token to KV on login and read it back on protected routes. SvelteKit's `defer` (from `@sveltejs/kit`) lets slow data sources stream after the initial HTML shell has been sent. Static security headers are declared in a `_headers` file at the project root; the adapter copies it verbatim to the Pages output directory.

---

## Section 1 — Adapter Config

`svelte.config.js`
```javascript
import adapter from '@sveltejs/adapter-cloudflare';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      // Routes to compile as edge functions (default: all server routes)
      routes: {
        include: ['/*'],
        exclude: ['<all>'],
      },
      platformProxy: {
        // Used during `vite dev` to inject a simulated platform.env
        configPath: 'wrangler.toml',
        environment: undefined,
        experimentalJsonConfig: false,
        persist: true,
      },
    }),
  },
};
```

`wrangler.toml`
```toml
name = "my-sveltekit-app"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = ".svelte-kit/cloudflare"

[[d1_databases]]
binding = "DB"
database_name = "sveltekit-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "SESSIONS"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

`app.d.ts` — type augmentation for `platform`
```typescript
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';

declare global {
  namespace App {
    interface Platform {
      env: {
        DB: D1Database;
        SESSIONS: KVNamespace;
      };
      context: {
        waitUntil(promise: Promise<unknown>): void;
      };
      caches: CacheStorage;
    }
  }
}

export {};
```

`static/_headers`
```
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), microphone=(), camera=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'
```

---

## Section 2 — Load Function with D1 and Deferred Streaming

`src/routes/blog/+page.server.ts`
```typescript
import { defer } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

interface Post {
  id: number;
  title: string;
  slug: string;
  published_at: string;
}

export const load: PageServerLoad = async ({ platform, url }) => {
  if (!platform?.env?.DB) {
    throw new Error('D1 binding (DB) not available — check wrangler.toml');
  }

  const page = parseInt(url.searchParams.get('page') ?? '1', 10);
  const limit = 20;
  const offset = (page - 1) * limit;

  // Fast data: resolved before HTML shell ships
  const { results: recentPosts } = await platform.env.DB.prepare(
    `SELECT id, title, slug, published_at
     FROM posts
     ORDER BY published_at DESC
     LIMIT ? OFFSET ?`
  )
    .bind(limit, offset)
    .all<Post>();

  // Slow data: streamed after shell — simulating a slow aggregation query
  const popularPostsPromise = platform.env.DB.prepare(
    `SELECT id, title, slug, view_count
     FROM posts
     ORDER BY view_count DESC
     LIMIT 5`
  ).all<Post & { view_count: number }>();

  return defer({
    recentPosts,
    page,
    // defer wraps the Promise; SvelteKit streams the resolution
    popularPosts: popularPostsPromise.then((r) => r.results),
  });
};
```

`src/routes/blog/+page.svelte`
```svelte
<script lang="ts">
  import { page } from '$app/stores';
  import type { PageData } from './$types';

  export let data: PageData;
</script>

<h1>Blog</h1>

<section>
  <h2>Recent posts</h2>
  <ul>
    {#each data.recentPosts as post (post.id)}
      <li><a >{post.title}</a></li>
    {/each}
  </ul>
</section>

<section>
  <h2>Popular posts</h2>
  {#await data.popularPosts}
    <p>Loading popular posts…</p>
  {:then posts}
    <ul>
      {#each posts as post (post.id)}
        <li>{post.title} ({post.view_count} views)</li>
      {/each}
    </ul>
  {:catch}
    <p>Could not load popular posts.</p>
  {/await}
</section>

<nav>
  {#if data.page > 1}
    <a href="?page={data.page - 1}">← Prev</a>
  {/if}
  <a href="?page={data.page + 1}">Next →</a>
</nav>
```

---

## Section 3 — Form Action with Workers KV Session

`src/routes/login/+page.server.ts`
```typescript
import { fail, redirect } from '@sveltejs/kit';
import type { Actions } from './$types';

const SESSION_TTL_SECONDS = 60 * 60 * 24; // 24 h

export const actions: Actions = {
  default: async ({ platform, request, cookies }) => {
    if (!platform?.env?.SESSIONS) {
      throw new Error('KV binding (SESSIONS) not available');
    }

    const formData = await request.formData();
    const username = formData.get('username')?.toString().trim();
    const password = <redacted-secret>'password')?.toString();

    if (!username || !password) {
      return fail(400, { error: 'Username and password are required.' });
    }

    // Replace with your real credential check (hashed password from D1 etc.)
    const isValid = username === 'demo' && password === 'secret';
    if (!isValid) {
      return fail(401, { error: 'Invalid credentials.' });
    }

    // Generate a cryptographically random session ID
    const sessionId = crypto.randomUUID();
    const sessionData = JSON.stringify({ username, createdAt: Date.now() });

    await platform.env.SESSIONS.put(sessionId, sessionData, {
      expirationTtl: SESSION_TTL_SECONDS,
    });

    // HttpOnly, Secure, SameSite=Lax session cookie
    cookies.set('session_id', sessionId, {
      path: '/',
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      maxAge: SESSION_TTL_SECONDS,
    });

    throw redirect(303, '/dashboard');
  },
};
```

`src/routes/dashboard/+page.server.ts`
```typescript
import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ platform, cookies }) => {
  const sessionId = cookies.get('session_id');
  if (!sessionId) throw redirect(303, '/login');

  const raw = await platform!.env.SESSIONS.get(sessionId);
  if (!raw) throw redirect(303, '/login');

  const session = JSON.parse(raw) as { username: string; createdAt: number };
  return { username: session.username };
};
```

---

## Anti-patterns
- **Accessing `platform.env` in universal load functions** — `platform` is only available in *server* load functions (`+page.server.ts`, `+server.ts`); it is `undefined` in `+page.ts`.
- **Storing sensitive data in cookies directly** — Use KV to hold the session payload; the cookie carries only the opaque session ID.
- **Hardcoding `_headers` paths to `/static`** — Place `_headers` inside your `static/` directory so SvelteKit copies it; do not place it in `src/`.
- **Skipping `platformProxy` in `svelte.config.js`** — Without `platformProxy`, `vite dev` cannot simulate D1/KV bindings and `platform.env` will be `undefined` during development.

---

## Gotchas
- `defer` requires SvelteKit ≥ 1.8.0; confirm your version before use.
- Workers KV `put` with `expirationTtl` uses **seconds**, not milliseconds — a common source of TTL errors.
- The `_headers` file applies to all Pages responses including static assets; overly broad CSP can break CDN-delivered fonts or analytics scripts.
- `crypto.randomUUID()` is available globally in the Workers runtime without any import; do not import Node's `crypto` module.

---

## Verification
```bash
# Install adapter
npm install --save-dev @sveltejs/adapter-cloudflare @cloudflare/workers-types

# Build
vite build

# Preview with bindings
wrangler pages dev --d1 DB=<database_id> --kv SESSIONS=<kv_namespace_id>

# Confirm security headers are present
curl -I http://localhost:8788/ | grep -i 'x-frame\|csp\|referrer'

# Deploy
wrangler pages deploy .svelte-kit/cloudflare --project-name my-sveltekit-app
```

---

## Related
- `react-server-components-cloudflare-pages.md`
- `cloudflare-pages-middleware-auth-redirect.md`
- `vue-nuxt-cloudflare-pages-nitro.md`

---

## Sources
- SvelteKit Cloudflare adapter — https://kit.svelte.dev/docs/adapter-cloudflare
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- SvelteKit `defer` streaming — https://kit.svelte.dev/docs/load#streaming-with-promises
