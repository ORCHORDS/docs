# worker-openai-compat-gateway

**Issue:** A home Ollama GPU box has no stable public entry point, but every client we use (editors, agent frameworks, OpenAI SDKs) already speaks the OpenAI wire format. The fix was a Cloudflare Worker exposing an OpenAI-compatible `/v1/chat/completions` endpoint that proxies to the home box through a tunnel, deployed both on `workers.dev` and on a custom route attached to a zone via `wrangler routes` (path-based routing). The `workers.dev` subdomain turned out to be unreliable for long-lived REST calls — clients hung with 10405-class timeouts that were never seen once the same Worker was served on the custom-route path — and streaming chat through an edge proxy has its own CPU/wall-clock rules that the gateway must respect.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why the OpenAI-Compat Surface Wins

1. **Clients standardize on the OpenAI shape.** Pointing any OpenAI SDK, LibreChat-style frontend, or agent framework at `BASE_URL=https://<gateway>/v1` works with zero client changes, which is why Cloudflare itself exposes OpenAI-compatible endpoints for Workers AI and AI Gateway — we reuse the same convention for a private upstream instead of a cloud provider.
2. **The Worker is the only public, secret-holding component.** The home box never exposes an IP; the Worker holds the upstream tunnel hostname and the shared key as secrets, terminates TLS at the edge, and is the single place to add auth, rate limits, and logging for all clients.
3. **Ollama's native `/v1` endpoint shrinks the translation layer.** Modern Ollama serves OpenAI-compatible `/v1/chat/completions` directly alongside `/api/chat`, so the gateway can often pass the body through untouched and only rewrite auth headers, model names, and error shapes instead of translating formats.
4. **A custom Worker beats AI Gateway for non-cloud upstreams.** AI Gateway's unified API normalizes known providers; a home box behind a rotating tunnel URL is not a supported provider, so a thin Worker (community examples like `kasuboski/openai-gateway` show the pattern) with our own upstream-resolution logic is the right tool.

## Streaming SSE Through the Worker

1. **Never buffer the completion body.** Return `fetch(upstream)`'s body directly (or through a `TransformStream` if rewriting chunks); Workers have a 128 MB per-isolate memory ceiling and buffering a long SSE stream will both blow memory and add minutes of perceived latency.
2. **Wall-clock time is unlimited while the client stays connected.** HTTP-triggered Workers have no hard duration limit — a Worker still streaming a response body stays active — so a 3-minute token stream is legal; what kills you is CPU time, not connection time.
3. **Budget CPU time deliberately.** CPU limits are 10 ms per request on the Free plan, 30 s default / up to 300 s configurable on paid (`cpu_ms` in wrangler config, raised in March 2025); a pure pass-through proxy uses microseconds of CPU because waiting on I/O does not count, but chunk rewriting or JSON parsing per SSE event adds up fast.
4. **Keep-alive bytes defeat idle connection reaping.** Emitting SSE comment lines (`: ping`) or flushing a heartbeat every 15-25 s keeps intermediate proxies from closing the connection during long thinking pauses from the small local model.
5. **Map subrequest limits into the design.** Free plan allows 50 fetches per invocation (paid default is far higher and configurable), and only 6 simultaneous connections may be waiting for response headers — fine for a single-upstream proxy, but a dealbreaker for fan-out patterns unless connections are serialized.

## workers.dev Quirks vs the Custom Route

1. **The 10405-class hang was real and subdomain-specific.** REST clients calling the gateway on its `workers.dev` subdomain intermittently hung until client timeout with a 10405-class error; the identical Worker deployed on a zone-owned path via `wrangler routes` (e.g. `route = { pattern = "zone.tld/llm/*", zone_name = "zone.tld" }`) never reproduced it. Treat `workers.dev` as a demo surface, not an API endpoint for programmatic clients.
2. **Path-based routing on a zone keeps one hostname for everything.** With routes, the gateway lives at `zone.tld/llm/v1/chat/completions` next to other services on the same zone, which avoids per-service subdomain sprawl and lets zone-level WAF, rate-limiting, and bot rules apply uniformly.
3. **Zone routes need the zone on Cloudflare.** Routes only exist on zones Cloudflare proxies; `workers.dev` needs nothing, which is why we kept both — `workers.dev` as a canary/deploy check, the route as the real entry point clients depend on.
4. **Same-zone worker-to-worker calls require service bindings.** A plain `fetch()` from one Worker to another Worker on the same zone fails; if a sibling Worker (auth, audit) must be called, use Service Bindings or target a Custom Domain, never the zone route.
5. **Health-check both surfaces independently.** Because behavior differs, uptime monitoring watches the custom route (the path clients use) and the `workers.dev` URL separately, so a subdomain-specific degradation pages us instead of being masked by the healthy route.

## Request Translation and Error Mapping

1. **Normalize errors into OpenAI's error envelope.** Upstream failures (tunnel down, Ollama 500, guard-proxy 429) get rewritten to `{"error": {"message": ..., "type": ..., "code": ...}}` with an appropriate HTTP status, because OpenAI SDK retry logic keys off that shape and off status codes (429 retry, 5xx retry, 4xx fail).
2. **Inject timeouts with `AbortSignal`.** Every upstream fetch carries an `AbortSignal.timeout()` — a wedged home model must surface as a fast 504 to the client, not a hang that occupies the connection until the client gives up.
3. **Translate model names at the edge.** Clients send public model aliases; the gateway maps them to whatever the home box actually has loaded, so swapping the local model never requires touching client configs.
4. **Strip and re-add auth on both sides.** Validate the client's bearer token against a Worker secret (or KV-held key set) before proxying, then replace it with the upstream key — never forward client credentials to the home network, and never leak the upstream key to clients.
5. **Log metadata, never payloads.** Analytics Engine gets model, token counts, latency, and status per request; prompt and completion text stay off the edge logs since the edge is the only component that sees both clients and the home network.
