# Specification Pattern: Composable D1 Query Building in Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your D1 queries grow as product requirements accumulate: filter by status, then add date ranges, then add multi-tenant scoping, then add full-text search, then add pagination. The result is a proliferation of query-building functions with boolean parameter combinatorics (`getOrdersActiveAfterDateForTenant(active, after, tenantId, page, ...)`). Adding a new filter requires touching every query function.

Classic signs:
- Query helper functions with 6+ boolean/optional parameters
- Duplicated `WHERE` clause fragments across multiple query functions
- Tests that enumerate every combination of filter flags
- Business rules like "eligible order" expressed in both SQL and TypeScript separately, prone to divergence

---

## Context

The Specification pattern encapsulates a business rule as an object that can answer "does this candidate satisfy this rule?" and—in the persistence variant—translate itself into a SQL predicate. Specifications compose via `and()`, `or()`, and `not()` combinators. The query builder accumulates `WHERE` clauses and bound parameters from a composed specification tree, then executes a single parameterised D1 statement.

This keeps business rules in one place, testable in isolation, and reusable across queries without SQL string surgery.

```
ActiveSpec.and(TenantSpec("acme")).and(DateRangeSpec(from, to))
  ↓ toSql()
"(status = 'active') AND (tenant_id = ?) AND (created_at BETWEEN ? AND ?)"
params: ["acme", from, to]
```

---

## Core Specification Types

```typescript
// src/spec/types.ts
export interface SqlSpec {
  toSql(): { clause: string; params: unknown[] };
  and(other: SqlSpec): SqlSpec;
  or(other: SqlSpec): SqlSpec;
  not(): SqlSpec;
}
```

---

## Base Class and Combinators

```typescript
// src/spec/base.ts
import type { SqlSpec } from "./types";

export abstract class BaseSpec implements SqlSpec {
  abstract toSql(): { clause: string; params: unknown[] };

  and(other: SqlSpec): SqlSpec {
    return new AndSpec(this, other);
  }

  or(other: SqlSpec): SqlSpec {
    return new OrSpec(this, other);
  }

  not(): SqlSpec {
    return new NotSpec(this);
  }
}

class AndSpec extends BaseSpec {
  constructor(private left: SqlSpec, private right: SqlSpec) { super(); }

  toSql() {
    const l = this.left.toSql();
    const r = this.right.toSql();
    return {
      clause: `(${l.clause}) AND (${r.clause})`,
      params: [...l.params, ...r.params],
    };
  }
}

class OrSpec extends BaseSpec {
  constructor(private left: SqlSpec, private right: SqlSpec) { super(); }

  toSql() {
    const l = this.left.toSql();
    const r = this.right.toSql();
    return {
      clause: `(${l.clause}) OR (${r.clause})`,
      params: [...l.params, ...r.params],
    };
  }
}

class NotSpec extends BaseSpec {
  constructor(private inner: SqlSpec) { super(); }

  toSql() {
    const { clause, params } = this.inner.toSql();
    return { clause: `NOT (${clause})`, params };
  }
}
```

---

## Concrete Specifications

```typescript
// src/spec/order-specs.ts
import { BaseSpec } from "./base";

export class ActiveOrderSpec extends BaseSpec {
  toSql() {
    return { clause: "status = 'active'", params: [] };
  }
}

export class TenantSpec extends BaseSpec {
  constructor(private tenantId: string) { super(); }

  toSql() {
    return { clause: "tenant_id = ?", params: [this.tenantId] };
  }
}

export class DateRangeSpec extends BaseSpec {
  constructor(private from: string, private to: string) { super(); }

  toSql() {
    return {
      clause: "created_at BETWEEN ? AND ?",
      params: [this.from, this.to],
    };
  }
}

export class MinimumValueSpec extends BaseSpec {
  constructor(private minCents: number) { super(); }

  toSql() {
    return { clause: "total_cents >= ?", params: [this.minCents] };
  }
}

export class FullTextSpec extends BaseSpec {
  constructor(private term: string) { super(); }

  toSql() {
    // D1 LIKE search; use FTS5 virtual table for production full-text
    return { clause: "lower(description) LIKE ?", params: [`%${this.term.toLowerCase()}%`] };
  }
}

// Composite domain specification: "eligible for expedited shipping"
export class ExpeditedEligibleSpec extends BaseSpec {
  constructor(private tenantId: string) { super(); }

  toSql() {
    const active = new ActiveOrderSpec();
    const tenant = new TenantSpec(this.tenantId);
    const highValue = new MinimumValueSpec(10000); // $100+
    return active.and(tenant).and(highValue).toSql();
  }
}
```

---

## Query Builder

```typescript
// src/spec/query-builder.ts
import type { SqlSpec } from "./types";

export interface QueryOptions {
  orderBy?: string;
  direction?: "ASC" | "DESC";
  limit?: number;
  offset?: number;
}

export function buildQuery(
  table: string,
  spec: SqlSpec,
  options: QueryOptions = {}
): { sql: string; params: unknown[] } {
  const { clause, params } = spec.toSql();
  const { orderBy = "created_at", direction = "DESC", limit = 50, offset = 0 } = options;

  // Allowlist column names to prevent injection via orderBy
  const safeOrder = /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(orderBy) ? orderBy : "created_at";
  const safeDir = direction === "ASC" ? "ASC" : "DESC";

  const sql = [
    `SELECT * FROM ${table}`,
    `WHERE ${clause}`,
    `ORDER BY ${safeOrder} ${safeDir}`,
    `LIMIT ? OFFSET ?`,
  ].join(" ");

  return { sql, params: [...params, limit, offset] };
}
```

---

## Worker: Composing Specs from Request Filters

```typescript
// src/worker.ts
import {
  ActiveOrderSpec, TenantSpec, DateRangeSpec, FullTextSpec, ExpeditedEligibleSpec,
} from "./spec/order-specs";
import { buildQuery } from "./spec/query-builder";
import type { SqlSpec } from "./spec/types";
import { BaseSpec } from "./spec/base";

export interface Env { DB: D1Database }

// A passthrough spec that matches everything (useful as the "empty" accumulator)
class AllSpec extends BaseSpec {
  toSql() { return { clause: "1=1", params: [] }; }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const p = url.searchParams;

    const tenantId = request.headers.get("X-Tenant-Id");
    if (!tenantId) return new Response("Unauthorized", { status: 401 });

    // Always scope to tenant
    let spec: SqlSpec = new TenantSpec(tenantId);

    if (p.get("status") === "active") {
      spec = spec.and(new ActiveOrderSpec());
    }

    if (p.get("from") && p.get("to")) {
      spec = spec.and(new DateRangeSpec(p.get("from")!, p.get("to")!));
    }

    if (p.get("q")) {
      spec = spec.and(new FullTextSpec(p.get("q")!));
    }

    if (p.get("expedited") === "true") {
      // Reuse the composite domain spec — DRY
      spec = spec.and(new ExpeditedEligibleSpec(tenantId));
    }

    const { sql, params } = buildQuery("orders", spec, {
      limit: Number(p.get("limit") ?? 50),
      offset: Number(p.get("offset") ?? 0),
    });

    const { results } = await env.DB.prepare(sql).bind(...params).all();
    return Response.json({ data: results, spec: spec.toSql().clause });
  },
};
```

---

## Unit-Testing Specifications Without D1

```typescript
// src/spec/__tests__/order-specs.test.ts
import { ActiveOrderSpec, TenantSpec, DateRangeSpec, ExpeditedEligibleSpec } from "../order-specs";

describe("TenantSpec", () => {
  it("produces correct clause and params", () => {
    const spec = new TenantSpec("acme");
    expect(spec.toSql()).toEqual({ clause: "tenant_id = ?", params: ["acme"] });
  });
});

describe("Composite specs", () => {
  it("and() joins clauses", () => {
    const spec = new ActiveOrderSpec().and(new TenantSpec("acme"));
    const { clause, params } = spec.toSql();
    expect(clause).toBe("(status = 'active') AND (tenant_id = ?)");
    expect(params).toEqual(["acme"]);
  });

  it("not() wraps clause", () => {
    const spec = new ActiveOrderSpec().not();
    expect(spec.toSql().clause).toBe("NOT (status = 'active')");
  });

  it("ExpeditedEligibleSpec composes correctly", () => {
    const spec = new ExpeditedEligibleSpec("acme");
    const { clause, params } = spec.toSql();
    expect(clause).toContain("status = 'active'");
    expect(clause).toContain("tenant_id = ?");
    expect(params).toContain("acme");
    expect(params).toContain(10000);
  });
});
```

---

## Anti-patterns

- **Concatenating SQL strings inside specifications**: `clause: `status = '${status}'`` is a SQL injection vulnerability. Always use `?` placeholders and return `params`.
- **Accessing the D1 database inside a specification**: Specifications describe predicates; they must not execute queries. Keep them pure functions of their constructor arguments.
- **One monolithic specification with all filters as constructor booleans**: This recreates the combinatorics problem in a new location. Each distinct business rule gets its own class.
- **Forgetting to allowlist `orderBy` column names**: The query builder receives `orderBy` from the request. Interpolating it directly into SQL allows column-name injection. Use a regex or enum allowlist.
- **Deeply nested `and(or(and(...)))` trees without readability aids**: For complex trees, create named composite specs (like `ExpeditedEligibleSpec`) to document the business intent.

---

## Gotchas

- D1's `bind(...params)` uses positional `?` markers. The order of parameters from `toSql()` must exactly match the order of `?` placeholders in the clause. Combinator order (left then right) must be consistent.
- D1 does not support named parameters (`:name`). If your spec tree is complex, log the generated SQL and params during development to verify ordering.
- `LIMIT` and `OFFSET` are appended by the query builder, not the spec. Do not add them inside specifications.
- SQLite (D1) `LIKE` is case-insensitive for ASCII but case-sensitive for non-ASCII. The `FullTextSpec` uses `lower()` on both sides as a workaround; for production use an FTS5 virtual table.
- Specifications are plain objects and inexpensive to construct. There is no need to cache or singleton them.

---

## Verification

1. Unit-test each specification in isolation (`toSql()` output only—no D1 needed).
2. Send a GET request with `?status=active&from=2026-01-01&to=2026-12-31&q=invoice` and log the generated SQL; verify all four clauses appear.
3. Omit `?status` and confirm the active-order clause is absent from the SQL.
4. Attempt `?limit=9999` and confirm the query builder caps at the configured maximum (add capping logic to `buildQuery` options).
5. Confirm `ExpeditedEligibleSpec` generates identical SQL whether called standalone or `.and()`-composed with another spec.

---

## Related

- `repository-pattern.md` — the repository uses specifications to query
- `pagination-cursor-pattern.md` — cursor-based pagination with D1
- `multi-tenant-data-isolation.md` — enforcing `TenantSpec` at the middleware level
- `database-index-strategies.md` — indexing the columns your specs filter on

---

## Sources

- Evans, Eric — Domain-Driven Design (2003): Specification pattern
- Fowler, Martin — Specification: https://martinfowler.com/apsupp/spec.pdf
- Cloudflare D1 prepared statements: https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- SQLite FTS5: https://www.sqlite.org/fts5.html
