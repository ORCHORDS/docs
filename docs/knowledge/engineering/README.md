---
title: "Engineering Documentation"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Engineering Documentation

This family contains reusable software-engineering knowledge, including architecture, databases, development tooling, frontend and mobile engineering, internationalization, patterns, performance, product engineering, project delivery, quality, research, testing, and worktree practices.

## Selected current guidance

- [Generative AI SSDF Community Profile](GENAI_SSDF_COMMUNITY_PROFILE.md)
- [A2A TCK Conformance Governance](A2A_TCK_CONFORMANCE_GOVERNANCE.md)

## 2026-09-01 standards and implementation guidance

- [Accessible Name and Description Computation 1.2](frontend/accname-1-2-verification.md)
- [ARIA in HTML Conformance](frontend/aria-in-html-conformance.md)
- [Service Workers Lifecycle Algorithms](frontend/service-worker-lifecycle-verification.md)
- [WAI-ARIA 1.2 Conformance](frontend/wai-aria-1-2-conformance.md)
- [WCAG 2.2 Accessible Authentication (Minimum)](frontend/wcag-accessible-authentication.md)
- [WCAG 2.2 Dragging Movements](frontend/wcag-dragging-movements.md)
- [WCAG 2.2 Focus Appearance](frontend/wcag-focus-appearance.md)
- [WCAG 2.2 Focus Not Obscured (Minimum)](frontend/wcag-focus-not-obscured.md)
- [WCAG 2.2 Target Size (Minimum)](frontend/wcag-target-size-minimum.md)

## 2026-09-01 cross-family standards and governance guidance

- [Ieee 1012 2016 Verification And Validation](IEEE_1012_2016_VERIFICATION_AND_VALIDATION.md)
- [Ieee 1028 2008 Software Reviews](IEEE_1028_2008_SOFTWARE_REVIEWS.md)
- [Ieee 12207 2017 Software Lifecycle Processes](IEEE_12207_2017_SOFTWARE_LIFECYCLE_PROCESSES.md)
- [Ieee 830 1998 Software Requirements Specification](IEEE_830_1998_SOFTWARE_REQUIREMENTS_SPECIFICATION.md)
- [Ietf Http Semantics Rfc 9110 Governance](IETF_HTTP_SEMANTICS_RFC_9110_GOVERNANCE.md)
- [Ietf Rfc 2119 Rfc 8174 Requirement Level Keywords](IETF_RFC_2119_RFC_8174_REQUIREMENT_LEVEL_KEYWORDS.md)
- [Iso Iec 25010 2011 Software Product Quality Model](ISO_IEC_25010_2011_SOFTWARE_PRODUCT_QUALITY_MODEL.md)
- [Iso Iec 27001 2022 Information Security Management](ISO_IEC_27001_2022_INFORMATION_SECURITY_MANAGEMENT.md)
- [Iso Iec Ieee 42010 2022 Architecture Description](ISO_IEC_IEEE_42010_2022_ARCHITECTURE_DESCRIPTION.md)
- [Nist Sp 800 218 Secure Software Development Framework](NIST_SP_800_218_SECURE_SOFTWARE_DEVELOPMENT_FRAMEWORK.md)
- [Nist Sp 800 53 Security And Privacy Controls](NIST_SP_800_53_SECURITY_AND_PRIVACY_CONTROLS.md)
- [W3C Wcag 2 2 Conformance Model](W3C_WCAG_2_2_CONFORMANCE_MODEL.md)

## 2026-09-01 batch 5 engineering deep dive

### patterns

- [Abstract Factory Pattern Dependency Injection Variant](patterns/abstract-factory-pattern-dependency-injection-variant.md)
- [Adapter Pattern Cloud Provider Portability](patterns/adapter-pattern-cloud-provider-portability.md)
- [Anti Corruption Layer Federated Data](patterns/anti-corruption-layer-federated-data.md)
- [Bulkhead Pattern Connection Pool Isolation](patterns/bulkhead-pattern-connection-pool-isolation.md)
- [Chain of Responsibility Pattern Validation Pipeline](patterns/chain-of-responsibility-pattern-validation-pipeline.md)
- [Circuit Breaker Pattern Retry Budget](patterns/circuit-breaker-pattern-retry-budget.md)
- [Claim Check Pattern Large Payload Queue](patterns/claim-check-pattern-large-payload-queue.md)
- [Command Pattern Audit Log Append Only](patterns/command-pattern-audit-log-append-only.md)
- [Compensating Transaction Pattern Saga Orchestration](patterns/compensating-transaction-pattern-saga-orchestration.md)
- [CQRS Pattern Event Store Segregation](patterns/cqrs-pattern-event-store-segregation.md)
- [Decorator Pattern Traffic Shaping Layer](patterns/decorator-pattern-traffic-shaping-layer.md)
- [Domain Event Pattern Outbox Table](patterns/domain-event-pattern-outbox-table.md)
- [Event Sourcing Pattern Snapshot Strategy](patterns/event-sourcing-pattern-snapshot-strategy.md)
- [Facade Pattern Public API Stabilization](patterns/facade-pattern-public-api-stabilization.md)
- [Feature Flag Pattern Launch Darkly Style Rollout](patterns/feature-flag-pattern-launch-darkly-style-rollout.md)
- [Hexagonal Architecture Port Adapter Boundary](patterns/hexagonal-architecture-port-adapter-boundary.md)
- [Outbox Pattern Exactly Once Delivery](patterns/outbox-pattern-exactly-once-delivery.md)
- [Pub Sub Pattern Topic Filter Semantics](patterns/pub-sub-pattern-topic-filter-semantics.md)
- [Saga Pattern Choreography vs Orchestration](patterns/saga-pattern-choreography-vs-orchestration.md)
- [Strangler Fig Pattern Traffic Mirror Fallback](patterns/strangler-fig-pattern-traffic-mirror-fallback.md)

### performance

- [Ab Test Velocity Distortion Web Vitals](performance/ab-test-velocity-distortion-web-vitals.md)
- [Ad Blocking Impact On First Load Timing](performance/ad-blocking-impact-on-first-load-timing.md)
- [Analytics Engine Query Latency Budget](performance/analytics-engine-query-latency-budget.md)
- [Cache Stampede Probabilistic Early Revalidation](performance/cache-stampede-probabilistic-early-revalidation.md)
- [Cdn Cache Key Normalization Strip Cookies](performance/cdn-cache-key-normalization-strip-cookies.md)
- [Connection Pool Starvation Thundering Herd](performance/connection-pool-starvation-thundering-herd.md)
- [Core Web Vitals CLS Image Dimension Reservation](performance/core-web-vitals-cls-image-dimension-reservation.md)
- [Critical Render Path Preload Vs Http2 Push](performance/critical-render-path-preload-vs-http2-push.md)
- [Curl Vs Fetch TLS Handshake Warm Up](performance/curl-vs-fetch-tls-handshake-warm-up.md)
- [D1 Cold Start Latency Mitigation Strategy](performance/d1-cold-start-latency-mitigation-strategy.md)
- [Database Connection Lifetime Vs Throughput Pool](performance/database-connection-lifetime-vs-throughput-pool.md)
- [Decompression Cost Brotli Vs Zstd Comparison](performance/decompression-cost-brotli-vs-zstd-comparison.md)
- [Dns Prefetch Tradeoffs Resolver Warmup](performance/dns-prefetch-tradeoffs-resolver-warmup.md)
- [Durable Objects Input Gating Throughput Limit](performance/durable-objects-input-gating-throughput-limit.md)
- [Http3 Quic Head Of Line Blocking Improvement](performance/http3-quic-head-of-line-blocking-improvement.md)
- [Json Serialization Thrift Vs Protobuf Vs Capnp](performance/json-serialization-thrift-vs-protobuf-vs-capnp.md)
- [R2 Object First Byte Latency Warm Region](performance/r2-object-first-byte-latency-warm-region.md)
- [Service Worker Render Blocking Paint Suppression](performance/service-worker-render-blocking-paint-suppression.md)
- [Tail Latency P99 Budget Allocation](performance/tail-latency-p99-budget-allocation.md)
- [Wasm Module Streaming Compile Perf](performance/wasm-module-streaming-compile-perf.md)

### testing

- [Accessibility Axe Core Rules Update Cadence](testing/accessibility-axe-core-rules-update-cadence.md)
- [API Contract Testing Pact Broker Versioning](testing/api-contract-testing-pact-broker-versioning.md)
- [Blue Green Deployment Test Strategy Mirror Traffic](testing/blue-green-deployment-test-strategy-mirror-traffic.md)
- [Boundary Value Analysis Equivalence Partitioning](testing/boundary-value-analysis-equivalence-partitioning.md)
- [Canary Deployment Automated Rollback SLI Check](testing/canary-deployment-automated-rollback-sli-check.md)
- [Chaos Engineering Game Day Runbook](testing/chaos-engineering-game-day-runbook.md)
- [Contract Test Schema Evolution Backwards Compatibility](testing/contract-test-schema-evolution-backwards-compat.md)
- [Coverage Mutation Testing Stryker Report](testing/coverage-mutation-testing-stryker-report.md)
- [Database Fixture Rollback Vs Truncate Strategy](testing/database-fixture-rollback-vs-truncate-strategy.md)
- [End To End Test Flake Quarantine Policy](testing/end-to-end-test-flake-quarantine-policy.md)
- [Fault Injection Toxiproxy Failpoints](testing/fault-injection-toxiproxy-failpoints.md)
- [Fuzz Testing Property Based Fast Check](testing/fuzz-testing-property-based-fast-check.md)
- [Integration Test Database Testcontainers](testing/integration-test-database-testcontainers.md)
- [Load Testing K6 Script Versioning Regression](testing/load-testing-k6-script-versioning-regression.md)
- [Mutation Testing Weak Equivalence Operators](testing/mutation-testing-weak-equivalence-operators.md)
- [Page Object Model Selector Stability Playwright](testing/page-object-model-selector-stability-playwright.md)
- [RBAC Test Matrix Role Enumeration ISTQB](testing/rbac-test-matrix-role-enumeration-istqb.md)
- [Security Test Zap Baseline Passive Scan](testing/security-test-zap-baseline-passive-scan.md)
- [Visual Regression Pixelmatch Threshold Calibration](testing/visual-regression-pixelmatch-threshold-calibration.md)
- [Worker Vitest Isolated Storage Mock Pool](testing/worker-vitest-isolated-storage-mock-pool.md)

### database

- [Advisory Lock Pattern Pg Try Advisory Xact Lock](database/advisory-lock-pattern-pg-try-advisory-xact-lock.md)
- [Archive Table Vs Cold Partition Strategy](database/archive-table-vs-cold-partition-strategy.md)
- [Audit Log Timestamp Monotonic Clock UTC](database/audit-log-timestamp-monotonic-clock-utc.md)
- [Connection Lifetime Short Vs Long Pool Pg](database/connection-lifetime-short-vs-long-pool-pg.md)
- [Covering Index Index Only Scan Explain Plan](database/covering-index-index-only-scan-explain-plan.md)
- [Dead Letter Table Vs Soft Delete Pattern](database/dead-letter-table-vs-soft-delete-pattern.md)
- [Explain Analyze Buffers Cost Row Estimate](database/explain-analyze-buffers-cost-row-estimate.md)
- [Generated Column Stored Vs Virtual Tradeoff](database/generated-column-stored-vs-virtual-tradeoff.md)
- [Hot Row Update Skip Locked Queue Table](database/hot-row-update-skip-locked-queue-table.md)
- [Hyperdrive Read Replica Routing Pool Size](database/hyperdrive-read-replica-routing-pool-size.md)
- [Idempotent Migration Zero Downtime Prisma](database/idempotent-migration-zero-downtime-prisma.md)
- [Jsonb Index Gin Operator Class Tradeoffs](database/jsonb-index-gin-operator-class-tradeoffs.md)
- [Partial Index Where Clause Rare Flag](database/partial-index-where-clause-rare-flag.md)
- [Partition Pruning List Partition Cost Savings](database/partition-pruning-list-partition-cost-savings.md)
- [Prepared Statement Plan Cache Pollution](database/prepared-statement-plan-cache-pollution.md)
- [Read Replica Lag Tolerant Routing Strategy](database/read-replica-lag-tolerant-routing-strategy.md)
- [Row Level Security Policy Execution Order](database/row-level-security-policy-execution-order.md)
- [Time Range Index Btree Vs Brin Selection](database/time-range-index-btree-vs-brin-selection.md)
- [Transaction Isolation Read Committed Vs Snapshot](database/transaction-isolation-read-committed-vs-snapshot.md)
- [Write Ahead Log Fsync Trade Off Durability](database/write-ahead-log-fsync-trade-off-durability.md)

### architecture

- [12 Factor App Config Store Vs Env Vars](architecture/12-factor-app-config-store-vs-env-vars.md)
- [Api Gateway Bff Edge Composition Pattern](architecture/api-gateway-bff-edge-composition-pattern.md)
- [Bulkhead Quota Microservice Failure Domain](architecture/bulkhead-quota-microservice-failure-domain.md)
- [Cache Coherence Write Through Vs Write Behind](architecture/cache-coherence-write-through-vs-write-behind.md)
- [Cell Based Architecture Shard Promise](architecture/cell-based-architecture-shard-promise.md)
- [Circuit Breaker Half Open State Policy](architecture/circuit-breaker-half-open-state-policy.md)
- [Cqrs Read Model Projection Event Ordering](architecture/cqrs-read-model-projection-event-ordering.md)
- [Data Lakehouse Medallion Lake Architecture](architecture/data-lakehouse-medallion-lake-architecture.md)
- [Event Driven Schema Registry Evolution](architecture/event-driven-schema-registry-evolution.md)
- [Hexagonal Architecture Test Isolation Port Mocks](architecture/hexagonal-architecture-test-isolation-port-mocks.md)
- [Layered Architecture Transaction Script Vs Domain](architecture/layered-architecture-transaction-script-vs-domain.md)
- [Leader Election Consensus Raft Etcd](architecture/leader-election-consensus-raft-etcd.md)
- [Load Balancer L4 Vs L7 Routing Decision](architecture/load-balancer-l4-vs-l7-routing-decision.md)
- [Microservice Chassis Spring Cloud Vs Go Kit](architecture/microservice-chassis-spring-cloud-vs-go-kit.md)
- [Observability Three Pillars Trace Metric Log](architecture/observability-three-pillars-trace-metric-log.md)
- [Polyglot Persistence Pick Two Theorem](architecture/polyglot-persistence-pick-two-theorem.md)
- [Queue Based Load Leveling Throttle Pattern](architecture/queue-based-load-leveling-throttle-pattern.md)
- [Service Mesh Sidecar Vs Sidecar Less Istio](architecture/service-mesh-sidecar-vs-sidecar-less-istio.md)
- [Sidecar Pattern Observability Shared Runtime](architecture/sidecar-pattern-observability-shared-runtime.md)
- [Zero Trust Network Segmentation Mtls Spiffe](architecture/zero-trust-network-segmentation-mtls-spiffe.md)
