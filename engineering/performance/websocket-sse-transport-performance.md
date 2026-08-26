# websocket-sse-transport-performance

**Issue:** Real-time features (live feeds, notifications, dashboards, chat, collaborative cursors) force a transport choice — WebSocket, Server-Sent Events, long-polling, or newer options like WebTransport — and the wrong pick taxes every layer: connection count and memory on the server, reconnection storms after network blips, CDN incompatibility, and per-message latency on the client. Benchmarks consistently show WebSocket and SSE within a few milliseconds of each other on throughput, so the real decision factors are directionality, reconnection semantics, infrastructure fit (especially serverless and edge runtimes, where long-lived stateful sockets are awkward), and fan-out cost. This article covers how to choose, and how to make whichever transport you pick survive flaky mobile networks cheaply.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the transport

1. **One-way streams should use SSE.** If the client mostly receives (tickers, feeds, status, notifications), Server-Sent Events over plain HTTP is the simpler machine: automatic browser reconnection, built-in Last-Event-ID resumption, text-event-stream framing the CDN layer can sometimes even cache or proxy, and no upgrade handshake. Community experience in 2025 coalesced around the view that SSE covers the large majority of real-time use cases.
2. **Bidirectional or high-frequency duplex needs WebSocket.** Chat, multiplayer, collaborative editing, and WebRTC signaling need a single low-latency bidirectional channel; layering client-to-server POSTs over SSE works but forfeits ordering guarantees and adds per-message request overhead exactly when message rates are highest.
3. **Benchmarks should not decide this.** Measured differences are small — WebSocket tends to be on the order of ~3 ms lower per-message latency in casual benchmarks, with SSE using slightly more CPU on some servers — both noise-level next to architecture costs like reconnect storms or sticky sessions. Decide on semantics and infrastructure, then verify latency is acceptable.
4. **Keep polling for the tail.** Long-polling remains a legitimate fallback for restrictive proxies and a pragmatic choice for slow-moving data (30-60 s freshness); it also caps idle connections, which matters on per-connection-metered platforms.

## Performance characteristics

1. **Handshake overhead.** WebSocket requires an HTTP upgrade per connection; SSE is a single streaming GET. After establishment both are a persistent pipe — per-message framing is minimal (2-14 bytes WebSocket header; SSE line-based text), so raw protocol overhead only matters at thousands of messages per second.
2. **HTTP/2 helps SSE more than WebSocket.** Many SSE streams over HTTP/1.1 hit the six-connections-per-host limit (a page with several tabs or several streams stalls); HTTP/2 multiplexing removes that, which is another reason SSE plays well with modern CDNs and fronting proxies.
3. **Server memory scales with connections.** Each live socket or stream holds buffers, timers, and (in Node) event listeners; a Node process comfortably holds tens of thousands of idle WebSockets but far fewer active ones. Track RSS and event-loop lag under connection load, not just throughput.
4. **Message size dominates.** Payload efficiency (compact keys, delta updates instead of full snapshots, binary frames for numeric-heavy streams on WebSocket) buys more than any transport swap; batch bursts server-side and flush on an interval (16-100 ms) to smooth spikes.

## Reconnection and resumption

1. **EventSource reconnects for free.** The browser retries automatically with exponential backoff and sends Last-Event-ID so the server can replay missed events — implement the replay cursor and most mobile-network blips become invisible to users. Hand-rolled WebSocket clients must recreate all of this.
2. **Add a heartbeat on both.** Proxies and mobile radios silently drop idle connections; a 25-30 s ping/pong (WebSocket) or comment-line keep-alive (SSE) detects dead connections promptly so clients reconnect instead of waiting on TCP timeouts measured in minutes.
3. **Backoff with jitter.** After deploy restarts or network partition recovery, thousands of clients reconnecting simultaneously (a thundering herd) can DDoS your own server; exponential backoff with randomized jitter plus server-side resume-from-cursor keeps the storm survivable.
4. **Version the protocol.** Reconnecting clients can be old builds talking to a new server; include a protocol version in the connection URL so the server can gate features instead of corrupting state.

## Serverless and edge fit

1. **Stateless runtimes favor SSE.** Plain-HTTP streaming matches serverless HTTP functions and edge runtimes: the response stays open while the function lives, and platforms cap duration — SSE survives duration caps better because reconnect-and-resume is native. Persistent WebSocket servers need Durable Objects or equivalent stateful hosting to coordinate fan-out, which is exactly the pattern Cloudflare recommends for real-time apps on Workers.
2. **Fan-out architecture beats per-connection polling of the source.** Whether on Workers (broadcast via a Durable Object holding the subscriber set) or on Node (Redis pub/sub feeding sockets), each upstream event should touch each connection once; polling the database per connection re-introduces the N+1 pattern at real-time scale.
3. **CDN and proxies must be checked.** Streaming responses disable response buffering (disable Nagle-style flushing on your framework; beware gzip middlewares that buffer); verify a curl -N receives events immediately in production, since many reverse proxies buffer text/event-stream by default and add tens of seconds of latency.
4. **Authentication over streams.** WebSockets cannot set custom headers at handshake from browsers, so auth moves to cookies, subprotocols, or ticket params; SSE rides normal request headers. Whichever you use, use short-lived credentials on reconnect so resumed sessions cannot outlive their permissions indefinitely.

## Monitoring

1. **Track reconnect rate as a health metric.** Reconnects per client per hour is the single best transport health signal; a spike indicates proxy changes, server restarts, or heartbeat failures long before users report staleness.
2. **Measure end-to-end event latency.** Timestamp events at publish, and compute p50/p95 arrival delay in the client; log separately from connection uptime, because a healthy-looking connection with slow publishes is a backend problem no transport change will fix.
3. **Cap and expose subscription counts.** Instrument concurrent streams per route and per user; runaway duplicate subscriptions (pages that never close their EventSource on unmount) are the most common self-inflicted outage in SSE apps — close on pagehide as well, since bfcache-frozen pages hold connections open.
