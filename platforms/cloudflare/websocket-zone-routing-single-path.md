# websocket-zone-routing-single-path

**Issue:** In example project's multi-deployment Cloudflare setup (a Next.js static export on Pages plus multiple Workers behind `example project-functions`), WebSocket connections could NOT ride the Pages proxy path. A WebSocket upgrade must terminate at a Worker via zone-level routing on the domain, so the only zone route configured on the domain is `api/streaming/*`, pointed at the streaming Worker; every other path is served path/proxy based through Pages. Getting this split wrong produces connections that hang, upgrade to nothing, or 404 with perfectly correct Worker code.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why the upgrade needs its own ingress path

1. **The Pages proxy path does not carry WebSocket upgrades.** Regular API traffic can be proxied/fetched through Pages Functions or service bindings because it is plain request/response HTTP, but a `GET` with `Upgrade: websocket` must be terminated by a Worker that returns the 101 Switching Protocols response — an intermediary hop that re-issues requests breaks the upgrade.
2. **Zone routing is what gives the Worker direct ingress.** A route like `example.com/api/streaming/*` binds that path prefix on the zone directly to the Worker, so the upgrade handshake reaches Worker code without a proxy layer in between. This is the single zone route on the domain; it exists specifically because WebSockets need it.
3. **Everything else stays path/proxy based.** All non-streaming traffic (the app shell, the 133 API routes) is served through Pages paths and proxying, keeping the zone's routing surface minimal — one zone route per special path prefix instead of a web of overlapping patterns.

## Zone routes vs Custom Domains for WebSockets

1. **Routes are pattern-based on an existing zone.** Per current Cloudflare routing docs, routes (e.g. `example.com/api/streaming/*`) are recommended when the Worker runs alongside other services on the same zone; non-matching paths fall through to the zone's existing origin. Only one route per pattern per zone is allowed.
2. **Custom Domains capture the whole hostname.** A Custom Domain routes all paths of a domain/subdomain to the Worker and auto-provisions DNS and TLS; Cloudflare recommends it when a Worker needs to accept WebSocket connections on a dedicated domain (e.g. `streaming.example.com`).
3. **Custom Domains are fetch()-able in-zone, routes are not.** A Custom Domain can be invoked via `fetch()` from other Workers in the same zone; a route cannot be targeted directly by URL. This matters if other Workers need to reach the WS endpoint server-side.
4. **Why a narrow zone route won here.** The domain is shared with the Pages app, so a Custom Domain per service would fragment hostnames; a single `api/streaming/*` route keeps the streaming Worker's blast radius to exactly the paths that need an upgrade, and every other path keeps its existing behavior.

## Terminating the upgrade in a Worker with Durable Objects

1. **Validate the upgrade request before billing it.** In the Worker's `fetch`, check the method/URL and the `Upgrade: websocket` header and return `426 Upgrade Required` if missing — otherwise invalid requests still consume Worker invocations.
2. **Forward to a Durable Object stub.** Map the connection to an object (e.g. `env.WEBSOCKET_SERVER.idFromName(roomId)`), call `stub.fetch(request)`, and have the object create a `WebSocketPair`, take the server end, and return a 101 response carrying the client end.
3. **Use the Hibernation API, not the event-listener API.** Call `this.ctx.acceptWebSocket(server)` instead of `server.accept()` and implement `webSocketMessage`/`webSocketClose` handlers. A hibernated object is evicted from memory while clients stay connected to the edge, and Billable Duration (GB-s) charges do not accrue during hibernation.
4. **Persist per-connection state across hibernation.** Store structured-clonable state with `setWebSocketAutoResponse`-adjacent attachment APIs (`serializeAttachment`/`deserializeAttachment`, max 16,384 bytes); anything larger goes to the Storage API with a key in the attachment. Incoming messages auto-wake the object and re-run its constructor, so keep the constructor minimal.
5. **Batch messages to cut per-frame overhead.** Pack multiple logical messages into one frame with an envelope format, flushing roughly every 50–100 ms or 50–100 messages, to reduce per-message runtime and context-switch overhead.

## Operational gotchas

1. **Deploys drop every live socket.** Deploying new code restarts Durable Objects and disconnects all connected WebSocket clients; clients need reconnect logic with backoff, and deploys should be scheduled accordingly.
2. **Timers and alarms defeat hibernation.** `setTimeout`/`setInterval`, alarms, and outbound WebSocket connections keep the object alive (outbound sockets up to 15 minutes), so move periodic work to alarms only when actually needed.
3. **Ping/pong is handled by the runtime.** The runtime automatically answers ping frames with pongs without waking the object, and control frames never invoke `webSocketMessage` — do not implement your own keep-alive pings at the application layer.
4. **Route present but 404? Check ingress before code.** A Worker with correct code and no ingress (missing/mis-scoped zone route) is a black box that 404s; confirm the route exists and matches the exact path prefix before debugging Worker code (see `cloudflare/pages-404-worker-split-diagnosis.md`).
