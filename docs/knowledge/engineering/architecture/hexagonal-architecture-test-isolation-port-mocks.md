# Hexagonal Architecture Test Isolation Port Mocks

## Scope

This article addresses the role of ports and adapters in hexagonal architecture (also known as ports and adapters, or the onion architecture) for the purpose of test isolation. It explains how the discipline of expressing every outward dependency as a port allows the application core to be tested in isolation, with mock implementations substituted for production adapters. The discussion covers the structural rules of hexagonal architecture, the mechanics of port definition and adapter implementation, the substitution of mocks in tests, and the trade-offs between pure port-mock testing and contract-driven integration testing. The article applies to any language or framework that supports dependency inversion, including TypeScript on Cloudflare Workers, Java with Spring, and Go without a framework.

## Workflow or implementation guidance

Hexagonal architecture separates the application into three concentric layers. The innermost layer is the domain model: pure business logic with no outward dependencies. The next layer is the application core: use cases that orchestrate the domain and invoke ports. The outermost layer is the adapters: concrete implementations of the ports that talk to databases, HTTP services, queues, files, clocks, and the outside world. The architecture's defining rule is that inward layers never depend on outward layers. The application core expresses its needs as ports (interfaces, in the type-system sense); the adapters implement those ports.

The first step in implementation is to identify the outward dependencies of the application. Each dependency—a database, a payment gateway, a clock, an ID generator, a queue producer—becomes a port in the application core. The port is a narrow interface that captures what the application needs, not what the dependency offers. A port for a payment gateway, for example, exposes `charge`, `refund`, and `getStatus`, not the gateway's full SDK surface. The second step is to define a "driven" port for outbound dependencies (databases, third-party APIs) and a "driving" port for inbound dependencies (the HTTP entry point, the queue consumer). The distinction matters for testing: driven ports are mocked in unit tests; driving ports are exercised by integration tests.

The third step is to write the application core against the ports and against the domain model. The application core has no `import` of any concrete database driver, HTTP client, or framework. This is the discipline that gives the test isolation guarantee. The fourth step is to write the production adapters. Each adapter is a concrete class that implements a port and is wired into the application core at composition time (the "main" function in Go, the `@Bean` configuration in Spring, the Worker entry point in Cloudflare).

The fifth step is to write the tests. Unit tests of the application core instantiate the application core with mock implementations of every port. The mock for a database port returns canned rows; the mock for a payment gateway returns canned responses; the mock for a clock returns a fixed instant. The application core's behaviour is exercised end-to-end through the use cases, but no real external system is touched. This is the primary test-isolation benefit: the application core can be tested without Docker, without a network, and without flakiness.

The sixth step is to write integration tests that exercise the real adapters against the real dependencies. These tests are slower, more brittle, and rarer, but they catch the bugs that the port-mock tests cannot: schema drift between the database adapter and the actual database, contract drift between the HTTP adapter and the actual API, and timing bugs that the fixed-clock mock hides.

## Controls

Hexagonal controls are about enforcing the boundary. The boundary is enforced by language rules (no `import` of an outward layer from an inward layer), by code review, by architectural lint rules, and by the test architecture itself: if a unit test of the application core requires a real database, the boundary has been violated. A common control is the "archunit" rule for Java, the "dependency-cruiser" rule for TypeScript, or the import-linter rule for Python: each enforces that the application core's package or directory does not import from the adapter layer.

A second class of controls covers the ports themselves. Ports should be narrow, stable, and intention-revealing. A port with fifty methods is a sign that the abstraction is leaking the dependency's surface. A port that returns an entity from a third-party SDK is a sign that the port is not abstracting away the dependency. A third class of controls covers the test mocks. Mocks should be minimal, hand-rolled, and shared only when they implement the same port. Mocking frameworks are useful but can hide the test's intent; a hand-rolled mock that returns a fixed response is often clearer than a framework-generated mock that records every interaction.

## Validation evidence

Validation of the hexagonal boundary is structural: a tool that walks the dependency graph from the application core's package outward must find no edge into a concrete adapter. The test suite is also evidence: a unit test of a use case must run in milliseconds and must not require any external service. If a unit test takes more than a second or fails because a database is not running, the boundary has been broken.

Validation of the application's behaviour is the responsibility of integration tests against real adapters and of contract tests between the application core and the ports. Contract tests assert that the application core's expectations of a port are stable across versions, so that an adapter change does not silently break the application core.

## Failure modes and correction

The dominant failure is the application core importing a concrete adapter. The "dependency inversion" rule is broken by convenience: it is easier to import the database client directly than to define a port. The cure is the architectural lint rule and the code-review gate. A second failure is the port becoming a leaky abstraction. The application core returns the database's row object, not a domain object. The cure is to define value objects in the domain layer and to map at the adapter boundary.

A third failure is the mocks becoming a copy of the production adapter. The test mocks so faithfully reproduce the production behaviour that the unit tests are integration tests in disguise. The cure is to make the mocks minimal: they answer the question "given this input, what is the next step the use case should take?" and nothing more. A fourth failure is the integration tests never running. The unit tests are green, the integration tests are flaky, and the team disables the integration tests. The cure is to invest in the test environment: a stable database in a container, a deterministic clock, a contract test against the real third-party service.

A fifth failure is the ports growing over time. Each new feature adds a method to the existing ports, and the ports become god objects. The cure is to introduce new ports for new concerns rather than extending the old ones, and to retire old ports when they have no remaining adapters.

## Limitations

Hexagonal architecture adds structural overhead. Every dependency becomes a port, every adapter implements a port, and the boilerplate can dwarf the actual business logic in a small application. The pattern is most valuable in an application with non-trivial business logic and a long lifetime; in a small prototype, the discipline is often overhead without payoff. The pattern also assumes that the team understands dependency inversion; without that understanding, the ports become interfaces in name only, and the boundary is not enforced. The pattern does not solve the problem of testing cross-cutting concerns (logging, metrics, tracing) cleanly: these are usually expressed as ports, but the port is so generic that it provides little test value.

## Canonical sources

- Alistair Cockburn — *Hexagonal Architecture* (originally "Ports and Adapters"), the originating essay: https://alistair.cockburn.us/hexagonal-architecture/
- Alistair Cockburn — *Hexagonal Architecture* talk and writings on the role of mock adapters in testing
- Eric Evans — *Domain-Driven Design*, on the role of bounded contexts and the isolation of the domain layer from infrastructure
- Vaughn Vernon — *Implementing Domain-Driven Design*, on the application of hexagonal architecture to DDD projects and the testing implications
- Martin Fowler — *Patterns of Enterprise Application Architecture*, the original catalog of the layered and domain model patterns that hexagonal architecture generalises
- Microsoft — *Azure Architecture Center* guidance on testability and dependency inversion in cloud-native services: https://learn.microsoft.com/en-us/azure/architecture/microservices/
