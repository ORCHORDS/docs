# Workers TCP Socket (connect() API) for Database Proxy Use Cases

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a Cloudflare Worker to open a raw TCP connection to a PostgreSQL-compatible database (self-hosted, AlloyDB, CockroachDB, etc.) for a health-check endpoint, a lightweight query proxy, or a database introspection API. The HTTP-only Worker runtime historically blocked raw socket connections, leaving teams to route through HTTP tunnels or external proxies. The `cloudflare:sockets` module removes this constraint but requires understanding its security model before connecting to production databases.

## Context

Cloudflare added the `cloudflare:sockets` module (runtime API `connect()`) to the Workers runtime to enable raw TCP connections from Worker code. Connections are only permitted to hosts that are reachable from Cloudflare's network and that are explicitly allowed — publicly routable IPs or private networks exposed via Cloudflare Tunnel. For database workloads at scale, **Hyperdrive** (Cloudflare's connection-pooling proxy) is the recommended path because it maintains a pool of pre-authenticated connections globally and avoids the cold-start overhead of a full TLS + PostgreSQL handshake on every Worker invocation. Direct `connect()` is better suited for: lightweight health probes, admin tooling that runs rarely, or protocols that Hyperdrive does not yet support.

## Using the cloudflare:sockets Module

```typescript
// src/tcp-proxy-worker.ts
import { connect } from "cloudflare:sockets";

export interface Env {
  // Hyperdrive binding (preferred for query workloads)
  HYPERDRIVE: Hyperdrive;
  // Direct host override for health-check use case
  DB_HOST: string;  // e.g. "db.internal.example.com"
  DB_PORT: string;  // e.g. "5432"
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/healthz/db") {
      return checkPostgresHealth(env.DB_HOST, parseInt(env.DB_PORT, 10));
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Minimal PostgreSQL Wire Protocol Handshake for Health Checks

```typescript
// Implements just enough of the PG wire protocol to confirm the
// database is accepting connections — no query is executed.
async function checkPostgresHealth(host: string, port: number): Promise<Response> {
  const socket = connect({ hostname: host, port }, { secureTransport: "starttls" });
  const writer = socket.writable.getWriter();
  const reader = socket.readable.getReader();

  try {
    // Startup message: length (4 bytes) + protocol 3.0 (4 bytes) + params
    const user = "health_checker";
    const database = "postgres";
    const params = `user\0${user}\0database\0${database}\0\0`;
    const paramBytes = new TextEncoder().encode(params);
    const msgLen = 4 + 4 + paramBytes.byteLength; // length int + protocol int + params

    const buf = new ArrayBuffer(msgLen);
    const view = new DataView(buf);
    view.setInt32(0, msgLen, false);       // message length (big-endian)
    view.setInt32(4, 196608, false);       // protocol version 3.0 = 0x00030000

    const msg = new Uint8Array(buf);
    const full = new Uint8Array(msgLen);
    full.set(msg, 0);
    full.set(paramBytes, 8);

    await writer.write(full);

    // Read the first byte of the server response
    // 'R' (0x52) = AuthenticationRequest  → server is alive
    // 'E' (0x45) = ErrorResponse           → server up but access denied (still alive)
    const { value } = await Promise.race([
      reader.read(),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("TCP health check timed out")), 3000)
      ),
    ]);

    const firstByte = value ? String.fromCharCode(value[0]) : null;
    const alive = firstByte === "R" || firstByte === "E";

    return Response.json({
      status: alive ? "healthy" : "unreachable",
      responseCode: firstByte,
    }, { status: alive ? 200 : 503 });
  } catch (err) {
    return Response.json(
      { status: "unhealthy", error: (err as Error).message },
      { status: 503 }
    );
  } finally {
    writer.releaseLock();
    reader.releaseLock();
    await socket.close();
  }
}
```

## Security Considerations and Allowlisted Hosts

```toml
# wrangler.toml
name = "db-proxy-worker"
main = "src/tcp-proxy-worker.ts"
compatibility_date = "2026-06-01"

# Direct TCP access — restrict to specific hosts only
# Workers can only connect to publicly reachable IPs or hosts
# exposed via Cloudflare Tunnel. Private RFC-1918 addresses
# require a Cloudflare Tunnel in front of the database.

[vars]
DB_HOST = "db-tunnel.example.com"  # Cloudflare Tunnel public hostname
DB_PORT = "5432"

# For query workloads use Hyperdrive (connection pooling)
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "<your-hyperdrive-config-id>"
```

## Connecting via Hyperdrive for Query Workloads

```typescript
// src/hyperdrive-query-worker.ts
// Use Hyperdrive instead of raw connect() for any query that
// needs connection pooling and low-latency re-use.
import { Client } from "pg";  // npm i pg

export interface Env {
  HYPERDRIVE: Hyperdrive;
}

export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    // Hyperdrive exposes a standard postgres:// connection string
    // pointing to Cloudflare's regional pooler — not your DB directly.
    const client = new Client({ connectionString: env.HYPERDRIVE.connectionString });
    await client.connect();

    try {
      const result = await client.query("SELECT NOW() AS ts");
      return Response.json({ time: result.rows[0].ts });
    } finally {
      await client.end();
    }
  },
};
```

## connect() vs Hyperdrive Comparison

| Dimension | `connect()` direct | Hyperdrive |
|---|---|---|
| Connection pooling | None — new TCP+TLS+PG handshake per invocation | Global pool; pre-authenticated |
| Cold start overhead | High (50–200 ms handshake) | Low (reuses existing connection) |
| Supported protocols | Any TCP protocol | PostgreSQL wire protocol only |
| Use case | Health probes, non-PG protocols, admin tooling | Production query workloads |
| Max concurrent connections | Limited by Worker concurrency | Managed by Hyperdrive pooler |
| Private network access | Via Cloudflare Tunnel | Via Hyperdrive config (built-in) |

## Anti-patterns

- **Using raw `connect()` for high-frequency queries** — each Worker invocation performs a full TCP+TLS+PG handshake; at scale this exhausts database `max_connections` within seconds; use Hyperdrive instead.
- **Hard-coding database credentials in `[vars]`** — vars are plaintext in `wrangler.toml` and visible in the dashboard; store passwords via `wrangler secret put`.
- **Connecting to RFC-1918 addresses directly** — Workers cannot reach `10.x.x.x` or `192.168.x.x` without a Cloudflare Tunnel; the connection silently fails or is blocked.
- **Not closing the socket in a `finally` block** — unclosed sockets leak resources within the Worker isolate and can cause connection exhaustion on the database side.

## Gotchas

- `cloudflare:sockets` is only available in the Workers runtime; it cannot be polyfilled locally with `wrangler dev` without the `--remote` flag.
- The `secureTransport` option in `connect()` accepts `"off"`, `"on"`, or `"starttls"`; most PostgreSQL servers require `"starttls"` (upgrading from plain TCP to TLS via `SSLRequest`).
- Workers have a default outbound TCP connection timeout; if the database host is geographically distant, set `socket.startTls()` immediately after the connection opens to avoid timeouts during the TLS negotiation phase.
- Hyperdrive requires you to create a config object (`wrangler hyperdrive create`) that stores the database URL — the `id` in `wrangler.toml` is the config ID, not a connection string.
- `pg` npm package must be imported via a bundler (esbuild via wrangler) as it uses Node.js built-ins; ensure `nodejs_compat` compatibility flag is enabled when using Node-built npm packages.

## Verification

```bash
# Enable nodejs_compat for the pg package
# Add to wrangler.toml:
# compatibility_flags = ["nodejs_compat"]

# Deploy and test health check endpoint
wrangler deploy
curl -si https://db-proxy-worker.example.workers.dev/healthz/db | jq .

# Verify Hyperdrive connection string is injected
wrangler dev --remote
curl http://localhost:8787/

# Create a Hyperdrive config for a PostgreSQL database
wrangler hyperdrive create my-db-config \
  --connection-string "postgresql://user:pass@db.example.com:5432/mydb"

# List Hyperdrive configs
wrangler hyperdrive list
```

## Related

- `d1-export-import-r2-archival-pipeline.md`
- `workers-for-platforms-tenant-custom-domains.md`

## Sources

- cloudflare:sockets module — https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- Hyperdrive documentation — https://developers.cloudflare.com/hyperdrive/
- PostgreSQL wire protocol reference — https://www.postgresql.org/docs/current/protocol.html
- Workers compatibility flags — https://developers.cloudflare.com/workers/configuration/compatibility-dates/
