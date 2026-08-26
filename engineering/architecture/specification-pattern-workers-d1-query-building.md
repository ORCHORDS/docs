# Specification Pattern: Workers + D1 Query Building

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

API endpoints accumulate deeply nested `if/else` chains that assemble D1 SQL queries from request filters — price range, category, availability, geo-fence. Adding a new filter requires touching the handler, the query builder, and the test suite simultaneously. You want composable, testable predicates that can be combined with AND / OR / NOT without changing the query assembly core.

## Context

The Specification pattern encapsulates a single business rule as an object with a `isSatisfiedBy` method (useful for in-memory filtering) and, in the database variant, a `toSQL` method that returns a SQL fragment plus its bound parameters. Specifications compose via `AndSpecification`, `OrSpecification`, and `NotSpecification` — together they form a predicate tree. The query builder walks the tree, concatenates fragments, and flattens bindings into the correct positional order for D1's `?`-placeholder syntax. This keeps handler code declarative and each filter independently unit-testable.

## Base Specification Interface

```typescript
// specifications/Specification.ts
export interface SQLFragment {
  sql: string;
  bindings: (string | number | boolean | null)[];
}

export interface Specification<T = unknown> {
  isSatisfiedBy(candidate: T): boolean;
  toSQL(): SQLFragment;
}

export class AndSpecification<T> implements Specification<T> {
  constructor(private readonly specs: Specification<T>[]) {}

  isSatisfiedBy(candidate: T): boolean {
    return this.specs.every((s) => s.isSatisfiedBy(candidate));
  }

  toSQL(): SQLFragment {
    const parts = this.specs.map((s) => s.toSQL());
    return {
      sql: parts.map((p) => `(${p.sql})`).join(" AND "),
      bindings: parts.flatMap((p) => p.bindings),
    };
  }
}

export class OrSpecification<T> implements Specification<T> {
  constructor(private readonly specs: Specification<T>[]) {}

  isSatisfiedBy(candidate: T): boolean {
    return this.specs.some((s) => s.isSatisfiedBy(candidate));
  }

  toSQL(): SQLFragment {
    const parts = this.specs.map((s) => s.toSQL());
    return {
      sql: parts.map((p) => `(${p.sql})`).join(" OR "),
      bindings: parts.flatMap((p) => p.bindings),
    };
  }
}

export class NotSpecification<T> implements Specification<T> {
  constructor(private readonly spec: Specification<T>) {}

  isSatisfiedBy(candidate: T): boolean {
    return !this.spec.isSatisfiedBy(candidate);
  }

  toSQL(): SQLFragment {
    const inner = this.spec.toSQL();
    return { sql: `NOT (${inner.sql})`, bindings: inner.bindings };
  }
}
```

## Concrete Specifications

```typescript
// specifications/product/PriceRangeSpecification.ts
import { Specification, SQLFragment } from "../Specification";

interface Product { price: number; category: string; inStock: boolean }

export class PriceRangeSpecification implements Specification<Product> {
  constructor(private readonly min: number, private readonly max: number) {}

  isSatisfiedBy(candidate: Product): boolean {
    return candidate.price >= this.min && candidate.price <= this.max;
  }

  toSQL(): SQLFragment {
    return {
      sql: "price >= ? AND price <= ?",
      bindings: [this.min, this.max],
    };
  }
}

export class CategorySpecification implements Specification<Product> {
  constructor(private readonly categories: string[]) {}

  isSatisfiedBy(candidate: Product): boolean {
    return this.categories.includes(candidate.category);
  }

  toSQL(): SQLFragment {
    const placeholders = this.categories.map(() => "?").join(", ");
    return {
      sql: `category IN (${placeholders})`,
      bindings: this.categories,
    };
  }
}

export class InStockSpecification implements Specification<Product> {
  isSatisfiedBy(candidate: Product): boolean {
    return candidate.inStock;
  }

  toSQL(): SQLFragment {
    return { sql: "in_stock = ?", bindings: [true] };
  }
}
```

## Query Builder and Handler

```typescript
// lib/SpecificationQueryBuilder.ts
import { Specification } from "../specifications/Specification";

export function buildQuery<T>(
  table: string,
  spec: Specification<T>,
  { limit = 50, offset = 0 }: { limit?: number; offset?: number } = {}
): { sql: string; bindings: (string | number | boolean | null)[] } {
  const { sql, bindings } = spec.toSQL();
  return {
    sql: `SELECT * FROM ${table} WHERE ${sql} LIMIT ? OFFSET ?`,
    bindings: [...bindings, limit, offset],
  };
}

// handlers/products.ts
import { AndSpecification, OrSpecification } from "../specifications/Specification";
import { PriceRangeSpecification, CategorySpecification, InStockSpecification } from "../specifications/product";
import { buildQuery } from "../lib/SpecificationQueryBuilder";

export async function handleProductSearch(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const minPrice = Number(url.searchParams.get("minPrice") ?? 0);
  const maxPrice = Number(url.searchParams.get("maxPrice") ?? 999_999);
  const categories = url.searchParams.getAll("category");
  const onlyInStock = url.searchParams.get("inStock") === "true";

  const specs = [new PriceRangeSpecification(minPrice, maxPrice)];

  if (categories.length > 0) {
    specs.push(new CategorySpecification(categories));
  }

  if (onlyInStock) {
    specs.push(new InStockSpecification());
  }

  const combined = new AndSpecification(specs);
  const { sql, bindings } = buildQuery("products", combined, {
    limit: 20,
    offset: Number(url.searchParams.get("offset") ?? 0),
  });

  const result = await env.DB.prepare(sql).bind(...bindings).all();
  return Response.json(result.results);
}
```

## Anti-patterns

- Concatenating raw user input into SQL fragments inside `toSQL()` — always use positional bindings to prevent injection.
- Building deeply nested specification trees (depth > 5) without factoring composite specs into named domain rules; the tree becomes harder to read than the original `if/else`.
- Using the specification solely for in-memory filtering when the data lives in D1 — always delegate filtering to the database to avoid full table scans.

## Gotchas

- D1 uses `?` positional placeholders; the binding order must exactly match the order fragments are concatenated. `flatMap` on an array of `SQLFragment` objects preserves this order only if you maintain a consistent left-to-right traversal.
- `LIMIT` and `OFFSET` must be the last two bindings appended after `WHERE` — push them inside `buildQuery` so individual specs never need to account for pagination.

## Verification

```bash
# Test composed spec via curl
curl "https://api.example.com/products?minPrice=10&maxPrice=100&category=books&category=music&inStock=true"

# Validate generated SQL with D1 directly
wrangler d1 execute DB \
  --command "SELECT * FROM products WHERE (price >= 10 AND price <= 100) AND (category IN ('books','music')) AND in_stock = 1 LIMIT 20 OFFSET 0;"
```

## Related

- `architecture/cqrs-cloudflare-workers-d1.md`
- `architecture/repository-pattern-ddd.md`
- `architecture/d1-batch-operations-query-optimisation.md`

## Sources

- https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- https://martinfowler.com/apsupp/spec.pdf
- https://refactoring.guru/design-patterns/specification
