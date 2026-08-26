# Data Mesh Architecture

> **When to use:** When a single central data team has become the bottleneck
> for every analytics request, the central data lake/warehouse is a swamp of
> ungoverned, duplicated, stale data, and domain teams know their data best
> but have no way to own it end-to-end.

Data mesh is an **organizational and architectural** pattern coined by
Zhamak Dehghani. It is not a technology. It treats data as a product,
owned by the domains that produce it, rather than as a central pipeline
owned by one team.

## Symptom

You need to consider data mesh when:

- Every new dashboard, ML feature, or report requires a ticket to the
  central data team, which has a 6-month backlog. Time-to-insight is
  measured in quarters.
- The central data lake contains 50 copies of "the customer table," each
  slightly different, none authoritative. No one trusts any of them.
- ETL pipelines are a tangled web of brittle jobs. One upstream schema
  change breaks a dozen downstream dashboards silently.
- Domain teams (orders, billing, marketing) produce great operational data
  but have no clean way to expose it for analytics. Everything funnels
  through the central team's extraction process.
- Data quality is everyone's complaint and no one's responsibility. There is
  no owner per dataset.

The diagnosis: **centralized data ownership does not scale with the number of
domains or the appetite for data.** The bottleneck is organizational, not
technical.

## Core Idea

Four principles, all required:

1. **Domain-oriented decentralized data ownership.** Each business domain
   (orders, payments, fulfillment) owns its data products end-to-end,
   including the analytical views it exposes.
2. **Data as a product.** Each domain publishes curated, documented,
   versioned, discoverable **data products** with SLOs (freshness, accuracy,
   latency)—treated with the same rigor as a customer-facing API.
3. **Self-serve data infrastructure as a platform.** A platform team provides
   the underlying plumbing (storage, compute, cataloging, access control,
   lineage) so domains focus on their data, not on infrastructure.
4. **Federated computational governance.** Global policies (naming,
   interoperability, security, compliance) are encoded and enforced
   automatically, not by a central data team reviewing tickets.

```
[Domain A] --data product--> [Catalog] <--query-- [Data Consumer]
[Domain B] --data product--> [Catalog] <--query-- [ML Team]
[Domain C] --data product--> [Catalog] <--query-- [Finance BI]
                ^
                |
   [Self-serve platform: storage, compute, governance, lineage]
```

The unit is a **data product**: an addressable, discoverable dataset with an
owner, a schema, a contract, and quality SLOs. Domains build them; consumers
find them in the catalog and use them directly.

## Gotchas

- **This is primarily an org change, not a tech buy.** Adopting a data mesh
  tool without redistributing data ownership changes nothing. The hardest
  part is getting domain teams to accept ownership and accountability for
  analytical data they used to hand off.
- **Domains must have the skills to produce data products.** If the orders
  team has never thought about data quality, freshness SLOs, or schema
  evolution, they need enablement. Without it, the mesh produces
  low-quality products and trust collapses. Invest in the platform team's
  self-serve tooling and in domain enablement—both.
- **You still need a platform team.** "Decentralized" does not mean "no
  central team." It means the central team builds infrastructure and
  governance, not pipelines. Underinvesting in the platform is the #1 reason
  meshes stall.
- **Data products need real contracts.** A dataset without a schema, an
  owner, an SLO, and a version is just a file. The "data as a product"
  principle is meaningless without enforcement. Tooling (DataHub, OpenMetadata,
  Amundsen) helps, but culture enforces it.
- **Governance must be computational, not manual.** A federated governance
  model where a committee reviews every dataset does not scale. Policies
  (PII tagging, access rules, retention) must be encoded as code and enforced
  by the platform. This is hard to build; budget for it.
- **Cross-domain joins become the consumer's problem.** In a centralized
  warehouse, joining orders to payments is one SQL query. In a mesh, those
  are two separate products owned by two domains. Consumers either federate
  the query or materialize a combined view. Both have costs.
- **Vendor lock-in risk.** Many vendors now sell "data mesh in a box." Some
  are good; none deliver the organizational change. Be skeptical of pitches
  that conflate a catalog tool with the full pattern.
- **Migration is long and painful.** You cannot flip a switch from a central
  warehouse to a mesh. Expect years, not months. A common path: pick one
  domain, stand up its data products and the platform plumbing, prove the
  model, then expand domain by domain.
- **Without discoverability, the mesh is invisible.** A great data product
  nobody can find is useless. The catalog (with search, lineage, quality
  scores, and ownership) is the connective tissue. Underinvest here and the
  mesh fragments into isolated silos—worse than the warehouse you left.

## Practical Example (Conceptual)

**A data product definition (orders domain publishing to the catalog):**

```yaml
# orders-domain/data-products/orders-summary.yaml
name: orders.daily-summary
owner: team-orders
version: 1.3.0
description: >
  Daily order counts and revenue, partitioned by date and region.
slo:
  freshness: PT6H          # updated within 6 hours of day-close
  accuracy: 99.9%         # reconciles to operational DB within 0.1%
schema:
  type: object
  properties:
    order_date: { type: date }
    region: { type: string }
    order_count: { type: integer }
    revenue_usd: { type: number }
access:
  classification: internal
  pii: false
  grant: via-datahub-request
quality:
  - row_count > 0
  - revenue_usd >= 0
  - no_nulls: [order_date, region]
```

**Consumer finds and uses it via the catalog (not a ticket):**

```bash
# Search the catalog
datahub search "orders daily revenue"

# Discover ownership, SLOs, and access policy
datahub get orders.daily-summary

# Request access (auto-provisioned if policy passes)
datahub request-access orders.daily-summary

# Query it (federated or materialized depending on platform)
SELECT region, SUM(revenue_usd) FROM orders.daily_summary
WHERE order_date >= CURRENT_DATE - 30
GROUP BY region;
```

The consumer never filed a ticket with a central team. The orders team owns
the product and its quality. Governance (PII, access) is encoded, not manual.

## When NOT to use data mesh

- **Small org with one or two domains.** A central warehouse with a small
  data team is simpler and cheaper. Mesh overhead is not justified.
- **Homogeneous data with one consumer pattern** (e.g., a single BI
  dashboard). Centralized works fine.
- **No appetite for organizational change.** If leadership will not
  redistribute ownership and fund a platform team, the pattern will not take.
- **Tight, synchronous, cross-domain query needs.** If your analytics
  fundamentally require joining many domains in real time, the mesh's
  domain-boundary cost may exceed the benefit.

## Decision Checklist

1. Are there 4+ distinct business domains producing data? -> Mesh candidate
2. Is the central data team a chronic bottleneck? -> Mesh candidate
3. Is data quality unowned and untrusted? -> Mesh candidate
4. Can you fund a self-serve platform team? -> Required
5. Will domains accept ownership of analytical data products? -> Required
6. Is this a small, single-domain org? -> Stay centralized

## Related Articles

- `data-lakehouse-pattern.md` — a complementary *storage* architecture (mesh
  is an *ownership* model; lakehouse can be the platform underneath it)
- `data-pipeline-architecture.md` — the centralized pipeline model mesh replaces
- `data-replication-strategies.md` — moving data between domains
- `domain-driven-design-basics.md` — domain boundaries, foundational to mesh
- `bounded-context-design.md` — each domain's data product scope
- `contract-first-api-design.md` — data products need contracts too
