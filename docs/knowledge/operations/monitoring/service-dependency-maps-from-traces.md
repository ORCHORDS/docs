# service-dependency-maps-from-traces

**Issue:** Nobody can hold a modern service topology in their head, and hand-maintained architecture diagrams are lies by the time they are committed. Distributed traces already contain the ground truth: every client-server span pair is an edge between two services. The OpenTelemetry service graph connector derives that map mechanically, matching client spans to their server spans and emitting edge metrics (traces_service_graph_request_total plus client and server duration metrics, dimensioned by source, destination, and success) that backends render as service maps or that drive dependency-aware alerting. The engineering problem is making the derived map trustworthy: incomplete instrumentation produces missing edges, broken context propagation produces phantom edges, and whatever the collector cannot see does not exist on the map, so a naive service graph is a map of your tracing gaps as much as your architecture.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the derivation works

1. **Span-kind pairing.** The connector inspects traces for spans in parent-child relationships where one side is a client span and the other a server span; each matched pair becomes an edge from the client's service to the server's service, with service.name supplying the node labels.
2. **Connectors join pipelines.** A connector acts as both exporter and receiver: the traces pipeline exports into the service graph connector, and the connector feeds a metrics pipeline, so no custom code is needed to turn traces into topology metrics.
3. **A wait window closes edges.** The connector buffers briefly (the latency setting) to let the server side of a request arrive before concluding an edge is one-sided; too small a window creates spurious client-server mismatch edges, too large a window adds memory cost and lag.
4. **Dimensions add context.** Beyond the default source/destination/success dimensions, the dimensions setting can lift span attributes (like the RPC method or messaging destination) onto edge metrics, at the usual cardinality cost per added dimension.

## Making the map trustworthy

1. **Propagation completeness is prerequisite.** Edges only appear where W3C trace context crosses the boundary intact; any hop that drops or mangles traceparent shows up as a broken chain and a missing or malformed edge, so fix propagation before trusting topology.
2. **Both sides must be instrumented.** If a dependency is called with an HTTP client that emits no client span, or the callee emits no server span, the edge silently never forms; the connector cannot invent relationships from one-sided data, which is the top cause of "why is service X missing from my map".
3. **The collector only maps what it sees.** Services exporting to a different backend, uninstrumented third parties, and database or queue traffic without appropriate instrumentation do not appear; state explicitly on the dashboard which telemetry sources feed the map.
4. **Handle virtual links for queues.** Messaging systems that break the parent-child relationship (produce here, consume there) need the connector's virtual node/link handling or explicit messaging conventions, otherwise queue edges are absent even when both producer and consumer are traced.

## Using the map operationally

1. **Blast-radius estimation.** During an incident, the service graph answers "what talks to this service" in seconds, which scopes the search for collateral impact and turns vague escalation into a concrete dependency list.
2. **Edge-level RED metrics.** Because each edge carries request rate, duration, and failure dimensions, you can alert on a specific dependency relationship (service A failing calls to service B) rather than averaging both endpoints together and hiding the problem.
3. **Change detection on topology.** A new edge appearing in the graph is often the first visible artifact of an unauthorized or accidental coupling; diffing the edge set over time catches architecture drift that code review missed.
4. **Input for capacity and risk planning.** Aggregate edge rates over weeks show which dependencies are actually load-bearing, informing which third parties deserve circuit breakers, retries, and explicit degradation plans.

## Pitfalls and maintenance

1. **Naming discipline defines node identity.** service.name is the node key; inconsistent naming (svc-payment, payment, payment-prod on the same logical service) fragments one node into three with split edges, so enforce naming at SDK config time.
2. **Sampling changes the map.** Head sampling at low rates makes rare edges vanish intermittently; run the service graph connector on a pipeline fed by tail sampling or full-fidelity traffic so topology is not sampled away with the noise.
3. **Keep an eye on edge cardinality.** Each dimension multiplies the metric series the connector emits; a fleet-wide map with method-level dimensions can generate more series than the underlying latency metrics, so add dimensions deliberately.
4. **Treat the map as derived, versioned data.** Rebuild it continuously from live traces, never snapshot it into a wiki; the whole value is that it cannot rot the way a hand-drawn diagram does.
