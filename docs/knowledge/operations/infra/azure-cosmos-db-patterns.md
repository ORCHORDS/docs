# azure-cosmos-db-patterns

**Issue:** Cosmos DB patterns for partition key design, RU budgeting, and consistency levels
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hot partitions causing 429 throttling, unexpected RU costs, or choosing the wrong consistency level for the workload.

## Pattern / Solution
Partition key selection rules:
```
Good partition keys:
- High cardinality (thousands of distinct values)
- Evenly distributed reads/writes
- Examples: userId, orderId, deviceId

Bad partition keys:
- Low cardinality: status, country, boolean
- Monotonically increasing: timestamp, autoincrement ID
- Single hot value: "global" or tenant with 80% of traffic
```

Synthetic partition key for composite access patterns:
```javascript
// Combine user + date for time-series partitioned by user
const partitionKey = `${userId}_${year}-${month}`;
```

```hcl
resource "azurerm_cosmosdb_account" "main" {
  name                = "prod-cosmos"
  resource_group_name = azurerm_resource_group.main.name
  location            = "East US"
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level = "Session"   # default; good balance
  }

  geo_location {
    location          = "East US"
    failover_priority = 0
  }
  geo_location {
    location          = "West US"
    failover_priority = 1
  }
}
```

Consistency level tradeoffs:
```
Eventual     → lowest latency, highest throughput, stale reads possible
Session      → default; read your own writes within a session
Bounded Staleness → configurable lag (e.g. 5s or 100 ops)
Strong       → linearizable; read from primary only; highest latency
```

RU estimation:
- 1 KB read ≈ 1 RU
- 1 KB write ≈ 5 RU
- Cross-partition query ≈ fan-out × per-partition cost

## Gotchas
- Autoscale max RU sets the billing ceiling — still billed for provisioned even if unused
- Serverless mode suits sporadic workloads; provisioned throughput for steady load
- TTL must be set at container level first, then per-document — missing container TTL means documents never expire
- Cosmos DB change feed does not support DELETE events in SQL API

## Related
- `database-sharding-patterns.md`
- `azure-app-service-patterns.md`
- `cache-invalidation-strategies.md`
