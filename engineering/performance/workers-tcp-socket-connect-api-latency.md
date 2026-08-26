# Workers TCP Socket `connect()` API — Direct Connection Latency

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker proxies requests to a raw TCP service (Redis, Postgres, SMTP, custom protocol).
Using `fetch()` adds an HTTP layer the upstream does not speak; rolling a WebSocket
tunnel is complex and wastes framing overhead. Measured RTT from Worker to origin sits
20–80 ms above direct TCP because every request negotiates a fresh TLS + HTTP/1.1
handshake through a third-party proxy.

## Context

Cloudflare Workers exposes `connect()` from the `cloudflare:sockets` module — a
WHATWG-compatible TCP Socket that dials the remote host directly from the edge PoP.
Unlike `fetch()`, the socket survives across multiple reads/writes within a single
request lifecycle, enabling pipelining and protocol multiplexing without HTTP overhead.
Connections are *not* shared across isolate invocations (no true cross-request pool),
but within one request you can reuse the socket for all sub-operations and close it
explicitly when done, eliminating per-command handshake cost.

## Opening a TCP Socket

```typescript
import { connect } from 'cloudflare:sockets';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const socket = connect({ hostname: env.REDIS_HOST, port: 6379 });

    const writer = socket.writable.getWriter();
    const reader = socket.readable.getReader();

    // Send PING command in RESP protocol
    await writer.write(new TextEncoder().encode('*1\r\n$4\r\nPING\r\n'));

    const { value } = await reader.read();
    const pong = new TextDecoder().decode(value); // "+PONG\r\n"

    await writer.close();
    await socket.close();

    return new Response(pong.trim());
  },
};
```

## Pipelining Multiple Commands in One RTT

Batch writes before issuing any reads to exploit TCP's full-duplex channel.

```typescript
async function redisPipeline(
  socket: Socket,
  commands: string[],
): Promise<string[]> {
  const writer = socket.writable.getWriter();
  const reader = socket.readable.getReader();

  // Write all commands without waiting for responses
  for (const cmd of commands) {
    await writer.write(new TextEncoder().encode(cmd));
  }

  // Read all responses
  const results: string[] = [];
  let buffer = '';
  const decoder = new TextDecoder();

  while (results.length < commands.length) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // RESP simple string lines end with \r\n
    const lines = buffer.split('\r\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.length > 0) results.push(line);
    }
  }

  return results;
}
```

## TLS Upgrade on an Existing Socket

```typescript
import { connect } from 'cloudflare:sockets';

const socket = connect(
  { hostname: 'db.example.com', port: 5432 },
  { secureTransport: 'starttls' }, // negotiate TLS after initial plaintext
);

// Send Postgres StartupMessage in cleartext, then upgrade
const plain = socket.writable.getWriter();
await plain.write(buildPgStartupMessage());

// Upgrade to TLS after receiving server's TLS-ready signal
const tlsSocket = await socket.startTls();
const secureWriter = tlsSocket.writable.getWriter();
await secureWriter.write(buildPgAuthMessage());
```

## Handling Backpressure with ReadableStream

Avoid buffering the entire response in memory for large result sets.

```typescript
async function streamQuery(socket: Socket): Promise<Response> {
  const writer = socket.writable.getWriter();
  await writer.write(encodeQuery('SELECT * FROM large_table'));

  // Stream the socket's ReadableStream directly to the Response body
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      controller.enqueue(parseProtocol(chunk)); // strip wire framing
    },
  });

  socket.readable.pipeTo(writable).catch(() => {}); // don't await — background

  return new Response(readable, {
    headers: { 'Content-Type': 'application/octet-stream' },
  });
}
```

## Reusing the Socket for Multiple Operations Within a Request

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const socket = connect({ hostname: env.DB_HOST, port: 5432 });

    const session = await openPgSession(socket);     // auth once
    const row = await session.query('SELECT 1');     // query
    const meta = await session.query('SELECT NOW()'); // reuse same conn
    await session.terminate();

    return Response.json({ row, meta });
  },
};
```

## Anti-patterns

- **Opening a socket per sub-operation inside one request** — each `connect()` starts
  a new TCP+TLS handshake; batch all I/O through one socket per request.
- **Leaving sockets open without `socket.close()`** — leaks the connection for the
  remainder of the CPU time budget and may exhaust the PoP's ephemeral port range.
- **Ignoring `socket.closed` promise** — if the remote resets mid-stream the error
  surfaces only on the `closed` promise; failing to await it silently drops errors.
- **Using `connect()` for HTTP upstreams** — `fetch()` already handles pooling and
  TLS resumption for HTTP; `connect()` adds code complexity with no latency gain.

## Gotchas

- `connect()` is only available inside the `cloudflare:sockets` module; it is not
  a global. Add `"cloudflare:sockets"` to `external_modules` in `wrangler.toml` if
  bundling with esbuild.
- Sockets are *per-request*, not shared across isolate activations. There is no
  persistent pool; Hyperdrive provides that for Postgres specifically.
- `secureTransport: 'on'` performs TLS from the very first byte; `'starttls'` allows
  a cleartext handshake before upgrade. Using the wrong mode results in a hung read.
- CPU time consumed waiting on `reader.read()` counts against the Worker's wall-clock
  limit, not just CPU time. Long-running queries may hit the 30 s wall-clock cap.

## Verification

```bash
# Measure socket RTT vs fetch RTT from a Wrangler tail session
wrangler tail --format=json | jq '.logs[] | select(.message | test("socket_rtt|fetch_rtt"))'

# Confirm no leaked connections (check PoP metrics in Cloudflare dashboard)
# Workers > Analytics > Subrequests — "TCP connections opened" per invocation should equal 1
```

Add `console.timeStamp('socket_opened')` and `console.timeStamp('first_byte')` to
measure handshake cost in production tail logs.

## Related

- `hyperdrive-connection-pooling-workers.md` — persistent Postgres pool via Hyperdrive
- `workers-fetch-connection-reuse-tcp.md` — HTTP-level connection reuse with fetch
- `durable-objects-low-latency-stateful.md` — sticky routing for stateful protocols
- `tls-handshake-0rtt-resumption.md` — 0-RTT TLS for latency reduction

## Sources

- Cloudflare Docs: [TCP Sockets](https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/)
- WHATWG Sockets API explainer
- Cloudflare Blog: "Direct sockets in Workers" (2023)
