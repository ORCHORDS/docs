# Chain of Responsibility Pattern Validation Pipeline

## Scope

This article covers the Chain of Responsibility pattern — GoF behavioral pattern where a request passes along a chain of handlers, each deciding to process it or pass it along — applied to request validation pipelines. The scope is the ordered sequence of checks an inbound payload traverses before reaching business logic: structural schema validation, semantic field rules, cross-field invariants, authorization and tenancy checks, and idempotency or duplication guards. The pattern is the right tool when validation concerns are numerous, independently authored, ordered by cost and dependency, and shared across endpoints; it is the wrong tool for a single endpoint with three fixed checks, where an explicit function composition is shorter and easier to read than a handler chain.

## Workflow or implementation guidance

Order the chain by three principles: fail on the cheapest signal first, validate before you authorize against expensive stores when possible, and never let a later handler depend on assumptions an earlier handler did not enforce. A production-viable order is: content-type and size guard, structural schema validation, type and range checks, semantic field rules, cross-field invariants, tenancy and ownership checks, rate or quota limits, and finally idempotency-key resolution. The size guard belongs first because rejecting a nine-megabyte body before parsing it is the difference between a fast 413 and a CPU-time outage.

Implement each handler with a uniform signature and a short-circuiting result type:

```ts
interface Validator {
  check(input: ValidatedRequest): Promise<ValidationResult | null>;
}

async function runChain(chain: Validator[], input: ValidatedRequest): Promise<ValidationResult> {
  for (const v of chain) {
    const failure = await v.check(input);
    if (failure) return failure; // first failure wins — do not keep poking a bad request
  }
  return { ok: true };
}
```

Two implementation disciplines matter. First, make each handler pure with respect to its decision: given the same request and the same external state, it returns the same verdict, which makes every failure reproducible in a test without standing up the entire chain. Second, collect structural errors in aggregate but short-circuit on the first semantic or authorization failure — clients need all their malformed fields at once, but exposing how far a forged request got through the chain is an information leak.

Compose chains per endpoint from named, reusable handlers rather than authoring one bespoke validator per route. When a handler needs configuration, pass it at composition time so the same handler class serves multiple endpoints with different thresholds. Log chain rejections with the handler identity and a stable internal error code, never with raw user input echoed back.

## Controls

Controls for this pattern are about ordering, coverage, and information discipline. Enforce chain composition through a declared, reviewable structure — a list of named handlers per route visible in one module — so ordering changes are diffs, not archaeology. Maintain an assertion, as a unit test, that no route omits the mandatory prefix of handlers (schema, tenancy); a route that accidentally drops its tenancy check is a security incident waiting for a scanner. Standardize the rejection payload contract: internal error code, safe user-facing message, and field pointers where applicable, with a lint rule that no handler invents its own response shape. Bound external calls per chain execution: a maximum of one or two store-backed checks per request, tracked in a counter, because validation chains quietly accrete database lookups until the "cheap" prefix costs more than the handler it guards. Redact or drop raw payloads from rejection logs — logs are an injection surface for downstream log-parsing systems.

## Validation evidence

Evidence for a validation chain is per-handler and whole-chain. Per handler: table-driven tests covering the accept boundary, the reject boundary just past it, and the malformed-input class the handler exists to catch, plus an explicit test that a `null`/absent field cannot crash the handler itself — validators are the first code to touch hostile input and the last place an uncaught exception is acceptable. Whole-chain: golden-path tests asserting the exact ordered verdicts for a fixture corpus of representative bad requests, so a reordering that silently weakens the chain fails a test by name. Coverage evidence: for each route, a mapping table of declared validation concerns to the handlers satisfying them, reviewed when routes are added. Fuzz evidence: run a short structured-fuzzing campaign against the chain entry point with generated malformed payloads and assert the invariant that no input produces an unhandled exception — only 4xx responses or explicit 5xx from declared downstream failures.

## Failure modes and correction

The most common failure is ordering drift: a new handler is appended at the end when it needed to run earlier, so expensive checks execute before cheap rejections and every malformed request costs a database round trip. Correct by encoding the canonical order as a fixture-tested constant and by timing assertions that a schema-invalid request never touches the store-backed handlers. The second failure is the do-everything handler, where cross-field, tenancy, and business rules merge into one thousand-line validator nobody can safely modify. Correct by splitting on concern boundaries; the chain exists precisely so concerns stay separate. A third is error-message leakage: detailed internal rejections ("tenant 412 does not own resource 88") that enumerate system internals to a hostile client. Correct with internal codes plus generic external text, and full detail in server-side logs only. A fourth is silent fall-through, where a handler returns `undefined` for a case it did not consider and the chain treats it as a pass. Correct by making the result type non-nullable — a handler must return an explicit verdict — and by treating unhandled input classes as rejects in strict environments.

## Limitations

A chain adds indirection, and for readers the cost is real: determining what validates a given field means walking the composition list rather than reading one function. Short-circuiting means clients see one error at a time for semantic failures, which is safer but slower for clients that needed several rounds of correction; batch APIs that must report all violations should aggregate outside the chain shape. Handlers that call external stores make the chain's latency profile dependent on those stores, and the pattern offers no built-in caching or circuit breaking — those must be composed in explicitly, which multiplies machinery. The pattern also does not express validation logic that is inherently order-dependent or stateful across requests (for example, sequencing rules), and forcing such rules into stateless handlers produces awkward workarounds.

## Canonical sources

- Gamma, Helm, Johnson, and Vlissides — Design Patterns: Elements of Reusable Object-Oriented Software, Addison-Wesley, 1994 (Chain of Responsibility, Behavioral Patterns catalog).
- Jakarta Bean Validation 3.0 specification (constraint declaration and validation ordering as a standardized pipeline): https://jakarta.ee/specifications/bean-validation/3.0/
- OWASP Cheat Sheet Series — Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
