# D1 Sessions API: Read-Your-Writes Consistency in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A user submits a form — creates a post, updates a profile, purchases an item — and the Worker
immediately redirects them to a detail page. The detail-page Worker reads from D1 and shows
stale data: the record is missing or still shows old values. The write succeeded, but D1's
read replicas haven't caught up yet.

This is the classic read-after-write (read-your-writes) consistency problem. In a globally
distributed edge runtime like Workers, every request may land on a different PoP and a
different D1 read replica. Without explicit coordination, reads and writes are handled by
different nodes and there is no guarantee the reader has seen the writer's changes.

## Context

D1 uses a primary-plus-read-replica architecture. Writes always go to the primary; reads are
served from the nearest replica. Replication lag is typically sub-second but never zero, and
under load or after failovers it can be several seconds.

Cloudflare addresses this with the **D1 Sessions API**. A session carries a *bookmark* — an
opaque cursor representing a replication position. When you pass a bookmark to a subsequent
query, D1 ensures that query executes on a replica that is at least as far ahead as the
bookmark. If no local replica qualifies, D1 routes the query to the primary or waits.

Bookmarks are serialised as strings and can be round-tripped through cookies, headers, or
Durable Objects.

## The Sessions API Surface

D1's binding exposes sessions via `env.DB.withSession(bookmark?)`:

```typescript
// wrangler.toml
// [[d1_databases]]
// binding = "DB"
// database_name = "myapp"
// database_id  = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

export interface Env {
  DB: D1Database;
}

// D1Database gains these methods in the Sessions API:
// env.DB.withSession(bookmark?: string): D1DatabaseSession
//
// D1DatabaseSession has:
//   .prepare(sql)   – same as D1Database.prepare
//   .batch([...])   – same as D1Database.batch
//   .exec(sql)      – same as D1Database.exec
//   .bookmark: string  – current replication position after last statement
```

`withSession()` without an argument creates a new session starting at `"first-unconstrained"`,
meaning any replica can serve the first query. After executing a statement, `.bookmark` reflects
the minimum replication position for subsequent reads to be consistent.

## Write Path: Capturing the Bookmark

The write Worker captures the bookmark after committing and stores it somewhere the next
read Worker can retrieve it.

```typescript
// workers/create-post.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{ title: string; content: string; authorId: string }>();

    // Open a session (no bookmark yet — write always goes to primary anyway)
    const session = env.DB.withSession();

    const result = await session
      .prepare(
        `INSERT INTO posts (id, title, content, author_id, created_at)
         VALUES (?, ?, ?, ?, unixepoch())
         RETURNING id`
      )
      .bind(crypto.randomUUID(), body.title, body.content, body.authorId)
      .first<{ id: string }>();

    if (!result) {
      return Response.json({ error: "insert failed" }, { status: 500 });
    }

    // Capture the bookmark AFTER the write
    const bookmark = session.bookmark;

    // Return bookmark to the client so the next request can use it
    return Response.json(
      { id: result.id },
      {
        status: 201,
        headers: {
          // Custom header — client must forward this on the next request
          "X-D1-Bookmark": bookmark,
        },
      }
    );
  },
};
```

## Read Path: Consuming the Bookmark

The read Worker accepts the bookmark from the incoming request and opens a session pinned
to that position.

```typescript
// workers/get-post.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const postId = url.pathname.split("/").pop();

    // Accept bookmark from client (header, cookie, or query param)
    const bookmark =
      request.headers.get("X-D1-Bookmark") ??
      parseCookie(request.headers.get("Cookie") ?? "")["d1_bookmark"] ??
      undefined; // undefined → any replica (no consistency guarantee)

    const session = env.DB.withSession(bookmark);

    const post = await session
      .prepare(
        `SELECT p.id, p.title, p.content, p.created_at,
                u.display_name AS author_name
         FROM   posts p
         JOIN   users u ON u.id = p.author_id
         WHERE  p.id = ?`
      )
      .bind(postId)
      .first();

    if (!post) {
      return Response.json({ error: "not found" }, { status: 404 });
    }

    // Propagate the advanced bookmark so the chain stays consistent
    return Response.json(post, {
      headers: { "X-D1-Bookmark": session.bookmark },
    });
  },
};

function parseCookie(raw: string): Record<string, string> {
  return Object.fromEntries(
    raw.split(";").map((pair) => {
      const [k, ...v] = pair.trim().split("=");
      return [k, decodeURIComponent(v.join("="))];
    })
  );
}
```

## Cookie-Based Bookmark Propagation (SPA / Server-Rendered)

For browser flows where JavaScript forwards headers automatically you can use cookies.
`HttpOnly; SameSite=Strict` prevents XSS exfiltration; `Max-Age` controls how long the
consistency window stays open (beyond which stale reads are acceptable).

```typescript
// Utility — build Set-Cookie header for D1 bookmark
function buildBookmarkCookie(bookmark: string, maxAgeSeconds = 30): string {
  return [
    `d1_bookmark=${encodeURIComponent(bookmark)}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Strict",
    `Max-Age=${maxAgeSeconds}`,
    // Omit Secure only in local dev; always add it in production
    "Secure",
  ].join("; ");
}

// In the write Worker response:
return new Response(JSON.stringify({ id: result.id }), {
  status: 201,
  headers: {
    "Content-Type": "application/json",
    "Set-Cookie": buildBookmarkCookie(session.bookmark),
  },
});
```

## Bookmark Forwarding via Durable Objects

When the write and read are in the same Worker but in separate requests within a Durable
Object, store the bookmark in the DO's in-memory state to avoid any latency from KV or
cookie round-trips.

```typescript
// durable-objects/user-session.ts
export class UserSessionDO implements DurableObject {
  private d1Bookmark?: string;

  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/write") {
      const { sql, params } = await request.json<{ sql: string; params: unknown[] }>();

      const session = this.env.DB.withSession(this.d1Bookmark);
      const result = await session.prepare(sql).bind(...params).run();

      // Advance the stored bookmark
      this.d1Bookmark = session.bookmark;

      return Response.json({ result, bookmark: this.d1Bookmark });
    }

    if (url.pathname === "/read") {
      // Always consistent with the last write this DO handled
      const session = this.env.DB.withSession(this.d1Bookmark);
      const rows = await session
        .prepare("SELECT * FROM posts WHERE author_id = ? ORDER BY created_at DESC LIMIT 20")
        .bind(url.searchParams.get("authorId"))
        .all();

      this.d1Bookmark = session.bookmark;
      return Response.json(rows.results);
    }

    return new Response("Not Found", { status: 404 });
  }
}
```

## Anti-patterns

**Always passing `"first-unconstrained"` as the bookmark.**
This is the default — it gives no consistency guarantee. Don't pass it explicitly as if it
helps. Omit the bookmark argument or pass `undefined` when you have no prior write.

**Storing bookmarks in D1 itself.**
You need a replication-safe store to propagate the bookmark; writing it to D1 and reading it
back creates a circular dependency. Use cookies, headers, KV (with short TTL), or Durable
Object memory.

**Holding sessions open across multiple HTTP requests.**
A `D1DatabaseSession` object is not serialisable. Create a new session per request and pass
only the bookmark string across the network boundary.

**Ignoring the advancing bookmark on read.**
Each `session.bookmark` after a read reflects the position of the replica that served that
read. Propagating this bookmark forward keeps the chain consistent across a multi-page flow.
Discarding it after the first read can re-introduce stale-read windows.

**Using sessions for all reads unconditionally.**
Sessions with bookmarks can incur extra latency when the nearest replica lags. Only use them
when the user actually performed a write in the recent flow. For read-heavy pages with no
preceding write, omit the bookmark for lowest latency.

## Gotchas

- **Bookmark format is opaque.** Do not parse, compare, or construct bookmarks manually.
  They may contain version prefixes or base64-encoded LSN data that is subject to change.

- **Bookmark expiry.** Very old bookmarks (hours to days) may no longer correspond to a
  valid replication position. D1 falls back to primary in that case, which is correct but
  slower. Set cookie `Max-Age` to a short window (15–60 seconds) to avoid accumulating
  stale bookmarks.

- **Session per statement vs. per request.** `withSession()` returns a session object you
  reuse for multiple statements within the same request. Each statement advances
  `session.bookmark`. Create one session at the start of the request handler, not one per
  statement.

- **Writes don't need a bookmark input.** Writes always route to the primary regardless of
  the session bookmark. The bookmark on the write session output is what matters.

- **No cross-database consistency.** A bookmark from database A cannot be used with
  database B's session. Each D1 database has an independent replication timeline.

## Verification

```typescript
// Integration test: assert read-your-writes within same Worker invocation
async function testReadYourWrites(env: Env): Promise<void> {
  const writeSession = env.DB.withSession();
  const id = crypto.randomUUID();

  await writeSession
    .prepare("INSERT INTO posts (id, title) VALUES (?, ?)")
    .bind(id, "consistency test")
    .run();

  const bookmark = writeSession.bookmark;
  console.assert(typeof bookmark === "string" && bookmark.length > 0, "bookmark must be non-empty");

  // Simulate a new request on a (potentially different) replica
  const readSession = env.DB.withSession(bookmark);
  const row = await readSession
    .prepare("SELECT id, title FROM posts WHERE id = ?")
    .bind(id)
    .first<{ id: string; title: string }>();

  console.assert(row !== null, "row must be visible after write with bookmark");
  console.assert(row?.title === "consistency test", "title must match");

  console.log("read-your-writes: OK", { bookmark, row });
}
```

## Related

- `d1-read-replicas-mobile-latency.md` — routing strategy and replica lag context
- `d1-savepoint-nested-transaction-workers.md` — transaction isolation within a single request
- `d1-advisory-lock-pattern-workers.md` — coordinating concurrent writes
- `d1-connection-pooling-workers.md` — session reuse across invocations
- `sqlite-production-wal-litestream-edge.md` — WAL replication concepts

## Sources

- Cloudflare D1 Sessions API documentation: https://developers.cloudflare.com/d1/worker-api/d1-database/#withsession
- Cloudflare D1 consistency model: https://developers.cloudflare.com/d1/reference/data-location/
- SQLite WAL and replication semantics: https://sqlite.org/wal.html
