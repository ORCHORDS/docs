# Adapter Pattern Cloud Provider Portability

## Scope

This article covers the Adapter pattern — GoF structural pattern "convert the interface of a class into another interface clients expect" — applied specifically to multi-cloud and provider-portability seams. The scope is the narrow, deliberate adaptation layer between an application and an external provider whose native API shape cannot or should not leak inward: object storage with different key semantics, blob stores with different multipart contracts, DNS or CDN APIs with different resource models, or vendor SDKs that pull heavy dependencies into the build. The pattern is about interface conversion, not feature parity. It is in scope when the application's internal contract is already settled and the provider must be bent to meet it; it is out of scope when the goal is full workload portability across clouds, which requires abstraction at the deployment and data layers as well, or when only a single provider will realistically ever be used.

## Workflow or implementation guidance

Begin by writing the internal interface first, from the application's vocabulary, never from the provider's. A `DocumentStore.put(key, bytes, contentType)` is a good internal contract; `uploadPart(bucketName, partNumber, uploadId)` is a provider concept and belongs only inside an adapter. Then implement one adapter per provider behind that interface. Each adapter owns four responsibilities exclusively: request construction, authentication, response mapping, and provider-specific error translation into a small internal error taxonomy (`NotFound`, `Conflict`, `Throttled`, `Unavailable`). Nothing else.

Order the error translation deliberately, because it is where adapters earn their keep. Map the provider's HTTP status to the internal taxonomy in one switch at the adapter boundary, so retry logic elsewhere can branch on internal categories instead of parsing vendor error bodies. Then wire the adapter through a service binding or an environment-driven constructor so callers never instantiate provider clients directly. On edge runtimes, prefer provider clients that work over plain fetch rather than SDKs requiring Node-only modules; an adapter that compiles everywhere is worth more than one that exposes the provider's full feature surface.

A representative internal contract and provider mapping:

```ts
type StoreError = 'not_found' | 'conflict' | 'throttled' | 'unavailable';

interface DocumentStore {
  put(key: string, body: Uint8Array, contentType: string): Promise<void>;
  get(key: string): Promise<Uint8Array | null>;
}

class EdgeObjectStore implements DocumentStore {
  // provider-specific headers, auth, and status mapping live here and nowhere else
}
```

Version the internal interface. When a provider releases a capability the application genuinely needs — conditional writes, object locking, batch delete — extend the interface with an optional capability method and check for it with a type guard, rather than widening the base contract and breaking every other adapter.

## Controls

Portability seams decay silently, so control them with tests and inventory, not intentions. Maintain an adapter registry listing every internal interface, every provider implementation, and which one is production-active; a registry that shows two adapters where only one has a green test run is a finding, not a detail. Require that each adapter's integration test suite runs against the real provider in CI on a schedule, because adapter code is the one place where mocks lie convincingly — a mocked 200 response cannot reveal that a provider changed its pagination token format. Forbid provider type names, error codes, and header constants in application code outside the adapter directory, enforced by a grep check in the build. Cap adapter size: an adapter past roughly four hundred lines is usually hiding orchestration logic that belongs in the application layer, and review should push it back out.

## Validation evidence

The evidence that an adapter portability seam works is a passing dual-provider run, not a clean diagram. Concretely: run the application's contract test suite — the suite that exercises the internal interface's documented semantics — against every registered adapter, and require identical results modulo explicitly declared provider differences recorded in a deviation table. For migration work, capture before/after evidence: byte-identical GET results for a sampled key set, and read/write latency distributions per provider for at least a few hundred thousand operations, so the portability cost is quantified rather than guessed. One portability drill worth running before committing to a second provider: implement the cheapest possible adapter and measure how much of the internal interface it could satisfy honestly. If the answer is under about eighty percent, the interface was secretly modeled on the first provider and needs redesign before the second adapter is written — discovering this in a drill costs a week, discovering it during an outage-driven migration costs much more.

## Failure modes and correction

The dominant failure is the lowest-common-denominator interface: the second provider cannot express conditional writes, so the capability is removed from the contract and the first provider's correctness guarantees silently degrade. Correct this by modeling capability differences as explicit optional methods plus a documented deviation table, never by deleting semantics. The second failure is adapter logic creep — pagination, retry, or business rules accumulating inside the adapter until it becomes an untestable tangle. Correct it by restricting adapters to translation only and moving policy into the application layer where it can be tested provider-agnostically. A third is error-translation drift: a provider changes an error payload shape, unmapped statuses fall through as `unknown`, and upstream retry logic stops distinguishing throttling from hard failure. Correct it with a default mapping that fails loudly — every unmapped status is logged with its raw body and counted in a metric. A fourth is credential coupling, where adapter tests only pass with long-lived production keys; correct it with short-lived scoped credentials in CI and an explicit expiry check.

## Limitations

Adapters convert interfaces, not operational reality. Latency profiles, consistency models, rate-limit shapes, and pricing differ across providers, so an application ported through adapters still needs provider-specific load and failure testing. The pattern also cannot abstract provider lock-in at the data layer: terabytes stored under one provider's key naming and lifecycle rules remain a migration project regardless of how clean the interface is. Each adapter is permanent maintenance surface, exercised rarely enough that regressions surface during emergencies unless scheduled provider tests exist. Finally, interface-first design tends to lag provider innovation; teams that adopt new provider features quickly may find the abstraction more friction than shield, and should confine adapters to stable, commodity capabilities such as storage, queues, and DNS rather than cutting-edge services.

## Canonical sources

- Gamma, Helm, Johnson, and Vlissides — Design Patterns: Elements of Reusable Object-Oriented Software, Addison-Wesley, 1994 (Adapter, Structural Patterns catalog).
- The Twelve-Factor App — Backing services (swappable attached resources as a portability discipline): https://12factor.net/backing-services
- Cloudflare Workers — Service bindings (provider seams without public HTTP): https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Microsoft Azure Architecture Center — Ambassador pattern (interposing translation in a helper process): https://learn.microsoft.com/en-us/azure/architecture/patterns/ambassador
