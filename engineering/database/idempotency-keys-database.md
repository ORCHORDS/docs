# idempotency-keys-database

**Issue:** Networks retry: mobile clients time out and resend, SDKs retry POSTs automatically with backoff, and users double-click submit. Any endpoint with side effects (create order, send payment, issue refund) will eventually be executed twice with identical intent unless the server can recognize "I've seen this exact request before". The industry-standard answer, popularized by Stripe, is a client-generated idempotency key stored server-side: the first request executes and records its outcome under the key; retries look up the key and replay the stored outcome instead of re-executing. Getting the storage layer right is a database design problem — the key table is the single point of correctness for the whole scheme, and a naive implementation still double-charges under concurrency or leaks request bodies into logs.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The canonical table shape

1. **Key, scope, and uniqueness.** A table like `idempotency_keys (scope text, key text, request_hash text, status text, response_code int, response_body jsonb, locked_at timestamptz, created_at timestamptz)` with a unique constraint on `(scope, key)`. Scoping matters: Stripe scopes keys per account and per request type, so the same UUID used for a payment and for a refund don't collide; encode the endpoint or operation in the scope.
2. **`request_hash` catches key reuse with a different payload.** Hash the normalized request body into `request_hash`; on a retry whose hash doesn't match the stored one, return a 422 `idempotency_error` instead of silently executing different work under the same key — this is exactly Stripe's documented behavior and it converts a silent correctness bug into a loud client bug.
3. **Status machine: `processing` → `completed` / `failed`.** Insert the row as `processing` before executing; concurrent duplicates that lose the insert race (unique violation) read the row, and if it is `completed` they return the stored response; if it is still `processing` they poll briefly or return 409-style "request in progress" rather than executing in parallel.
4. **Retention with an expiry.** Stripe stores results for 24 hours; pick an explicit window (24 hours to 30 days depending on how stale clients can retry), index `created_at`, and purge with a scheduled job so the table doesn't grow forever — old keys expire and the same key may legally start a new request afterward.

## The concurrency mechanics (where naive versions fail)

1. **The unique constraint is the mutex.** The correct flow is: `INSERT` the key row first; on unique-violation, fall through to the read path. Checking with a `SELECT` before inserting is a check-then-set race that double-executes under concurrency — the database constraint, not application logic, is what makes the pattern safe.
2. **Execute inside or immediately after the insert transaction, deliberately.** Inserting as `processing`, committing, then executing, then updating to `completed` survives handler crashes (stale `processing` rows can be reclaimed after a timeout) but needs reaper logic. Wrapping insert + business write in one transaction is simpler and atomic, but a retry arriving mid-transaction will see no row and must wait on the constraint — either way, handle the in-flight case explicitly.
3. **Reclaim stuck `processing` rows.** A crash between insert and completion leaves rows stuck; store `locked_at` and treat rows older than a threshold (e.g. 5 minutes) as failed, either returning "original request failed, use a new key" or allowing takeover with an atomic conditional update (`UPDATE ... WHERE status = 'processing' AND locked_at < now() - interval '5 minutes'`).
4. **Beware retry storms on hot keys.** A widely shared key (buggy shared constant) serializes all traffic through one row and fails everyone after the first; alert on high collision counts per key, which is a client bug signal, not a server load problem.

## Operational and security concerns

1. **Never log response bodies blindly.** `response_body` exists so retries get identical answers, which means it can contain PII or payment data; encrypt at rest if sensitive, exclude from general query logs and error reporters, and project only what the client needs.
2. **Treat the table as write-hot, keep it lean.** Every mutating request costs an insert and an update here; avoid wide columns, keep the response body truncated to what replay requires, and consider partitioning or aggressive vacuum tuning like any other high-churn table (same MVCC rules as a queue table).
3. **Keys are client-generated; validate them.** Require a minimum length and entropy (a UUID is good; `\"1\"` or a timestamp is not), cap length, and never accept keys containing user-controlled data you wouldn't store raw.
4. **Make retry behavior observable.** Instrument the three outcomes — first execution, replayed response, rejected (hash mismatch / in-progress / expired) — per endpoint; the replay rate is your visibility into how often clients actually retry, and hash-mismatch spikes pinpoint client bugs.
5. **Apply the same pattern to internal calls.** Service-to-service retries (queue handlers, webhook deliveries, cron steps) need the same key discipline via a deterministic key (source event id + step name); a `UNIQUE` constraint on `(source_event_id, step)` gives exactly-once side effects per event without distributed transactions.

## When the pattern is overkill

1. **Natural idempotency already present.** Endpoints keyed by upsert semantics (`INSERT ... ON CONFLICT DO NOTHING` on a business natural key, like "one subscription per user per plan") are already idempotent; layering a key table adds complexity without changing outcomes.
2. **Read-only or purely derived endpoints.** GETs and cached computations don't need keys; use request de-duplication at the cache layer instead.
3. **Very low-stakes writes.** An analytics event or a log line duplicated is harmless; reserve the machinery for requests where a duplicate means money, access, or communication.
