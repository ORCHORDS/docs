# Specification Pattern for Composable D1 Queries

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Filter logic for D1 queries gets duplicated across multiple repository methods as hand-rolled SQL strings: `WHERE status = 'active' AND region = ?`, `WHERE status = 'active' AND price < ?`, and so on. Each variant is a copy-paste risk and untestable in isolation. The Specification pattern encapsulates a single filter criterion as an object and lets you compose them with `AND` / `OR` without touching raw SQL strings.

## Context

- Runtime: Cloudflare Workers
- Database: Cloudflare D1 (SQLite dialect)
- Language: TypeScript 5.x
- Pattern: Specification (Evans, Domain-Driven Design) adapted for SQL generation
- Related: used alongside the Data Mapper pattern for the repository layer

---

## 1. Core Interface

```typescript
// src/specs/ISpecification.ts

/**
 * A Specification encapsulates one predicate that can be applied
 * to a D1 query.  `toSql()` returns the WHERE fragment and its
 * positional bindings — never interpolated values.
 */
export interface ISpecification<_T> {
  /** Returns a SQL fragment (no leading WHERE) and its bound params */
  toSql(): { clause: string; params: unknown[] };

  and(other: ISpecification<_T>): ISpecification<_T>;
  or(other: ISpecification<_T>): ISpecification<_T>;
  not(): ISpecification<_T>;
}
```

---

## 2. Abstract Base

```typescript
// src/specs/BaseSpecification.ts
import { ISpecification } from "./ISpecification";

export abstract class BaseSpecification<T> implements ISpecification<T> {
  abstract toSql(): { clause: string; params: unknown[] };

  and(other: ISpecification<T>): ISpecification<T> {
    return new AndSpecification(this, other);
  }

  or(other: ISpecification<T>): ISpecification<T> {
    return new OrSpecification(this, other);
  }

  not(): ISpecification<T> {
    return new NotSpecification(this);
  }
}

export class AndSpecification<T> extends BaseSpecification<T> {
  constructor(
    private readonly left: ISpecification<T>,
    private readonly right: ISpecification<T>
  ) {
    super();
  }

  toSql(): { clause: string; params: unknown[] } {
    const l = this.left.toSql();
    const r = this.right.toSql();
    return {
      clause: `(${l.clause} AND ${r.clause})`,
      params: [...l.params, ...r.params],
    };
  }
}

export class OrSpecification<T> extends BaseSpecification<T> {
  constructor(
    private readonly left: ISpecification<T>,
    private readonly right: ISpecification<T>
  ) {
    super();
  }

  toSql(): { clause: string; params: unknown[] } {
    const l = this.left.toSql();
    const r = this.right.toSql();
    return {
      clause: `(${l.clause} OR ${r.clause})`,
      params: [...l.params, ...r.params],
    };
  }
}

export class NotSpecification<T> extends BaseSpecification<T> {
  constructor(private readonly inner: ISpecification<T>) {
    super();
  }

  toSql(): { clause: string; params: unknown[] } {
    const { clause, params } = this.inner.toSql();
    return { clause: `NOT (${clause})`, params };
  }
}
```

---

## 3. Concrete Specifications

```typescript
// src/specs/productSpecs.ts
import { BaseSpecification } from "./BaseSpecification";

// Phantom type tag for type-safe composition
export interface ProductRecord {
  id: string;
  status: string;
  price_cents: number;
  category: string;
  in_stock: boolean;
}

export class ProductStatusSpec extends BaseSpecification<ProductRecord> {
  constructor(private readonly status: string) {
    super();
  }
  toSql() {
    return { clause: "status = ?", params: [this.status] };
  }
}

export class ProductMaxPriceSpec extends BaseSpecification<ProductRecord> {
  constructor(private readonly maxCents: number) {
    super();
  }
  toSql() {
    return { clause: "price_cents <= ?", params: [this.maxCents] };
  }
}

export class ProductCategorySpec extends BaseSpecification<ProductRecord> {
  constructor(private readonly category: string) {
    super();
  }
  toSql() {
    return { clause: "category = ?", params: [this.category] };
  }
}

export class ProductInStockSpec extends BaseSpecification<ProductRecord> {
  toSql() {
    return { clause: "in_stock = 1", params: [] };
  }
}
```

---

## 4. Repository Integration

```typescript
// src/db/productRepository.ts
import { D1Database } from "@cloudflare/workers-types";
import { ISpecification } from "../specs/ISpecification";
import { ProductRecord } from "../specs/productSpecs";

export class ProductRepository {
  constructor(private readonly db: D1Database) {}

  async findBySpec(
    spec: ISpecification<ProductRecord>,
    limit = 50,
    offset = 0
  ): Promise<ProductRecord[]> {
    const { clause, params } = spec.toSql();

    // Positional params are appended AFTER spec params
    const stmt = this.db
      .prepare(
        `SELECT id, status, price_cents, category, in_stock
         FROM products
         WHERE ${clause}
         ORDER BY id
         LIMIT ? OFFSET ?`
      )
      .bind(...params, limit, offset);

    const { results } = await stmt.all<ProductRecord>();
    return results;
  }

  async countBySpec(spec: ISpecification<ProductRecord>): Promise<number> {
    const { clause, params } = spec.toSql();
    const row = await this.db
      .prepare(`SELECT COUNT(*) AS n FROM products WHERE ${clause}`)
      .bind(...params)
      .first<{ n: number }>();
    return row?.n ?? 0;
  }
}
```

---

## 5. Composition at the Call Site

```typescript
// src/handlers/searchProducts.ts
import { Env } from "../types";
import { ProductRepository } from "../db/productRepository";
import {
  ProductStatusSpec,
  ProductMaxPriceSpec,
  ProductCategorySpec,
  ProductInStockSpec,
} from "../specs/productSpecs";

export async function handleSearchProducts(
  req: Request,
  env: Env
): Promise<Response> {
  const url = new URL(req.url);
  const category = url.searchParams.get("category") ?? "electronics";
  const maxPrice = Number(url.searchParams.get("maxPrice") ?? "10000");

  // Build composed spec — no raw SQL string concatenation
  const spec = new ProductStatusSpec("active")
    .and(new ProductInStockSpec())
    .and(new ProductCategorySpec(category))
    .and(new ProductMaxPriceSpec(maxPrice * 100)); // dollars → cents

  const repo = new ProductRepository(env.DB);
  const [products, total] = await Promise.all([
    repo.findBySpec(spec, 20, 0),
    repo.countBySpec(spec),
  ]);

  return Response.json({ products, total });
}
```

---

## Anti-patterns

- **String interpolation in `toSql()`**: never build `clause` with template literals that embed param values — always use `?` placeholders and return values in `params`.
- **Mixing in-memory predicate logic**: if you add an `isSatisfiedBy(obj: T): boolean` method, keep it separate from `toSql()` — the two evaluation paths have different invariants.
- **Global mutable spec state**: specs are value objects; make them immutable (readonly constructor fields only).
- **Composing specs from different table domains**: `AndSpecification` does not validate that left and right specs target the same table — use phantom type tags (the `_T` parameter) to catch misuse at compile time.

## Gotchas

- D1 `bind(...params)` flattens arrays — spreading `[...l.params, ...r.params]` is correct, but ensure params are primitives (string, number, null); D1 rejects objects and arrays.
- SQLite `boolean` is stored as integer; `in_stock = 1` is correct, not `in_stock = true`.
- D1 has a 100-statement batch limit and a maximum query length of ~1 MB — deeply nested `OrSpecification` trees with hundreds of alternatives should be replaced with `IN (?, ?, ...)` clauses instead.
- `LIMIT` and `OFFSET` must be integers — always coerce `Number()` and validate range before binding.

## Verification

```bash
# Unit test compositions without a real DB (pure toSql() assertions)
npx vitest run src/specs/

# Integration: run against local D1
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) FROM products WHERE status='active' AND in_stock=1"

# Curl the handler
curl -s 'http://localhost:8787/products/search?category=books&maxPrice=25' | jq .
```

## Related

- `documentation/categories/architecture/workers-data-mapper-pattern-d1-domain.md`
- `documentation/categories/architecture/workers-api-gateway-aggregator-service-bindings.md`

## Sources

- https://developers.cloudflare.com/d1/reference/d1-client-api/
- https://martinfowler.com/apsupp/spec.pdf
- https://www.sqlite.org/lang_expr.html
