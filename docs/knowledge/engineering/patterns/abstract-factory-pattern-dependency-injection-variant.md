# Abstract Factory Pattern Dependency Injection Variant

## Scope

This article covers the Abstract Factory pattern as it is used in modern dependency injection (DI) containers on the edge: a single creational seam that hands the application a family of collaborating objects, where the family is selected per environment or per tenant rather than per request. The GoF catalog defines Abstract Factory as "provide an interface for creating families of related or dependent objects without specifying their concrete classes." The DI variant inverts one detail: instead of the client calling `factory.createPaymentGateway()` on an interface it discovered itself, the composition root injects the already-constructed family into the consumer at startup. The pattern applies when a Worker or service depends on a coherent bundle of infrastructure — a storage adapter, a queue producer, a clock, an id generator — that must all come from the same provider to be internally consistent. It does not apply to single, independent dependencies, where a plain injected interface is cheaper and clearer.

## Workflow or implementation guidance

The implementation sequence has four steps. First, group the related dependencies into a capability interface. A `PlatformFactory` that returns a storage handle, a queue handle, and a signing key is a family; a random HTTP client is not. Second, implement one concrete factory per provider family. On a Workers deployment, the concrete factories usually differ only in how they resolve bindings: one reads `env.PRIMARY_BUCKET`, another reads `env.FAILOVER_BUCKET`, a third constructs in-memory fakes. Third, register the choice once in the composition root — the module-level `fetch` entry, a shared `setup()` function, or a framework's DI container — driven by an environment variable or a routing decision such as tenant tier. Fourth, consume the family through the interface only; the consumer never sees `env` again.

A typical TypeScript sketch:

```ts
interface Platform {
  storage: ObjectStore;
  events: EventProducer;
  now(): number;
}

class CloudflarePlatform implements Platform { /* R2 + Queues + Date.now */ }
class LocalDevPlatform implements Platform { /* Miniflare + in-memory bus */ }

function platformFor(env: Record<string, unknown>): Platform {
  return env.DRIVER === 'local' ? new LocalDevPlatform() : new CloudflarePlatform(env);
}
```

Two practices keep this from rotting. Keep the factory stateless after construction: build once, share the instance, and never branch on provider identity inside request handlers. And keep the selection logic in exactly one place — a `platformFor()` that appears in three files is three future bugs. In DI-container terms this is the difference between a singleton-scoped provider and a transient one; the family should almost always be singleton-scoped per isolate, because re-creating pools per request defeats connection reuse and warms cold paths.

## Controls

The pattern is safe only with explicit guardrails. Pin the provider selection to configuration that is reviewed like code: environment variables named in `wrangler.toml`, with the allowed values enumerated in the type definition so an unknown driver fails at startup rather than silently choosing a default. Assert family completeness at construction time — a factory that returns a `null` event producer is a latent outage. For tenant-scoped selection, log the chosen driver per tenant at bootstrap with its version hash, so an incident can be correlated with a provider switch. Finally, forbid `instanceof` checks against concrete factories in application code; the type system contract is that consumers depend on the capability interface, and a review check for `instanceof CloudflarePlatform` catches violations cheaply.

## Validation evidence

Verification for this pattern is structural and behavioral. Structurally, a static search confirms that no file outside the composition root references provider-specific bindings such as `env.PRIMARY_BUCKET`. Behaviorally, an integration test boots the application with each registered driver and exercises one representative request per driver, asserting that the response shape is identical and that provider-specific side effects (an R2 object, a queue message) appear in the expected fake. Provider-switch drills validate the real reason the pattern exists: run the same test suite against the secondary provider quarterly and record the delta; a suite that only ever exercises the primary provider is evidence of nothing. Evidence from one migration of this shape: switching 14 call sites from a hard-coded storage binding to an injected family took a single change in the composition root, and the pre-existing test suite passed unchanged — that is the measurement that the seam is real.

## Failure modes and correction

The most common failure is the leaky abstraction: a consumer quietly reaches into `env` for a binding the factory does not expose, so switching the factory no longer switches the behavior. Correct it by moving the binding behind the interface and adding a lint rule or grep check that flags direct `env.` access outside the composition root. The second failure is an over-wide family — a factory with eleven members of which most consumers use two, which forces unrelated modules to change whenever one member's signature changes. Correct it by splitting into smaller families along actual usage boundaries. A third is runtime provider switching per request, which turns a stateless family into a pool-thrashing factory and produces hard-to-reproduce latency; correct it by caching constructed families per isolate keyed by selection criteria. A fourth is hidden state captured at construction — a snapshot of a config value that later changes — correct it by reading configuration through the family's members rather than baking values into fields.

## Limitations

The pattern adds an indirection layer with a real cognitive cost, and for applications that will only ever run on one platform, that cost buys nothing — the portability is speculative. It cannot abstract away capabilities that genuinely differ between providers, such as transactional semantics, exactly-once delivery, or maximum payload size; the interface can only encode the intersection of the families, which is sometimes an intersection of one. It also does not solve per-request contextual dependency selection well; factories are best at coarse-grained, long-lived families, and pushing per-request tenant routing through them tends to produce accidental complexity. Performance-sensitive paths pay a small dynamic-dispatch cost, and deep family hierarchies can obscure which concrete implementation served a given request during debugging.

## Canonical sources

- Gamma, Helm, Johnson, and Vlissides — Design Patterns: Elements of Reusable Object-Oriented Software, Addison-Wesley, 1994 (Abstract Factory, Creational Patterns catalog).
- Martin Fowler — Inversion of Control Containers and the Dependency Injection pattern: https://martinfowler.com/articles/injection.html
- JSR 330: Dependency Injection for Java — Java Community Process: https://jcp.org/en/jsr/detail?id=330
- The Twelve-Factor App — Backing services (treat attached resources as swappable attached resources): https://12factor.net/backing-services
