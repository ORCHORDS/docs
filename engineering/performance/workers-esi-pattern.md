# Edge-Side Includes (ESI) Pattern with Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A page is composed of independently cacheable fragments: a static shell, a dynamic
navigation bar personalised per user, a product listing cached for 60 s, and a cart
widget that must never be cached. Traditional server-side rendering assembles the
entire page on origin, forcing the lowest common denominator cache TTL — usually zero —
because one fragment is dynamic. Edge-Side Includes (ESI) moves assembly to the edge:
each fragment is fetched and cached independently, and the edge stitches them into the
final HTML before delivery. Cloudflare Workers can implement a full ESI pipeline without
Varnish or any proprietary ESI processor.

## Context

ESI was originally a W3C specification targeting CDNs (Akamai, Varnish) but never saw
broad adoption in the HTTP/2 era. Cloudflare Workers provide the primitives needed to
implement the same pattern: fast in-process HTML parsing, subrequest fan-out with
independent cache-control per fragment, and streaming response assembly. A Workers-based
ESI implementation is fully programmable: fragment substitution rules are JavaScript
code, not XML directives, which allows conditional inclusion, header forwarding, and
per-user cache key customisation that generic ESI processors cannot express.

## Fragment Resolution with Parallel fetch

The core pattern: parse `<esi:include >` tags from the shell template, resolve
all fragments in parallel, and stream the assembled response.

```typescript
interface EsiFragment {
  tag: string;      // the original <esi:include ...> string
  src: string;      // the fragment URL
  fallback: string; // content to use if fragment fetch fails
}

function extractFragments(html: string): EsiFragment[] {
  const pattern = /<esi:include\s+]+)"(?:\s+onerror="([^"]*)")?[^>]*>/gi;
  const fragments: EsiFragment[] = [];
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(html)) !== null) {
    fragments.push({
      tag: match[0],
      src: match[1],
      fallback: match[2] === "continue" ? "" : `<!-- ESI error: ${match[1]} -->`,
    });
  }

  return fragments;
}

async function resolveFragments(
  fragments: EsiFragment[],
  req: Request
): Promise<Map<string, string>> {
  const results = new Map<string, string>();

  await Promise.allSettled(
    fragments.map(async ({ tag, src, fallback }) => {
      try {
        const fragmentReq = new Request(src, {
          headers: {
            // Forward user context for personalisation
            cookie: req.headers.get("cookie") ?? "",
            "x-forwarded-for": req.headers.get("cf-connecting-ip") ?? "",
          },
        });
        const res = await fetch(fragmentReq);
        if (!res.ok) {
          results.set(tag, fallback);
          return;
        }
        results.set(tag, await res.text());
      } catch {
        results.set(tag, fallback);
      }
    })
  );

  return results;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // 1. Fetch the shell template (long-lived cache)
    const shellRes = await fetch("https://origin.example.com/shell", {
      cf: { cacheEverything: true, cacheTtl: 3600 },
    });
    const shell = await shellRes.text();

    // 2. Extract fragment directives
    const fragments = extractFragments(shell);
    if (fragments.length === 0) {
      return new Response(shell, { headers: { "content-type": "text/html" } });
    }

    // 3. Resolve all fragments in parallel
    const resolved = await resolveFragments(fragments, req);

    // 4. Substitute
    let assembled = shell;
    for (const [tag, content] of resolved) {
      assembled = assembled.replaceAll(tag, content);
    }

    // 5. Determine response cache TTL from the most-restrictive fragment
    return new Response(assembled, {
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "private, no-store", // personalised response — do not cache
      },
    });
  },
};
```

## Per-Fragment Cache Control via Cloudflare Cache API

Fragment responses can be independently cached at the edge using the Cache API,
applying each fragment's own `cache-control` directive without letting a single dynamic
fragment poison the entire page TTL.

```typescript
async function fetchFragment(src: string, cache: Cache): Promise<string> {
  const cacheKey = new Request(src);

  // Serve from edge cache if available
  const cached = await cache.match(cacheKey);
  if (cached) return cached.text();

  const res = await fetch(src);
  if (!res.ok) return "";

  const text = await res.text();

  // Cache only if the fragment allows it
  const cc = res.headers.get("cache-control") ?? "";
  const isPublic = cc.includes("public") && !cc.includes("no-store");

  if (isPublic) {
    // Store a clone with the original cache-control so edge expiry is correct
    await cache.put(cacheKey, new Response(text, {
      headers: { "cache-control": cc, "content-type": "text/html" },
    }));
  }

  return text;
}

export default {
  async fetch(req: Request): Promise<Response> {
    const cache = caches.default;
    const shellRes = await fetch("https://origin.example.com/shell");
    const shell = await shellRes.text();
    const fragments = extractFragments(shell);

    const results = await Promise.allSettled(
      fragments.map((f) => fetchFragment(f.src, cache))
    );

    let assembled = shell;
    fragments.forEach((f, i) => {
      const content = results[i].status === "fulfilled" ? results[i].value : f.fallback;
      assembled = assembled.replaceAll(f.tag, content);
    });

    return new Response(assembled, {
      headers: { "content-type": "text/html" },
    });
  },
};
```

## Streaming Assembly for Improved TTFB

Assembling the response as a `ReadableStream` lets the browser begin parsing HTML while
the Worker is still awaiting slower fragments. Segment the shell at each `<esi:include>`
boundary and enqueue static segments immediately.

```typescript
function streamAssemble(shell: string, resolved: Map<string, string>): ReadableStream {
  return new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      const esiPattern = /<esi:include\s+]+)"[^>]*>/gi;
      let lastIndex = 0;
      let match: RegExpExecArray | null;

      while ((match = esiPattern.exec(shell)) !== null) {
        // Enqueue the static segment before this tag
        controller.enqueue(enc.encode(shell.slice(lastIndex, match.index)));
        // Enqueue the resolved fragment (or empty string on failure)
        const content = resolved.get(match[0]) ?? "";
        controller.enqueue(enc.encode(content));
        lastIndex = match.index + match[0].length;
      }

      // Enqueue the tail of the shell after the last tag
      controller.enqueue(enc.encode(shell.slice(lastIndex)));
      controller.close();
    },
  });
}

export default {
  async fetch(req: Request): Promise<Response> {
    const [shellRes] = await Promise.all([
      fetch("https://origin.example.com/shell"),
    ]);
    const shell = await shellRes.text();
    const fragments = extractFragments(shell);
    const resolved = await resolveFragments(fragments, req);

    return new Response(streamAssemble(shell, resolved), {
      headers: { "content-type": "text/html; charset=utf-8" },
    });
  },
};
```

## Anti-patterns

**Cascading ESI tags** — a fragment that itself contains `<esi:include>` directives
creates a recursive fetch dependency. Resolve only one level unless you explicitly add
a recursion guard with a depth counter.

**Forwarding the full `cookie` header to all fragments** — this passes session tokens
to every fragment endpoint, which may be unnecessary and widens the attack surface. Only
forward cookies that specific fragment routes actually need.

**Caching the assembled page** — after ESI assembly, the response reflects the least-
cacheable fragment. Caching the assembled output at the edge permanently locks in the
state of the fastest-expiring fragment for all users. Cache fragments individually;
never cache the assembled result unless all fragments are public with identical TTLs.

**Large shell templates in memory** — parsing a multi-MB HTML shell with `replaceAll`
is O(n × m) in the number of fragments. Use streaming assembly or limit shell size
to < 100 KB.

## Gotchas

- `<esi:include>` tags inside `<script>` or `<style>` blocks are a security hazard
  if the fragment content is attacker-controlled. Sanitise fragment HTML or restrict
  fragment origins to trusted internal services.
- Fragment fetch errors are silently swallowed if `onerror="continue"` is set. Monitor
  fragment error rates separately in Analytics Engine.
- ESI assembly doubles or triples the Worker's subrequest count. A page with 10
  fragments plus its own origin fetch uses 11 subrequests per invocation — track this
  against the 50-concurrent and 1 000-total limits.
- The `cf` fetch options (`cacheTtl`, `cacheEverything`) only apply when the request is
  cacheable at Cloudflare's edge. Fragments with cookies in the request will not be
  cached by `cf` options; use the Cache API explicitly with a cookie-stripped cache key
  for public fragments that are fetched with user context.

## Verification

```bash
# Confirm shell is cached separately (should return HIT after first request)
curl -si https://worker.example.com/ | grep -i "cf-cache-status"

# Confirm fragment endpoint has correct cache-control
curl -si https://origin.example.com/fragments/nav | grep -i cache-control

# Measure TTFB with streaming assembly vs buffered
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://worker.example.com/
```

Add a `x-esi-fragments` response header listing the fragment SRCs and their cache
status (hit/miss) to aid debugging:

```typescript
headers.set("x-esi-fragments", fragments.map((f) => f.src).join(", "));
```

## Related

- `workers-subrequest-fanout-parallelism.md`
- `cloudflare-cache-api-workers-mobile.md`
- `streaming-ssr-performance.md`
- `edge-caching-patterns.md`
- `partial-hydration-islands.md`

## Sources

- https://www.w3.org/TR/esi-lang/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/workers/runtime-apis/streams/readablestream/
- https://developers.cloudflare.com/workers/platform/limits/#subrequests
