# Polyglot Persistence Pick Two Theorem

## Scope

This article addresses the engineering discipline of polyglot persistence, the deliberate use of multiple data storage technologies within a single system, each chosen for the workload it serves. It explains the trade-offs that justify the discipline, the constraints that govern the choice, and the "pick two" formulation that captures the impossibility of getting all three of consistency, availability, and partition tolerance from a single data store in the presence of a network partition. The discussion covers relational, document, key-value, wide-column, graph, search, time-series, and object stores, and the patterns for using each. The article applies to any system whose data needs have outgrown a single database engine.

## Workflow or implementation guidance

Polyglot persistence begins with the recognition that different data has different access patterns. A relational database is good at transactional integrity; a document store is good at flexible schema; a key-value store is good at low-latency reads; a search engine is good at full-text queries; a graph database is good at relationship traversals; a columnar store is good at analytical scans; an object store is good at large blobs. Trying to make one engine serve all these needs results in a compromise: the relational database that stores JSON documents in TEXT columns, the document store that simulates joins in application code, the search engine that is not transactional.

The first step in adopting polyglot persistence is to identify the bounded contexts of the application and to choose a primary store per context. The order domain is owned by a relational database or by an event store; the product catalog is owned by a document store; the search index is owned by Elasticsearch; the recommendation engine is owned by a graph database or a vector store; the user session is owned by an in-memory key-value store; the analytics warehouse is owned by a columnar store; the file archive is owned by an object store. Each store is chosen for the access pattern of its context.

The second step is to design the data flow between stores. A change in the primary store is replicated to the secondary stores asynchronously: a product update in the catalog eventually appears in the search index, the recommendation model, and the warehouse. The replication is typically event-driven: a domain event is raised when the catalog changes, and the secondary stores subscribe. The third step is to accept the consequences of eventual consistency. A search index may be seconds behind the catalog; a recommendation may be stale; a warehouse query may not include the last minute of writes. The application must be designed against these consequences.

The fourth step is to govern the proliferation. Polyglot persistence is not "add a new database every time a new feature is needed." Each new store adds operational complexity (a new deployment, a new backup, a new monitoring surface). The team must justify each store and must be willing to retire stores that no longer earn their place.

The "pick two" formulation, derived from Brewer's CAP theorem, captures a related truth: in the presence of a network partition, a distributed data store can provide either consistency (every read sees the latest write) or availability (every request receives a response) but not both. This is not an absolute impossibility—modern systems make nuanced trade-offs—but it is the shape of the design space. A relational database with synchronous replication chooses consistency; a Dynamo-style key-value store chooses availability. The polyglot application must understand which trade-off each store makes and must design around the consequences.

## Controls

Polyglot controls cover data governance, replication integrity, and store-level SLAs. Data governance: every data element must have an owner, a primary store, and a documented replication path. Replication integrity: the replication between stores must be observable (lag metrics, error rates), idempotent (a duplicate event must not double-write), and recoverable (a failed replication must be replayable). Store-level SLAs: each store has its own availability, durability, and performance targets, and the application must accept the worst-case of those targets.

Operational controls include the runbook for each store, the backup policy for each store, and the access control for each store. A team that adopts polyglot persistence inherits the operational burden of every store; the burden is real and must be staffed.

## Validation evidence

Validation must prove that the stores are consistent enough for the application's needs. The standard test writes to the primary store, waits for replication, and asserts that the secondary store reflects the write. The test must cover the failure path: a replication failure must not corrupt the secondary store; the secondary store must remain queryable, possibly with stale data, and the system must catch up when the replication recovers.

Validation must also prove that the application behaves correctly under each store's failure mode. If the search index is down, the application must still serve the catalog page (perhaps without search). If the session store is down, the application must still serve authenticated users (perhaps by falling back to a longer-lived store). The validation is typically done as a chaos test: each store is taken down in turn, and the application is observed.

## Failure modes and correction

The dominant failure is unbounded store proliferation. Every team adds the store that fits its feature, and the operational surface explodes. The cure is governance: a clear policy on when a new store is justified, and a clear owner for each existing store. A second failure is replication lag becoming user-visible. The user searches for a product that was just added but does not see it because the search index is behind. The cure is to expose the lag in the UI ("indexed 3 seconds ago") or to reduce the lag by faster replication.

A third failure is silent data divergence. The primary store and the secondary store disagree, and the disagreement is not detected until a customer reports it. The cure is reconciliation: a periodic job that compares the stores and reports (or auto-corrects) differences. A fourth failure is the wrong CAP trade-off being chosen. A store is expected to be consistent and available during a partition, and the application is designed around that expectation, but the store's actual behaviour under partition is different. The cure is to read the store's documented guarantees and to design against them.

A fifth failure is the polyglot stores becoming a polyglot of licenses, deployment patterns, and security models. The cure is to standardise on a small set of stores and to consolidate where possible.

## Limitations

Polyglot persistence is a powerful discipline but it is not free. The operational cost of running multiple stores is real: each store has its own deployment, its own backup, its own monitoring, its own on-call rotation. The team must be willing to invest in the operational maturity to support multiple stores; without that investment, the discipline collapses into chaos. The "pick two" formulation is also a simplification: modern systems like Google Spanner or CockroachDB make trade-offs that blur the CAP line, and the application must understand the actual guarantees of the actual store.

Finally, polyglot persistence is not a substitute for good data modelling. A well-modelled relational database can serve many access patterns; a well-modelled document store can serve many access patterns. The decision to introduce a new store should be made after the existing stores have been exhausted, not before.

## Canonical sources

- Martin Fowler — *PolyglotPersistence* bliki entry, defining the discipline and its rationale: https://martinfowler.com/bliki/PolyglotPersistence.html
- Pramod Sadalage — *NoSQL Distilled* and *Refactoring Databases* (Addison-Wesley), the canonical reference for evolutionary database design and polyglot persistence
- Eric Brewer — *CAP Twelve Years Later: How the "Rules" Have Changed* (Computer, 2012), the updated formulation of CAP
- AWS — *NoSQL vs SQL* and database service documentation, contextualising the polyglot choice in a cloud setting: https://aws.amazon.com/what-is/load-balancing/
