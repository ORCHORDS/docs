# Svelte 5 Runes on Cloudflare Pages

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You are migrating a SvelteKit application from Svelte 4 reactive statements (`$:`, `let`, stores) to Svelte 5 runes (`$state`, `$derived`, `$effect`, `$props`) and deploying to Cloudflare Pages. The new rune-based reactivity compiles differently, has distinct SSR semantics in Workers, and requires changes to how you share state between components and across the server/client boundary.

## Context

Svelte 5 replaced its compiler-based reactive assignments with explicit rune declarations. Runes are compiler directives that look like function calls (`$state()`, `$derived()`) but are processed at compile time — they do not exist at runtime. This produces smaller, faster output and aligns Svelte's reactivity model with fine-grained reactive signals. On Cloudflare Pages with `@sveltejs/adapter-cloudflare`, SvelteKit's SSR runs as a Pages Function; the rune primitives work the same on the server but the SSR output is plain HTML — no rune state survives to the client without hydration.

---

## $state – Reactive Local State

`$state` replaces top-level `let` for reactive variables. Deep objects are made reactive via Proxy.

```svelte
<!-- src/routes/counter/+page.svelte -->
<script lang="ts">
  let count = $state(0);
  let user = $state({ name: 'Alice', score: 0 });

  function increment() {
    count++;
    user.score++;  // deep proxy – triggers reactivity
  }
</script>

<button onclick={increment}>
  {count} clicks | Score: {user.score}
</button>
```

To opt out of deep reactivity (for performance with large objects):

```svelte
<script lang="ts">
  import { $state } from 'svelte'; // not needed – rune is implicit

  // Use $state.raw() for non-proxied state (replace-only updates)
  let bigList = $state.raw<string[]>([]);

  function reset() {
    bigList = [];  // must replace, cannot mutate
  }
</script>
```

---

## $derived – Computed Values

`$derived` replaces `$: derivedValue = ...` reactive statements.

```svelte
<script lang="ts">
  let items = $state<{ id: number; done: boolean }[]>([]);

  const pending = $derived(items.filter((i) => !i.done));
  const completed = $derived(items.filter((i) => i.done));
  const completionRate = $derived(
    items.length === 0 ? 0 : Math.round((completed.length / items.length) * 100),
  );
</script>

<p>{pending.length} pending · {completionRate}% complete</p>
```

For expensive computations use `$derived.by`:

```svelte
<script lang="ts">
  let data = $state<number[]>([]);

  const stats = $derived.by(() => {
    // Only re-runs when `data` changes
    const sorted = [...data].sort((a, b) => a - b);
    return {
      min: sorted[0] ?? 0,
      max: sorted.at(-1) ?? 0,
      median: sorted[Math.floor(sorted.length / 2)] ?? 0,
    };
  });
</script>
```

---

## $props – Typed Component Props

`$props()` replaces the `export let` syntax for component inputs.

```svelte
<!-- src/lib/components/UserCard.svelte -->
<script lang="ts">
  interface Props {
    name: string;
    avatarUrl?: string;
    onSelect?: (name: string) => void;
  }

  const { name, avatarUrl = '/default-avatar.png', onSelect }: Props = $props();
</script>

<div role="button" tabindex="0" onclick={() => onSelect?.(name)}>
  <img src={avatarUrl} alt="" width="48" height="48" />
  <span>{name}</span>
</div>
```

For bindable props (two-way binding):

```svelte
<script lang="ts">
  interface Props {
    value: string;
  }

  let { value = $bindable() }: Props = $props();
</script>

<input bind:value />
```

---

## $effect – Side Effects and Cleanup

`$effect` replaces `onMount` + `$:` reactive side effects. It runs after mount and re-runs when its reactive dependencies change.

```svelte
<script lang="ts">
  let query = $state('');
  let results = $state<string[]>([]);
  let controller: AbortController | null = null;

  $effect(() => {
    if (!query.trim()) {
      results = [];
      return;
    }

    // Cleanup the previous request when query changes
    controller?.abort();
    controller = new AbortController();

    fetch(`/api/search?q=${encodeURIComponent(query)}`, {
      signal: controller.signal,
    })
      .then((r) => r.json() as Promise<{ results: string[] }>)
      .then(({ results: r }) => {
        results = r;
      })
      .catch((err) => {
        if ((err as Error).name !== 'AbortError') console.error(err);
      });

    // Return cleanup function – runs before next $effect and on unmount
    return () => {
      controller?.abort();
    };
  });
</script>

<input bind:value={query} placeholder="Search…" />
<ul>{#each results as r}<li>{r}</li>{/each}</ul>
```

---

## Shared State with $state in a Module

For cross-component state, export `$state` from a `.svelte.ts` module (Svelte 5 `.svelte.ts` files support runes).

```typescript
// src/lib/cart.svelte.ts
interface CartItem {
  id: string;
  name: string;
  price: number;
  qty: number;
}

function createCart() {
  let items = $state<CartItem[]>([]);

  const total = $derived(
    items.reduce((sum, item) => sum + item.price * item.qty, 0),
  );

  const count = $derived(items.reduce((sum, item) => sum + item.qty, 0));

  function add(item: Omit<CartItem, 'qty'>) {
    const existing = items.find((i) => i.id === item.id);
    if (existing) {
      existing.qty++;
    } else {
      items.push({ ...item, qty: 1 });
    }
  }

  function remove(id: string) {
    items = items.filter((i) => i.id !== id);
  }

  function clear() {
    items = [];
  }

  return {
    get items() { return items; },
    get total() { return total; },
    get count() { return count; },
    add,
    remove,
    clear,
  };
}

export const cart = createCart();
```

```svelte
<!-- Any component -->
<script lang="ts">
  import { cart } from '$lib/cart.svelte.ts';
</script>

<p>{cart.count} items – ${cart.total.toFixed(2)}</p>
```

---

## SvelteKit Load Functions with Cloudflare Pages Bindings

```typescript
// src/routes/blog/+page.server.ts
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ platform }) => {
  // Access Cloudflare bindings via platform.env
  const kv = platform?.env?.BLOG_KV;
  if (!kv) throw new Error('KV binding unavailable');

  const keys = await kv.list({ prefix: 'post:' });

  const posts = await Promise.all(
    keys.keys.map((key) => kv.get<Post>(key.name, 'json')),
  );

  return {
    posts: posts.filter(Boolean) as Post[],
  };
};

interface Post {
  slug: string;
  title: string;
  date: string;
}
```

```svelte
<!-- src/routes/blog/+page.svelte -->
<script lang="ts">
  import type { PageData } from './$types';

  const { data }: { data: PageData } = $props();

  // data.posts is typed from the load function
  const sorted = $derived(
    [...data.posts].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
    ),
  );
</script>

<ul>
  {#each sorted as post (post.slug)}
    <li><a >{post.title}</a></li>
  {/each}
</ul>
```

---

## Anti-patterns

- **Using `$state` at module level in `.svelte` files** – module-level `$state` in a `.svelte` file is shared across all instances of the component (singleton behaviour); use `.svelte.ts` factory functions for shared state.
- **Reading `$derived` inside `$effect`** – `$derived` values read inside `$effect` create a dependency; if you only want to act on a specific change, read only the source `$state` inside the effect.
- **Mixing Svelte 4 stores with Svelte 5 runes** – `$store` auto-subscription syntax still works in Svelte 5 for backward compatibility but adds overhead; migrate to `.svelte.ts` modules.
- **Mutating props directly** – in Svelte 5, `$props()` values are read-only unless declared with `$bindable()`; mutations throw in development mode.
- **Calling `$effect` outside component initialization** – runes must be called at the top level of a `<script>` block or a `.svelte.ts` function; conditional or loop-nested calls are a compiler error.

---

## Gotchas

- `.svelte.ts` files (containing runes outside components) require Svelte 5 and the Svelte VS Code extension ≥ 0.9; older versions show false type errors.
- Cloudflare Pages adapter (`@sveltejs/adapter-cloudflare`) must be v5 or later to support the Svelte 5 compilation output format.
- `$effect` does NOT run during SSR on the Cloudflare Workers runtime; use `onMount` (still available in Svelte 5) or server load functions for data that must be available at SSR time.
- Deep reactive proxies (`$state({})`) track property access; spreading the object (`{ ...reactiveObj }`) creates a snapshot, not a live reference — intentional but surprising.
- `$derived.by` caches its result until dependencies change; if you see stale values, ensure all accessed reactive values are declared with `$state` (plain `let` is not tracked).

---

## Verification

```bash
# Install Svelte 5 and the Cloudflare adapter
npm install svelte@^5 @sveltejs/kit@^2 @sveltejs/adapter-cloudflare@^5

# Run local dev with Cloudflare bindings (uses Wrangler proxy)
npx wrangler pages dev .svelte-kit/cloudflare -- --compatibility-date 2026-08-01

# Check compiled output uses rune signals (not Svelte 4 $$ stores)
npx svelte-check --tsconfig ./tsconfig.json
```

```svelte
<!-- Quick rune smoke-test component -->
<script lang="ts">
  let n = $state(0);
  const doubled = $derived(n * 2);
</script>
<button onclick={() => n++}>{n} → {doubled}</button>
```

Open in browser; clicking should update both values without page reload. Check Svelte DevTools panel to confirm signals rather than component stores.

---

## Related

- `sveltekit-cloudflare-pages-adapter.md`
- `signals-fine-grained-reactivity.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`
- `progressive-enhancement-workers-form-actions.md`
- `islands-architecture-cloudflare-pages-partial-hydration.md`

---

## Sources

- https://svelte.dev/docs/svelte/what-are-runes
- https://svelte.dev/docs/svelte/$state
- https://kit.svelte.dev/docs/adapter-cloudflare
- https://developers.cloudflare.com/pages/framework-guides/deploy-a-svelte-kit-site/
