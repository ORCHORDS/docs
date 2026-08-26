# Cloudflare Storage Primitive Selection: KV vs D1 vs R2 vs Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You are building on Cloudflare Workers and you need to persist something. The
Cloudflare docs list KV, D1, R2, Durable Objects, Hyperdrive, Vectorize, and Workers
Analytics Engine as storage options. Each has a different consistency model, latency
profile, pricing structure, and appropriate use case. Picking the wrong one creates
architectural debt that is painful to undo: migrating data between Cloudflare storage
primitives is not trivial.

This article is a decision guide for startup-scale Cloudflare Workers projects.

---

## Context

Cloudflare's storage primitives are not interchangeable. Each one reflects a
deliberate trade-off in the distributed systems design space:

| Primitive | Consistency | Primary key | Query capability | Best for |
|---|---|---|---|---|
| KV | Eventually consistent | String key | Key lookup only | Config, caching, session tokens |
| D1 | Strongly consistent | SQL (rowid) | Full SQL | Relational data, user records |
| R2 | Strongly consistent | Object key | Prefix list + metadata | Blobs, files, exports |
| Durable Objects | Strongly consistent | DO ID | Key-value (Transactional Storage API) | Real-time coordination, unique entity state |
| Vectorize | Eventually consistent | Vector ID | ANN similarity search | Embeddings, semantic search |
| Analytics Engine | Append-only | Event blobs | SQL via API | Event telemetry, metrics |
| Hyperdrive | (passthrough) | (your DB) | (your DB's SQL) | Connecting to external Postgres |

The right choice depends on: consistency requirements, query shape, data volume,
latency sensitivity, and whether the data is operational or analytical.

---

## Section 1 — KV: When and When Not

**Use KV when:**
- You need fast global reads with low latency on the critical path
- Data changes infrequently (hourly or less)
- You only ever retrieve by a single known key
- You are caching the output of a more expensive computation

**Canonical use cases:**
- Feature flags (read on every request, updated rarely)
- Rate limit state (but prefer the Workers Rate Limiting binding instead)
- Session tokens (write on login, read on every request, delete on logout)
- A/B test configuration (updated by a deploy or a manual trigger)
- CDN purge lists

**Do not use KV when:**
- You need to query by anything other than a known key
- You need a list of all keys matching a pattern at query time (KV list is slow and
  not suitable for frequent use)
- Your data changes faster than once per second per key (eventual consistency will
  cause stale reads at some edge locations for 60+ seconds)
- You need transactional writes across multiple keys

**KV limits (as of 2026):**
- Value size: 25 MB max
- Key size: 512 bytes max
- Writes propagate globally in ~60 seconds (not instantaneous)
- Free tier: 100k reads/day, 1k writes/day
- Paid: $0.50 per million reads, $5 per million writes

**Pricing note:** KV is expensive on writes at scale. If you are writing frequently
(e.g., updating a counter per request), use Durable Objects instead.

---

## Section 2 — D1: When and When Not

**Use D1 when:**
- You need relational data with joins, ordering, and filtering
- You need ACID transactions
- Your data has a schema that evolves over time (migrations)
- You are building CRUD applications (users, posts, orders, settings)

**Canonical use cases:**
- User accounts and profile data
- Application settings and configuration with complex query patterns
- Orders, subscriptions, and billing records
- Audit logs (with `INSERT INTO` only, never `UPDATE` or `DELETE`)
- Any data you would previously have put in PostgreSQL or SQLite

**D1 is SQLite at the edge.** This means:
- No stored procedures
- No full outer joins (use two left joins instead)
- No ENUM type (use a CHECK constraint)
- No `NOW()` at the database level (pass the timestamp from the Worker)
- Full-text search via FTS5 extension (built in, useful for basic search)

**Do not use D1 when:**
- You need write throughput >100 writes/second per database (D1 is a single-writer
  architecture; read replicas are available but writes go to one region)
- You have large blobs (images, PDFs, videos) — store those in R2, reference in D1
- You need real-time collaborative editing where two users may write the same row
  simultaneously — use Durable Objects for the coordination layer

**D1 limits (as of 2026):**
- Database size: 10 GB
- Max connections: 1 per Worker invocation (no persistent pools)
- Free tier: 5 GB storage, 25 million reads/day, 50k writes/day
- Paid: storage $0.75/GB/month, reads $0.001 per million, writes $1.00 per million

---

## Section 3 — R2: When and When Not

**Use R2 when:**
- You need to store files, blobs, or large objects
- You need to serve those objects to users (via a public R2 bucket or a Worker that
  streams from R2)
- You generate exports, reports, or archives
- You need S3-compatible storage (R2 is compatible with the S3 API)

**Canonical use cases:**
- User-uploaded files (images, documents, videos)
- Build artifacts and release bundles
- Backup archives from D1 or other data stores
- PDF exports generated server-side
- Logs and audit trails exported from Workers via Logpush
- Model weights or large assets for AI inference pipelines

**Do not use R2 when:**
- You need sub-millisecond random access to structured data — use D1 or KV
- You need to query the content of stored files — R2 is key-based, content is opaque

**R2 limits (as of 2026):**
- Object size: 5 TB
- Free tier: 10 GB storage, 1 million Class A operations/month (writes),
  10 million Class B operations/month (reads), free egress
- Paid: $0.015/GB/month storage, $4.50 per million Class A ops

**Egress is free from R2 to the internet**, which is the primary cost advantage over
S3. At scale, egress fees on S3 are significant; R2 eliminates them.

---

## Section 4 — Durable Objects: When and When Not

**Use Durable Objects when:**
- You need strongly consistent, real-time coordination across multiple Worker instances
- You are implementing entity state that must be serialised (e.g., "only one person
  can edit this record at a time")
- You need WebSocket connections with shared state (a chat room, a collaborative
  document, a game session)
- You need a distributed counter that increments accurately (not "eventually")
- You need a unique entity that runs actor-model logic

**Canonical use cases:**
- Chat room state (one DO per room, handles all connections to that room)
- Rate limiter per user (one DO per user ID, increments atomically)
- Distributed lock (DO as a mutex)
- Live collaboration (one DO per document)
- Shopping cart (one DO per session, ensures no race conditions on concurrent adds)

**Do not use Durable Objects when:**
- Your data is read-mostly with occasional writes — KV or D1 is simpler
- You need to query across many entities (you cannot query "all DOs that match X")
- Your data is relational — D1 is much easier to query

**Durable Objects pricing (as of 2026):**
- $0.15 per million requests
- $12.50 per million GB-seconds of compute
- Storage: $0.20/GB/month (Transactional Storage API)

Durable Objects incur compute cost even for idle time if the DO is active. Design your
DOs to hibernate (`ctx.waitUntil()` and auto-hibernation) when idle.

---

## Section 5 — Decision Tree

```
Do you need to store a blob or file?
  YES → R2

Do you need real-time coordination or a WebSocket endpoint?
  YES → Durable Objects

Do you need to query by anything other than a single key?
  YES → D1

Does the data change less than once per minute AND is it read on the hot path?
  YES → KV (cache / config)

Otherwise?
  → D1 (default relational store)
```

---

## Section 6 — Common Combinations

**User-uploaded images:**
- Store metadata (filename, size, content type, user ID, upload timestamp) in D1
- Store the blob itself in R2
- Return a signed R2 URL (or serve via a Worker) for display

**Feature flags:**
- Store flag definitions in D1 (authoritative, queryable by admin)
- Cache active flag values in KV (fast read on every request, TTL 60 seconds)
- Bust the KV cache when a flag is updated in D1

**Real-time multiplayer:**
- Durable Object per game/document/room for coordination
- D1 for persistent game state (save at end of session)
- R2 for recordings or replays

**Audit log:**
- Write-only inserts to D1 with a compound index on (entity_id, created_at)
- Export to R2 via a Cron Worker daily for long-term retention

---

## Anti-patterns

- **Using KV as a database.** KV has no query capability. Storing JSON blobs in KV
  and filtering them in the Worker is inefficient and breaks at scale. Use D1.
- **Using D1 to store blobs.** SQLite stores BLOBs but D1 is not optimised for large
  binary data. Queries on a D1 table with large BLOB columns are slow. Use R2 for
  files, store only a reference URL in D1.
- **Not setting a TTL on KV entries used as a cache.** Without a TTL, cache entries
  accumulate indefinitely. Set `expirationTtl` on every `kv.put()` that is used as a
  cache layer.
- **Creating a Durable Object per request.** DOs are for long-lived entity state.
  Creating a new DO for each HTTP request defeats the purpose and incurs unnecessary
  cost. DOs should represent entities that persist over time (a user, a room, a
  document).
- **Storing secrets in KV, D1, or R2.** None of these is a secrets manager. Use
  `wrangler secret put` for secrets at rest. References to stored credentials in
  storage primitives are a SIEM alert waiting to happen.

---

## Gotchas

- **D1 read replicas do not guarantee strong consistency.** In 2025/2026 D1 introduced
  read replicas for lower-latency reads. Reads from a replica may lag behind the
  primary by milliseconds. Do not use a replica for reads that must reflect a just-
  completed write (e.g., "read after write" in the same request chain). Read from the
  primary for those cases.
- **KV is eventually consistent even within the same region.** A write to KV is not
  immediately visible to a concurrent read in the same data centre. Design around this:
  never write to KV and immediately read it back expecting the new value.
- **Durable Object storage is not a replacement for R2 for large data.** DO storage
  (Transactional Storage API) has a 128 KB per-value limit by default. Use R2 for
  anything larger.
- **R2 has no built-in CDN caching.** To cache R2 objects at the edge, serve them
  through a Worker that sets `Cache-Control` headers or uses the Workers Cache API.
  A direct `r2.publicUrl()` domain has caching, but a Worker-served R2 response does
  not unless you explicitly cache it.
- **D1 migrations are irreversible if you use `DROP` statements.** Always write
  backward-compatible migrations. Add columns, never drop them in the first migration.
  Drop in a second migration after the column has been absent from application code for
  a full release cycle.

---

## Verification

When choosing a storage primitive for a new feature, answer these questions first:

- [ ] What is the access pattern? (Key lookup, range query, full SQL, blob retrieval)
- [ ] What is the consistency requirement? (Eventual vs strong)
- [ ] What is the data volume (rows, object count, total bytes)?
- [ ] What is the write frequency per second?
- [ ] Is this operational data (low latency reads) or analytical data (batch reads)?
- [ ] What is the cost at 10x current scale?
- [ ] Does the chosen primitive have a migration path if requirements change?

Document the decision in an ADR.

---

## Related

- `build-vs-buy-cloudflare-adjacent-tooling.md`
- `developer-experience-dx-cloudflare-workers.md`
- `migrations-must-be-backward-compatible.md`
- `cache-invalidation-is-harder-than-caching.md`
- `never-store-secrets-in-env-files.md`
- `data-layer-must-survive-app-failure-2026.md`

---

## Sources

- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare R2: https://developers.cloudflare.com/r2/
- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare storage pricing: https://developers.cloudflare.com/workers/platform/pricing/
