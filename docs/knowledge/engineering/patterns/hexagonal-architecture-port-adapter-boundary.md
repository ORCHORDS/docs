# Hexagonal Architecture Port Adapter Boundary

## Scope

This article covers the port and adapter boundary in Hexagonal Architecture (Ports and Adapters): application logic interacting with the outside world exclusively through ports — interfaces owned by the application — with adapters supplying concrete technology implementations on both the driving (input) and driven (output) sides. Scope covers what makes a port well-formed, the composition and placement of adapters, the boundary's enforcement, and testing consequences. It excludes domain modeling inside the hexagon, overall service decomposition, and framework choice, except where those decisions leak across the boundary.

## Workflow or implementation guidance

Define ports in the application's language, oriented around intent rather than technology. A port named `PaymentGateway.charge(order)` describes what the application needs; one named `StripeClient.createPaymentIntent` describes a vendor and is a symptom that the outside chose the vocabulary. Rule of thumb: if renaming a port requires naming a product, protocol, or storage engine, the boundary is already leaking.

Classify every port as driving or driven and keep the asymmetry explicit. Driving adapters (HTTP handler, queue consumer, CLI) translate external stimuli into application calls — they parse, authenticate, and dispatch, and contain no business decisions. Driven adapters (database repository, payment gateway, email sender) translate application calls into technology operations. The application sits between them knowing neither HTTP nor SQL. Placement follows: driving adapters own request parsing and response serialization; driven adapters own persistence detail and vendor error mapping; the application owns everything you would still need if you swapped every technology tomorrow.

Composition happens once, at the outside edge:

```ts
// application owns this interface — the port
interface OrderRepository { load(id: OrderId): Promise<Order | null>; store(o: Order): Promise<void>; }

// adapter implements it — infrastructure detail
class SqlOrderRepository implements OrderRepository { /* SQL, mapping, error translation */ }

// composition root: the only place both sides appear together
const app = new PlaceOrder(new SqlOrderRepository(db), new StripePaymentGateway(keys));
```

Enforce one-directional dependency: the application module imports nothing from the adapters directory, ever. Inverse the physical layout if it helps — adapters depending on application types, never the reverse. Keep application state and control flow synchronous where possible: push asynchrony, retries, and batching to the adapters, so the application's logic remains a readable sequence of decisions, and infrastructure concerns compose around it rather than through it.

The boundary earns its cost at test time, so exploit it deliberately: application tests run against in-memory or scripted port implementations that are fast, deterministic, and able to simulate conditions (gateway declines, concurrent writes, corrupt rows) that real infrastructure makes painful to stage.

## Controls

The boundary decays quietly, so enforce it mechanically. Dependency-direction checks: a static analysis rule or import-linter asserting that the application package imports no adapter or framework module — reviewed exceptions only, with each exception documented as accepted debt. Port ownership rule: port definitions live in application packages, with adapters implementing them; a port defined inside an infrastructure package is a boundary inversion. Constructor-injection discipline: application types receive ports through constructors or an explicit composition root, and a test that greps for direct client instantiation inside application code catches the workaround where someone news up a vendor client mid-logic. Adapter size ceilings: adapters past a few hundred lines are usually hiding decisions that belong in the application, and review should push them inward. For the driving side, require that each adapter performs the same, boring sequence — parse, authorize, call application, serialize — implemented by shared scaffolding, so a new input channel cannot invent its own authorization order.

## Validation evidence

The strongest structural evidence is the swap test: run the full application test suite against a second, minimal adapter set (in-memory repository, scripted gateway) and assert it passes unchanged — the suite's independence from adapter choice is the measurable form of the boundary. Dependency-direction reports from the import-linter, run in CI on every change, show zero violations or an explicitly tracked count. Behavioral evidence: application-level tests express scenarios in domain terms and simulate error conditions through port scripts — a scripted decline from `PaymentGateway` exercises the application's fallback decision without a sandboxed vendor account, and the coverage report shows business branches covered without infrastructure mocks dominating the picture. Performance evidence: driven adapters carry their own integration test suites against real technology, measuring mapping overhead and error-translation completeness (every vendor error class mapped or explicitly failed loudly), because adapter tests are where technology risk belongs and where it must be verified. Together these show the two test populations — fast application tests plus slow adapter tests — separated cleanly, which is the operational payoff the architecture promises.

## Failure modes and correction

The characteristic failure is the anemic hexagon: logic migrates outward until the application is a pass-through and adapters hold the decisions, at which point the boundary exists only as folder structure. Correct by pulling decisions inward whenever they are touched and by reviewing adapter complexity as a smell. The second is the leaky port: a port signature carrying ORM entities, vendor error types, or protocol concepts like status codes, so switching adapters still means rewriting the application. Correct by rewriting the port in domain terms and mapping in the adapter, plus a review rule that port types come from the application's own type module. The third is framework capture: a framework's request/response types appear throughout application logic because the driving adapter passed them inward — convenient once, permanent after. Correct with an explicit request model owned by the application, translated at the adapter. A fourth is the testing bypass: teams test through the HTTP adapter with heavy scaffolding because application tests were never written, abandoning the architecture's main benefit. Correct by making application tests the default review expectation and adapter tests the narrow, slow supplement. A fifth is port explosion: an interface per use case with single implementations, yielding ceremony without swaps. Correct by coarsening ports where implementations genuinely vary together.

## Limitations

The pattern costs indirection now for optionality later, and when the option is never exercised — the application runs on one stack for its life — the cost bought nothing but mapping code. Ports express the intersection of what adapters can do, so capabilities unique to one technology (transactional semantics, partial indexing hints, vendor-specific idempotency keys) either stay outside the boundary or force the port to widen until it stops being technology-neutral, and finding that balance is continuous judgment rather than a settled rule. The boundary also relocates performance decisions: batching, caching, and connection reuse live in adapters and interact with application logic only through latency, so performance debugging crosses the seam. Team discipline is the real dependency — nothing in the code prevents the next contributor from importing the ORM into the domain, and the enforcement tooling is only as good as its exceptions process. Finally, for small services with two dependencies and no realistic swap scenario, full port-and-adapter ceremony exceeds the problem; a simpler layered boundary delivers most of the testability at a fraction of the structure.

## Canonical sources

- Alistair Cockburn — Hexagonal Architecture (Ports and Adapters), 2005: https://alistair.cockburn.us/hexagonal-architecture/
- Fowler — Inversion of Control Containers and the Dependency Injection pattern (the composition mechanics behind the boundary): https://martinfowler.com/articles/injection.html
- Microsoft Azure Architecture Center — Anti-Corruption Layer pattern (translation discipline at the boundary): https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer
