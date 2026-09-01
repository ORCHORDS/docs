# Assign Global Request Id Correlation

When a request fails, the first question is always the same: which log
lines, traces, and downstream calls belong to this exact request? The
answer is a request identifier assigned at the edge, propagated through
every hop, attached to every log record, and echoed back to the client.
Without it, engineers grep timestamps and guess. With it, one pasted
identifier reconstructs the entire path of a request across the worker,
the API, the queue, and the database. The pattern is small — generate
once, propagate always, log everywhere — but it has to be implemented
consistently or it silently stops at the first process boundary.

## Scope

Assigning and propagating request identifiers for HTTP services and
workers: where to generate the ID, which headers to honor, how to
propagate across service boundaries and async tasks, how to attach the
ID to structured logs, and how to verify correlation end to end. Covers
the plain `x-request-id` convention and the standardized W3C Trace
Context `traceparent` header. Not covered: full tracing backend
operation or sampling strategy design.

## Workflow or implementation guidance

1. **Assign at the outermost edge.** The first component that touches a
   request — the CDN, edge worker, API gateway, or application
   middleware — generates the identifier if the incoming request does
   not already carry a trusted one. A UUID v4 or a ULID is appropriate:
   both are globally unique without coordination; ULIDs sort by time,
   which makes log aggregation friendlier.
2. **Honor inbound IDs only from trusted tiers.** Accept an incoming
   `x-request-id` from your own edge or known internal callers, and
   regenerate for anything else. Passing through arbitrary client
   supplied identifiers invites log injection and poisoned correlation:
   sanitize to an allowed character set and length, or overwrite.
3. **Echo the identifier in the response.** Return the ID in the
   `x-request-id` response header. Support tickets and bug reports then
   arrive pre-loaded with the exact key needed to find the logs, which
   halves time-to-diagnosis for customer-reported issues.
4. **Propagate on every outbound call.** A request-scoped HTTP client
   wrapper stamps the current ID onto `x-request-id` for hop-to-hop
   correlation, and onto `traceparent` when downstream systems
   participate in W3C Trace Context. The rule in review is simple: no
   `fetch` or database call leaves this process without the current
   identifiers attached.
5. **Bridge into async work.** Queue producers attach the request ID to
   the message payload or metadata, and consumers restore it into their
   logging context before doing work. A trace that dies at the queue
   boundary is the most common failure of this pattern; treat the
   consumer's first statement as "rehydrate correlation context".
6. **Put the ID in every structured log line.** Use one logger
   configured with an async context store (AsyncLocalStorage in Node,
   the request context in Workers runtimes, task-local equivalents
   elsewhere) so application code logs normally and the ID is attached
   by the framework, not by developers copy-pasting a variable into
   every call.

## Controls

- **Single generation point.** Exactly one component per request path
   is allowed to mint an ID; everything downstream either propagates or
   nests a parent-child relationship. Two generators on one path
   produces split traces.
- **Header contract.** Document `x-request-id` (opaque correlation) and
   `traceparent` (standards-compliant trace context) in the API
   specification, including case, allowed length, and character set, so
   clients and middleware implement the same thing.
- **Log field name.** Standardize one JSON field name such as
  `request_id` across services; mixed `requestId`, `req-id`, and
  `x_request_id` fields defeat log search across teams.
- **Retention note.** The identifier itself carries no user data, which
   keeps it safe to persist; the same cannot be said for headers people
   smuggle alongside it, so limit what is copied from inbound headers
   into logs.

## Validation evidence

End-to-end correlation is testable in a single script:

1. `curl -i` the service and confirm the response carries
   `x-request-id`, and that the value matches the `request_id` field of
   the log line emitted for that request (search the log stream for the
   returned value; exactly one root request line should appear).
2. Call the service with a crafted inbound `x-request-id` from an
   untrusted source; a correct implementation logs a freshly generated
   ID, not the crafted one.
3. Trigger a request that fans out to a downstream service and a queue
   consumer; grep the downstream service logs and the consumer logs for
   the root ID. All three log sets returning hits is the pass
   condition.
4. Verify propagation is bidirectional where supported: parse the
   `traceparent` your edge emits and confirm downstream spans share the
   same trace identifier in the tracing UI.
5. In CI, run an integration test that asserts the response header
   exists, matches the allowed format, and equals the logged ID — this
   is the guard that survives refactors of the middleware.

## Failure modes and correction

- **IDs stop at the first internal call.** A hand-rolled HTTP call
   bypassed the request-scoped client. Centralize outbound HTTP in one
   wrapper and lint for bare `fetch`/`axios` imports in application
   code.
- **Two IDs for one request.** An inner tier regenerated because it did
   not trust the header. Fix the trust list, and log both the accepted
   inbound and generated outbound IDs during the transition to find
   which tier is minting duplicates.
- **Log injection via the header.** Newlines or control characters in a
   client-supplied ID corrupt log files or spoof entries. Validate
   against a strict pattern before use, and reject or regenerate on
   mismatch.
- **Context lost after an await boundary.** Async context stores are
   lost when work escapes the tracked promise chain (timers, custom
   thread pools, some SDK callbacks). Wrap the escape point explicitly
   to capture and restore the store.
- **Correlation works locally but not in production.** A load balancer
   or platform middleware strips unknown hop-by-hop headers; verify the
   header survives each tier with a per-tier echo endpoint before
   blaming application code.

## Limitations

- A plain request ID correlates but does not encode causality; parent
   and child spans, sampling decisions, and cross-service timing need
   real trace context tooling.
- Long-lived background jobs outlive the request; keeping the original
   request ID is useful for diagnosis but misrepresents the job as one
   request, so record both a job ID and the originating request ID.
- Browser restrictions and third-party clients cannot be forced to
   return or forward the header; treat client participation as a
   best-effort optimization.

## Canonical sources

- W3C, Trace Context specification (traceparent header): https://www.w3.org/TR/trace-context/
- OpenTelemetry, Tracing API concepts: https://opentelemetry.io/docs/specs/otel/trace/api/
- IETF, HTTP Semantics (RFC 9110, header handling): https://www.rfc-editor.org/rfc/rfc9110.html
