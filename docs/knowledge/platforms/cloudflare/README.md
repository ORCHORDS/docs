---
title: "Cloudflare Platform Knowledge"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-02"
review-cycle: "90 days"
next-review: "2026-12-01"
---

# Cloudflare Platform Knowledge

Reusable operational guidance for Cloudflare Workers, Durable Objects, D1, R2, Hyperdrive, Queues, Analytics Engine, Cache, WAF, and Turnstile. Vendor facts are verified against current primary documentation.

## Selected guidance

### Workers

- [Workers Versioned Migrations Deployment Discipline](workers-versioned-migrations-deployment.md)
- [Workers Smart Placement Read-Regression Testing](workers-smart-placement-read-regression.md)
- [Workers Gradual Deployments Traffic Split Verification](workers-gradual-deployments-traffic-split.md)
- [Workers Queues Backpressure and Concurrency Limits](workers-queues-backpressure-limits.md)
- [Workers Analytics Engine SQL Boundaries](workers-analytics-engine-sql-boundaries.md)
- [Workers Logs and Observability Query Limits](workers-logs-observability-query-limits.md)
- [Durable Object Hibernation WebSocket Budget](durable-object-hibernation-websocket-budget.md)

### Storage and data

- [D1 Backup and Time Travel Restore Drills](d1-backups-time-travel-restore-drill.md)
- [D1 Read Replication Consistency Models](d1-read-replication-consistency.md)
- [R2 Lifecycle Rules and Storage Tiers](r2-lifecycle-rules-storage-tiers.md)
- [Hyperdrive Connection Pooling Savings Analysis](hyperdrive-connection-pool-savings.md)

### Edge and security

- [Turnstile Managed Versus Invisible Mode](turnstile-managed-vs-invisible-mode.md)
- [Zaraz Consent Mode Integration](zaraz-consent-mode-integration.md)
- [Cache API Stale-While-Revalidate Governance](cache-api-stale-while-revalidate-governance.md)
- [Cache Reserve Cost Governance](cache-reserve-cost-governance.md)
- [WAF Custom Rules Expression Budget](waf-custom-rules-expression-budget.md)
- [Ruleset Phase Order Validation](ruleset-phase-order-validation.md)
