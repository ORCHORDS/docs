# Facade Pattern Public API Stabilization

## Scope

This article covers the Facade pattern — GoF structural pattern providing a unified, higher-level interface to a subsystem — used to stabilize a public API surface while the implementation beneath it changes. Scope includes the facade as the versioned external contract, request routing and aggregation behind it, deprecation and compatibility management, and the discipline of hiding subsystem churn. It excludes API gateway products (infrastructure-level routing, auth offload) except where a gateway enforces facade decisions, and excludes the Backend-for-Frontend shape, which optimizes per client type rather than stabilizing one contract.

## Workflow or implementation guidance

Design the facade from the client's jobs, not from the subsystem's capabilities. Enumerate what external callers need to accomplish, name endpoints in their vocabulary, and then map each endpoint onto the subsystem operations that implement it — the mapping is allowed to be ugly; the facade's whole purpose is to absorb that ugliness so the public surface stays clean. Where one client job requires three internal calls, the facade composes them; where internal models split differently than clients think, the facade reshapes them.

Establish the contract boundary as versioned and explicit. The facade's request and response schemas are the product; everything behind them is implementation detail you may refactor freely within a version. Encode that distinction structurally:

```ts
interface PublicOrder {        // v1 contract — changes require a version bump
  id: string;
  placedAt: string;
  total: { amount: string; currency: string };
}

function toPublicOrder(internal: OrderRecord): PublicOrder {
  // reshapes, renames, hides — the only place internal shapes leak toward the public
}
```

Manage change through a deprecation discipline rather than breakage. Additive changes — new optional fields, new endpoints — ship within a version. Anything else requires a new version path alongside the old, a migration guide, a sunset date communicated through response headers (`Deprecation`, `Sunset`), and usage telemetry per client on the deprecated surface so the sunset is enforced against data, not hope. The facade is also the right place to keep response shapes stable against internal pagination, error, and envelope conventions: internal error taxonomies never leak as-is; they map to documented public error codes with safe messages.

Keep the facade thin in logic but complete in translation. Business decisions do not belong here — a facade that starts owning workflow becomes a second service with two contracts to break. But translation must be total: every subsystem response the facade returns has been validated against the public schema before serialization, because an internal field rename that slips through unvalidated becomes a breaking change shipped without a version bump — the exact failure the pattern exists to prevent.

## Controls

Enforce the contract with schema validation on egress, not only ingress: responses are validated against the published public schema before leaving the facade, and a mismatch fails loudly in staging and is counted and alerted on in production — this is the mechanical guarantee that internal refactorings cannot silently change the public surface. Maintain a compatibility test suite that pins the exact serialized shape of representative responses per version, run on every deploy, so any egress change is a reviewed diff. Track per-client usage of every endpoint and field (field-level telemetry via sampled response schemas) — deprecation decisions without field-level usage data are guesses about other people's code. Require a written compatibility policy: what counts as additive, what requires a new version, minimum notice periods, and maximum number of concurrent supported versions (two is a common ceiling, because supporting three versions forever is a real cost with no natural terminator). Review gateway configuration and facade code as one unit when routing changes, so an infrastructure-level rewrite cannot bypass facade translation.

## Validation evidence

The core evidence artifact is the contract snapshot suite: recorded request/response pairs per public endpoint and version, replayed against every deploy, with byte-level comparison of serialized shapes modulo documented dynamic fields. Its green run is the proof that the stabilization promise held through that change. Compatibility evidence for schema evolution: run the previous version's snapshot suite alongside the new version's on every deploy of a migration, so both contracts are continuously verified while they coexist. Negative evidence: inject an internal model change (rename a field on the internal record in a test build) and assert the egress validator fails — proving the guardrail detects the class of error it exists for, rather than assuming it. Deprecation evidence: per-client usage curves for the deprecated surface with a documented sunset enforcement decision at the threshold, plus evidence that `Deprecation` and `Sunset` headers actually appear on responses (a header promised in docs but absent in responses is a common silent failure). Load evidence: facade aggregation paths (one public call fanning into several subsystem calls) measured under production-shaped concurrency, because facades shift fan-out cost from clients to your service and the resulting latency profile must be known, not discovered.

## Failure modes and correction

The dominant failure is the leaky facade: an internal field name, error code, or pagination envelope escapes through a response, clients depend on it, and a later internal refactor breaks them — with no version bump having happened. Correct with mandatory egress schema validation and the contract snapshot suite; both exist to make leakage a deploy-time failure. The second is facade logic creep: orchestration, business rules, and state accumulate until the facade is a service with two contracts and double the change surface. Correct by pushing decisions into the subsystem behind it and restricting the facade to translation, composition, and contract enforcement. A third is version sprawl: soft-hearted retention of v1 alongside v2 and v3 indefinitely, each new feature implemented two or three times. Correct with the supported-version ceiling and sunset enforcement tied to usage telemetry. A fourth is undocumented breaking change via serialization defaults: a new optional internal field flows through to JSON because nothing strips unknown fields, technically additive but observed by strict clients as a contract change. Correct with explicit allowlist-based field projection in the translation layer. A fifth is aggregation coupling: a facade endpoint composing three subsystem calls inherits the worst availability and latency of the three, and public reliability degrades as internal topology grows. Correct with per-dependency timeouts, cached fallbacks where business semantics allow, and by measuring the fan-out cost per endpoint.

## Limitations

A facade stabilizes the interface contract, not the semantics beneath it: if the subsystem's behavior changes — ordering guarantees, consistency windows, idempotency rules — the facade's unchanged shapes will carry changed meanings, and clients break anyway in ways schema validation cannot detect. The pattern concentrates translation and aggregation work in one component, which becomes a latency and availability chokepoint proportional to how much it composes. Supporting old versions is genuine engineering cost with no expiry unless enforced, and the discipline required to sunset is organizational, not technical. Field-level usage telemetry needed for safe deprecation has privacy and storage costs of its own, and incomplete telemetry (sampling gaps, unidentified clients) understates dependence precisely on the rarely-used endpoints most likely to be cut. Finally, a facade cannot paper over fundamental model mismatch: if internal and public models diverge structurally, every translation becomes a lossy mapping with edge cases, and the honest fix is a dedicated backend-for-frontend or a redefinition of one of the models — more work than a facade can absorb.

## Canonical sources

- Gamma, Helm, Johnson, and Vlissides — Design Patterns: Elements of Reusable Object-Oriented Software, Addison-Wesley, 1994 (Facade, Structural Patterns catalog).
- Microsoft Azure Architecture Center — Gateway Routing pattern (routing behind a unified facade endpoint): https://learn.microsoft.com/en-us/azure/architecture/patterns/gateway-routing
- Microsoft Azure Architecture Center — Gateway Aggregation pattern (facade-composed subsystem calls): https://learn.microsoft.com/en-us/azure/architecture/patterns/gateway-aggregation
- OWASP Cheat Sheet Series — Input Validation Cheat Sheet (egress/ingress validation discipline): https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
