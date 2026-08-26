# Workers TCP Sockets — Outbound connect() for Raw Protocol Clients

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need a Workers handler to speak a raw TCP protocol — Postgres wire, Redis RESP, SMTP submission, a proprietary binary protocol — without wrapping an HTTP adapter. Existing Cloudflare bindings (Hyperdrive, KV, D1) do not cover your target, or you are building a generic proxy that must open arbitrary outbound TCP connections.

## Context

Workers expose `connect()` from the `cloudflare:sockets` module (module syntax only). It returns a `Socket` with a `ReadableStream` and `WritableStream`, and supports optional TLS via `startTls()`. Connections are tied to the request lifetime unless held in a Durable Object. Ports 25 (SMTP relay), 587, and a small set of others are blocked by default; 465 (SMTPS) and standard database ports are open.

## 1 — Opening a Raw TCP Connection

```typescript
import { connect } from 'cloudflare:sockets';

interface Env {}

export default {
  async fetch(request: Request, _env: Env): Promise<Response> {
    const socket = connect({ hostname: 'db.example.com', port: 5432 });

    const writer = socket.writable.getWriter();
    const reader = socket.readable.getReader();

    // Send a startup message bytes (simplified Postgres example)
    const startupMsg = buildPostgresStartupMessage('mydb', 'myuser');
    await writer.write(startupMsg);

    const { value } = await reader.read();
    await writer.close();
    await socket.close();

    return new Response(value ?? new Uint8Array(), {
      headers: { 'Content-Type': 'application/octet-stream' },
    });
  },
};

function buildPostgresStartupMessage(db: string, user: string): Uint8Array {
  // Real implementation would encode the Postgres wire protocol
  const encoder = new TextEncoder();
  return encoder.encode(`\x00\x00\x00\x08\x00\x03\x00\x00database\x00${db}\x00user\x00${user}\x00\x00`);
}
```

## 2 — TLS Upgrade with startTls()

```typescript
import { connect } from 'cloudflare:sockets';

async function tlsConnect(host: string, port: number): Promise<Socket> {
  // Option A: TLS from the start
  const tlsSocket = connect(
    { hostname: host, port },
    { secureTransport: 'on' },
  );
  return tlsSocket;
}

async function starttlsConnect(host: string, port: number): Promise<Socket> {
  // Option B: plain TCP, then upgrade (STARTTLS pattern)
  const plain = connect({ hostname: host, port }, { secureTransport: 'starttls' });

  // Exchange plain-text EHLO before upgrading
  const writer = plain.writable.getWriter();
  await writer.write(new TextEncoder().encode('EHLO example.com\r\n'));
  writer.releaseLock();

  // Upgrade to TLS — returns a new Socket
  const tls = plain.startTls();
  return tls;
}
```

## 3 — RESP Protocol Redis Client Pattern

```typescript
import { connect } from 'cloudflare:sockets';

interface Env { REDIS_HOST: string; REDIS_PORT: string; REDIS_PASSWORD: string; }

export async function redisGet(env: Env, key: string): Promise<string | null> {
  const socket = connect(
    { hostname: env.REDIS_HOST, port: Number(env.REDIS_PORT) },
    { secureTransport: 'on' },
  );

  const enc = new TextEncoder();
  const dec = new TextDecoder();

  const writer = socket.writable.getWriter();
  const reader = socket.readable.getReader();

  // AUTH
  await writer.write(enc.encode(`*2\r\n$4\r\nAUTH\r\n$${env.REDIS_PASSWORD.length}\r\n${env.REDIS_PASSWORD}\r\n`));
  // GET
  await writer.write(enc.encode(`*2\r\n$3\r\nGET\r\n$${key.length}\r\n${key}\r\n`));

  // Read responses (simplified: assumes two bulk-string responses)
  const chunks: Uint8Array[] = [];
  let done = false;
  while (!done) {
    const { value, done: d } = await reader.read();
    if (value) chunks.push(value);
    done = d;
    // In production: parse RESP frames and break when both responses are complete
    break;
  }

  await writer.close();
  await socket.close();

  const raw = dec.decode(chunks[1] ?? new Uint8Array());
  // Parse RESP bulk string: +OK\r\n$5\r\nhello\r\n
  const match = raw.match(/\$\d+\r\n(.+)\r\n/);
  return match ? match[1] : null;
}
```

## 4 — Holding TCP Connections in a Durable Object

Stateless Workers close the TCP socket at the end of the request. For persistent connections, move the socket into a Durable Object.

```typescript
// src/do/tcp-pool.ts
import { connect, Socket } from 'cloudflare:sockets';

export class TcpPool implements DurableObject {
  private socket: Socket | null = null;

  constructor(private state: DurableObjectState, private env: { BACKEND_HOST: string }) {}

  async getOrCreateSocket(): Promise<Socket> {
    if (this.socket && !this.socket.closed) return this.socket;
    this.socket = connect(
      { hostname: this.env.BACKEND_HOST, port: 6379 },
      { secureTransport: 'on' },
    );
    return this.socket;
  }

  async fetch(request: Request): Promise<Response> {
    const socket = await this.getOrCreateSocket();
    // Use socket.writable / socket.readable for the request
    return new Response('ok');
  }
}
```

## 5 — Error Handling and Reconnection

```typescript
import { connect } from 'cloudflare:sockets';

async function connectWithRetry(
  host: string,
  port: number,
  retries = 3,
): Promise<Socket> {
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const socket = connect({ hostname: host, port });
      // Verify connectivity by waiting for the first byte (e.g. server banner)
      const reader = socket.readable.getReader();
      const { value } = await reader.read();
      reader.releaseLock();
      if (!value) throw new Error('Empty server banner');
      return socket;
    } catch (err) {
      if (attempt === retries - 1) throw err;
      // Brief backoff before retry
      await new Promise(r => setTimeout(r, 50 * (attempt + 1)));
    }
  }
  throw new Error('unreachable');
}
```

## 6 — Streaming Binary Data Through a Worker Response

```typescript
import { connect } from 'cloudflare:sockets';

export default {
  async fetch(request: Request): Promise<Response> {
    const target = new URL(request.url).searchParams;
    const host = target.get('host') ?? '';
    const port = Number(target.get('port') ?? 0);

    if (!host || !port) return new Response('Missing host/port', { status: 400 });

    const socket = connect({ hostname: host, port });

    // Pipe the TCP readable stream directly as the HTTP response body
    return new Response(socket.readable as ReadableStream<Uint8Array>, {
      headers: { 'Content-Type': 'application/octet-stream' },
    });
  },
};
```

## Anti-patterns

- **Opening a new TCP socket on every stateless Worker request** for protocols that benefit from persistent connections (Redis, Postgres) — use Hyperdrive for Postgres or a Durable Object for custom protocols.
- **Not calling `socket.close()` after use** — sockets consume the subrequest budget and may delay isolate eviction even after the response is sent.
- **Treating `socket.readable` as a line-oriented stream** — TCP delivers bytes in arbitrary chunks; always accumulate and parse frames before acting on data.
- **Using Service Worker syntax** — `connect()` is only available in module-format Workers; Service Worker syntax will throw a `ReferenceError`.

## Gotchas

- Port 25 is blocked outright. Ports 587 and 465 require the `allowPortForTesting` flag in `wrangler.toml` for local dev; production Workers respect network policy.
- `socket.closed` is a Promise, not a boolean; use `await socket.closed` to wait for the remote close rather than polling.
- `connect()` counts against the subrequest limit (1000 per request in Unbound; 50 in Bundled).
- TLS certificate verification is on by default for `secureTransport: 'on'`; self-signed internal CAs require the `allowSelfSignedCertificates` option (use only in controlled environments).
- `startTls()` can only be called once per socket; calling it twice throws.

## Verification

```bash
# Local test via wrangler dev
curl "http://localhost:8787/?host=example.com&port=80"
# Should stream the raw TCP response bytes from example.com:80
```

## Related

- `cloudflare-hyperdrive-connection-pooling-d1-pg.md`
- `durable-objects-best-practices.md`
- `cloudflare-spectrum-tcp-udp-proxy.md`
- `workers-resource-limits.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/#starttls
- https://blog.cloudflare.com/workers-tcp-socket-api-connect-databases/
