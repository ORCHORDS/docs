# Domain Service Pattern — Workers & D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Business logic that spans two or more aggregates (e.g., "transfer funds between accounts", "merge duplicate customer records") does not belong on either aggregate. Placing it in an application service leaks domain knowledge upward; placing it inside one aggregate creates an artificial dependency on the other. The Domain Service pattern gives that logic a named home in the domain layer with no infrastructure coupling.

---

## Context

Domain Services in DDD are stateless domain-layer objects that:

- Operate on multiple aggregates or value objects
- Express a concept that belongs in the ubiquitous language ("Transfer", "Allocator", "PricingEngine")
- Accept repositories/domain objects as arguments, never infrastructure primitives directly
- Have no persistent identity of their own

In a Cloudflare Workers stack the service is a plain TypeScript class injected with repository interfaces. D1 supplies the persistence; the service never imports D1 types directly.

---

## Defining the Domain Service Interface

```typescript
// domain/services/FundTransferService.ts
export interface FundTransferService {
  transfer(
    fromAccountId: string,
    toAccountId: string,
    amount: Money,
    idempotencyKey: string
  ): Promise<TransferResult>;
}

export interface TransferResult {
  transferId: string;
  status: "completed" | "insufficient_funds" | "account_not_found";
}
```

---

## Repository Interfaces (Domain Layer, No D1 Imports)

```typescript
// domain/repositories/AccountRepository.ts
export interface AccountRepository {
  findById(id: string): Promise<Account | null>;
  save(account: Account): Promise<void>;
}

// domain/model/Account.ts
export class Account {
  constructor(
    public readonly id: string,
    private balance: Money,
    private readonly version: number
  ) {}

  debit(amount: Money): void {
    if (this.balance.lessThan(amount)) throw new InsufficientFundsError();
    this.balance = this.balance.subtract(amount);
  }

  credit(amount: Money): void {
    this.balance = this.balance.add(amount);
  }

  get currentBalance(): Money { return this.balance; }
  get optimisticVersion(): number { return this.version; }
}
```

---

## Domain Service Implementation

```typescript
// domain/services/FundTransferServiceImpl.ts
import type { AccountRepository } from "../repositories/AccountRepository";
import type { TransferRepository } from "../repositories/TransferRepository";
import type { FundTransferService, TransferResult } from "./FundTransferService";

export class FundTransferServiceImpl implements FundTransferService {
  constructor(
    private readonly accounts: AccountRepository,
    private readonly transfers: TransferRepository
  ) {}

  async transfer(
    fromId: string,
    toId: string,
    amount: Money,
    idempotencyKey: string
  ): Promise<TransferResult> {
    const existing = await this.transfers.findByIdempotencyKey(idempotencyKey);
    if (existing) return { transferId: existing.id, status: "completed" };

    const [from, to] = await Promise.all([
      this.accounts.findById(fromId),
      this.accounts.findById(toId),
    ]);

    if (!from || !to) return { transferId: "", status: "account_not_found" };

    from.debit(amount);   // throws InsufficientFundsError if balance low
    to.credit(amount);

    const transferId = crypto.randomUUID();

    // Infrastructure coordination happens in the app service or unit-of-work;
    // the domain service only expresses the invariants and orchestration.
    await this.accounts.save(from);
    await this.accounts.save(to);
    await this.transfers.record({ id: transferId, fromId, toId, amount, idempotencyKey });

    return { transferId, status: "completed" };
  }
}
```

---

## D1-Backed Repository Implementation

```typescript
// infrastructure/D1AccountRepository.ts
import type { D1Database } from "@cloudflare/workers-types";
import type { AccountRepository } from "../domain/repositories/AccountRepository";

export class D1AccountRepository implements AccountRepository {
  constructor(private readonly db: D1Database) {}

  async findById(id: string): Promise<Account | null> {
    const row = await this.db
      .prepare("SELECT id, balance_cents, version FROM accounts WHERE id = ?")
      .bind(id)
      .first<{ id: string; balance_cents: number; version: number }>();

    if (!row) return null;
    return new Account(row.id, new Money(row.balance_cents, "USD"), row.version);
  }

  async save(account: Account): Promise<void> {
    const result = await this.db
      .prepare(
        `UPDATE accounts SET balance_cents = ?, version = version + 1
         WHERE id = ? AND version = ?`
      )
      .bind(account.currentBalance.cents, account.id, account.optimisticVersion)
      .run();

    if (result.meta.changes === 0)
      throw new ConcurrencyError(`Account ${account.id} was modified concurrently`);
  }
}
```

---

## Wiring in the Worker Entry Point

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const accountRepo = new D1AccountRepository(env.DB);
    const transferRepo = new D1TransferRepository(env.DB);
    const transferService = new FundTransferServiceImpl(accountRepo, transferRepo);

    // Application service handles HTTP concerns; domain service handles domain logic
    const handler = new TransferHandler(transferService);
    return handler.handle(request);
  },
};
```

---

## Anti-patterns

- **God application service**: putting cross-aggregate logic directly in a Worker handler creates untestable, domain-leaking code.
- **Aggregate calling another aggregate's methods**: Aggregates must not hold references to other aggregates; only IDs and domain services bridge them.
- **Domain service with I/O primitives**: importing `D1Database` into the domain service breaks the dependency rule; inject the repository interface instead.
- **Stateful domain service**: storing mutable state on the service class causes bugs when the Worker instance is reused; keep it stateless.

---

## Gotchas

- **Transaction boundary**: D1 has no multi-statement transactions in the free tier batch API; use `db.batch([...])` to send multiple statements atomically when D1 supports it, or accept eventual consistency with compensating transactions.
- **Optimistic locking race**: two concurrent transfers from the same account both read version=5; the second `UPDATE ... WHERE version = 5` returns 0 changes — catch `ConcurrencyError` and retry at the application layer.
- **Error translation**: domain exceptions (`InsufficientFundsError`) must be caught by the application layer and translated to HTTP 422 before they reach the Worker response path.

---

## Verification

```typescript
// test/FundTransferService.test.ts
import { describe, it, expect, vi } from "vitest";

describe("FundTransferServiceImpl", () => {
  it("debits sender and credits receiver", async () => {
    const from = new Account("A", new Money(10000, "USD"), 1);
    const to   = new Account("B", new Money(5000, "USD"), 1);
    const accounts = { findById: vi.fn().mockResolvedValueOnce(from).mockResolvedValueOnce(to), save: vi.fn() };
    const transfers = { findByIdempotencyKey: vi.fn().mockResolvedValue(null), record: vi.fn() };

    const svc = new FundTransferServiceImpl(accounts as any, transfers as any);
    const result = await svc.transfer("A", "B", new Money(3000, "USD"), "key-1");

    expect(result.status).toBe("completed");
    expect(from.currentBalance.cents).toBe(7000);
    expect(to.currentBalance.cents).toBe(8000);
  });
});
```

---

## Related

- `application-services.md` — application layer orchestration above domain services
- `aggregate-root-pattern.md` — invariant enforcement within a single aggregate
- `unit-of-work-d1-workers.md` — batching D1 writes in a single unit of work
- `optimistic-concurrency-control-d1.md` — version-based conflict detection in D1
- `repository-pattern-ddd.md` — repository interface contracts for aggregates

---

## Sources

- Evans, E. (2003). *Domain-Driven Design*. Addison-Wesley. Ch. 5 — Domain Services
- Cloudflare D1 documentation — batch API and optimistic concurrency
- Vernon, V. (2013). *Implementing Domain-Driven Design*. Addison-Wesley.
