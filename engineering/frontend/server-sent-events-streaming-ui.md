# server-sent-events-streaming-ui

**Issue:** A feature needs server-to-client realtime updates — live feed inserts, build-status ticks, AI token streaming, notification toasts — and the team reaches for WebSocket, accepting sticky-session load-balancer config, custom reconnect logic, and a new protocol to debug through every proxy. For one-way streams, Server-Sent Events (SSE) over plain HTTP gets automatic reconnection, event IDs with resume (`Last-Event-ID`), and named events for free, works with every CDN/proxy that handles streaming responses, and needs zero special infrastructure. The known failure modes are proxy buffering eating the stream, the browser's HTTP/1.1 connection limit, GET-only `EventSource` (no Authorization header), and React effect cleanup leaking duplicate connections.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When SSE instead of WebSocket

1. **Direction of data decides it.** If the client only receives (feed, dashboards, progress bars, LLM token streams, notifications), SSE is the simpler, more robust choice. If the client must push frequently mid-connection (chat typing, multiplayer, collaborative editing cursors), you need WebSocket — SSE's "client sends" path is just ordinary HTTP requests alongside the stream.
2. **No sticky sessions required.** WebSocket pins a long-lived TCP connection to one backend instance, forcing load balancers to route by session. SSE is a normal HTTP response; on reconnect the client hits whatever instance is healthy and resumes from `Last-Event-ID`, so state must live in a shared store (Redis stream, queue, database cursor), not in the connection.
3. **Infra-friendly.** SSE is `Content-Type: text/event-stream` over chunked HTTP — passes through Nginx, Cloudflare (with buffering disabled), and serverless platforms that support streaming responses (Next.js route handlers, Cloudflare Workers can both stream). WebSocket needs upgrade support at every hop.
4. **Builtin browser semantics.** Auto-reconnect with backoff, `Last-Event-ID` resume, and `event:` named channels are protocol-level — no client library needed. With WebSocket you reimplement all three and they will be wrong the first time (duplicate delivery on reconnect, missed events during the gap).

## EventSource mechanics that matter

1. **Wire format is three fields.** The server writes `event: <name>`, `data: <string>` (repeat `data:` lines for multi-line payloads), and `id: <event-id>`, blank line to flush. The browser dispatches a `MessageEvent` on the `EventSource` for named events or `onmessage` for unnamed ones — JSON payloads ride inside `data` and are parsed client-side.
   ```js
   const es = new EventSource('/api/feed');
   es.addEventListener('post', (e) => render(JSON.parse(e.data)));
   es.onerror = () => showReconnecting(); // browser retries automatically
   ```
2. **`id` is the resume cursor.** The browser stores the last received `id` and, on any reconnect (network blip or server close), sends it back as the `Last-Event-ID` request header. The server replays missed events from that cursor — this is the entire durability contract; servers that ignore the header drop events during every reconnect, which users experience as "the feed randomly misses things."
3. **Control the retry cadence.** The server can send `retry: 3000` (milliseconds) to set the browser's reconnect delay; default is ~3s with browser-chosen backoff. Set it deliberately — a busy server being hammered by thousands of 0-delay reconnects is a self-inflicted outage.
4. **ReadyState lifecycle.** `0` connecting, `1` open, `2` closed-permanently. `EventSource` only reaches `2` if the connection errored and the server disabled retries or the browser gave up — code that checks `es.readyState === 2` should surface an error UI and offer manual restart rather than silently dead-feeding.

## Beyond EventSource: fetch + ReadableStream

1. **EventSource cannot send headers or POST.** No `Authorization: Bearer …`, no custom headers, GET-only — which forces tokens into query strings (leaked into logs) for authenticated streams. The standard workaround is `fetch()` the event-stream endpoint and parse the body from a `ReadableStream` yourself, or use `@microsoft/fetch-event-source`, which adds header support, POST, and error-throwing semantics (EventSource swallows HTTP errors and retries forever against a 401).
2. **You inherit the reconnect logic.** With fetch-based streaming you implement retry, backoff, and re-sending `Last-Event-ID` yourself (the browser does not do it for plain fetch). `fetch-event-source` provides the skeleton; verify it fires `onclose`/`onerror` correctly behind your proxies.
3. **AbortController is mandatory.** A fetch stream without an `AbortController` tied to component unmount keeps the connection (and the server work) alive after the user navigates away. Create the controller, pass its signal, and call `.abort()` in cleanup — see the React section.
4. **Prefer EventSource when you can.** If the stream can be authenticated by cookie (same-origin or proper CORS credentials), plain `EventSource` with its free reconnect/resume is less code than any fetch-based parser. Reach for fetch-streaming only for the header/POST requirement.

## React integration and infrastructure gotchas

1. **One hook, one connection, real cleanup.** Open in `useEffect`, close (`es.close()` or `controller.abort()`) in the returned cleanup, and key the effect by the stream's identity (room id, feed id) — not by data that updates every event, which would reconnect per message. Buffer rapid bursts with a small queue + `requestAnimationFrame`/`startTransition` flush instead of `setState` per token when streaming at LLM speeds (hundreds of updates/sec stall React rendering).
2. **Strict Mode double-mount in dev.** React 18/19 Strict Mode mounts effects twice in development — an SSE effect without cleanup opens two connections, and events arrive duplicated. If you see doubled messages only in dev, the cleanup is missing; do not dedupe with keys as a "fix."
3. **Proxy buffering is the #1 silent killer.** Nginx (`proxy_buffering on` default) and some CDNs accumulate the stream and deliver it as one lump when the connection ends — the UI looks frozen then floods. Set `X-Accel-Buffering: no` on responses for Nginx, disable response buffering on your platform (Cloudflare: streaming supported for Workers responses; Vercel: check the runtime's streaming support), and disable gzip/compression middleware for `text/event-stream` since compressed buffering defeats chunking.
4. **HTTP/1.1 six-connection limit.** Over HTTP/1.1, each `EventSource` occupies one of the browser's ~6 connections per origin — open 3 streams plus images and the site stalls. Serve everything over HTTP/2+ (streams multiplex over one connection), and keep the app to one multiplexed stream endpoint (one connection, event names as channels) rather than N endpoints.
5. **Keep-alives and timeouts.** Corporate proxies and load balancers kill idle connections at 30–60s; the server should emit a comment line (`: ping`) every ~15–25s to keep the stream alive and detect dead clients. Design the server loop so a dropped client's write error closes and frees the handler (Workers: `cancel()` on the stream).

## Related

- `browser-fetch-patterns.md`
- `react-useeffect-cleanup.md`
- `react-query-patterns.md` (polling alternative when realtime is overkill)
- `next-js-route-handlers.md` (streaming responses in App Router)
