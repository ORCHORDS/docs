# Value Object Pattern in TypeScript Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A function signature reads `createOrder(userId: string, email: string, amountCents: number)`.
Callers accidentally swap `userId` and `email` — both are `string`. A negative `amountCents`
slips through because validation only exists in one of three places that create orders.
D1 receives an un-validated email that later causes a UNIQUE constraint violation.

## Context

Value Objects (VOs) are immutable, self-validating wrappers around primitive values. Two VOs
are equal when their *values* are equal, regardless of object identity. In TypeScript Workers:

- **Branded types** give compile-time type safety with zero runtime overhead for simple cases
- **Class-based VOs** provide runtime validation, domain methods, and explicit serialization
- VOs serialize to plain SQLite-compatible values for D1 storage
- Invalid values throw at construction time — callers receive a valid object or an error, never a silent bad state

---

## Section 1 — UserId Branded Type

Branded types prevent primitive obsession without class overhead. The brand exists only at
compile time; at runtime it is a plain string.

```typescript
// src/domain/valueObjects/UserId.ts

declare const __userIdBrand: unique symbol;
export type UserId = string & { readonly [__userIdBrand]: void };

export function UserId(raw: string): UserId {
  const trimmed = raw.trim();
  if (!trimmed) throw new Error('UserId cannot be empty');
  if (trimmed.length > 36) throw new Error(`UserId too long: ${trimmed.length} chars`);
  // Accept UUID v4 or ULID format
  if (!/^[a-zA-Z0-9_-]{1,36}$/.test(trimmed)) {
    throw new Error(`UserId contains invalid characters: ${trimmed}`);
  }
  return trimmed as UserId;
}

// Equality is just ===  — no helper needed for branded primitives
// Serialization: store directly as TEXT in D1
// Deserialization: UserId(row.user_id) — validates on the way out of D1 too
```

---

## Section 2 — Email Value Object (Class-based)

```typescript
// src/domain/valueObjects/Email.ts

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export class Email {
  private readonly _value: string;

  constructor(raw: string) {
    const normalised = raw.trim().toLowerCase();
    if (!EMAIL_RE.test(normalised)) {
      throw new Error(`Invalid email address: "${raw}"`);
    }
    if (normalised.length > 254) {
      throw new Error(`Email exceeds RFC 5321 maximum length: ${normalised.length}`);
    }
    this._value = normalised;
  }

  get value(): string {
    return this._value;
  }

  get domain(): string {
    return this._value.split('@')[1];
  }

  /** Value equality — two Email instances with the same address are equal. */
  equals(other: Email): boolean {
    return this._value === other._value;
  }

  /** Serialize to D1 TEXT column. */
  toD1(): string {
    return this._value;
  }

  /** Deserialize from a D1 TEXT column value. */
  static fromD1(stored: string): Email {
    return new Email(stored);
  }

  toString(): string {
    return this._value;
  }

  toJSON(): string {
    return this._value;
  }
}
```

---

## Section 3 — Money Value Object

Money stores amounts as integer cents to avoid floating-point rounding errors.

```typescript
// src/domain/valueObjects/Money.ts

export type Currency = 'USD' | 'EUR' | 'GBP';

const CURRENCY_MINOR_UNITS: Record<Currency, number> = {
  USD: 2,
  EUR: 2,
  GBP: 2,
};

export class Money {
  private readonly _cents: number;
  private readonly _currency: Currency;

  constructor(cents: number, currency: Currency) {
    if (!Number.isInteger(cents)) {
      throw new Error(`Money amount must be an integer (cents), got: ${cents}`);
    }
    if (cents < 0) {
      throw new Error(`Money amount cannot be negative: ${cents}`);
    }
    if (cents > 999_999_99) {
      throw new Error(`Money amount exceeds maximum (999,999.99): ${cents}`);
    }
    this._cents = cents;
    this._currency = currency;
  }

  get cents(): number { return this._cents; }
  get currency(): Currency { return this._currency; }

  /** Human-readable decimal string, e.g. "19.99" */
  get decimal(): string {
    const factor = Math.pow(10, CURRENCY_MINOR_UNITS[this._currency]);
    return (this._cents / factor).toFixed(CURRENCY_MINOR_UNITS[this._currency]);
  }

  add(other: Money): Money {
    this.assertSameCurrency(other);
    return new Money(this._cents + other._cents, this._currency);
  }

  subtract(other: Money): Money {
    this.assertSameCurrency(other);
    const result = this._cents - other._cents;
    if (result < 0) throw new Error('Money subtraction would produce a negative amount');
    return new Money(result, this._currency);
  }

  multiply(factor: number): Money {
    if (!Number.isFinite(factor) || factor < 0) {
      throw new Error(`Invalid multiply factor: ${factor}`);
    }
    return new Money(Math.round(this._cents * factor), this._currency);
  }

  equals(other: Money): boolean {
    return this._cents === other._cents && this._currency === other._currency;
  }

  isGreaterThan(other: Money): boolean {
    this.assertSameCurrency(other);
    return this._cents > other._cents;
  }

  private assertSameCurrency(other: Money): void {
    if (this._currency !== other._currency) {
      throw new Error(
        `Currency mismatch: ${this._currency} vs ${other._currency}`
      );
    }
  }

  /** Serialize for D1: store cents as INTEGER and currency as TEXT. */
  toD1(): { amountCents: number; currency: Currency } {
    return { amountCents: this._cents, currency: this._currency };
  }

  static fromD1(amountCents: number, currency: Currency): Money {
    return new Money(amountCents, currency);
  }

  toJSON(): { amount: string; currency: Currency } {
    return { amount: this.decimal, currency: this._currency };
  }

  toString(): string {
    return `${this.decimal} ${this._currency}`;
  }
}
```

---

## Section 4 — Using Value Objects in a Domain Service and D1 Repository

```typescript
// src/domain/services/RegisterUserService.ts

import { UserId } from '../valueObjects/UserId';
import { Email } from '../valueObjects/Email';
import type { IUserRepository } from '../repositories/IUserRepository';

export interface RegisterUserCommand {
  rawId: string;
  rawEmail: string;
  displayName: string;
}

export async function registerUser(
  repo: IUserRepository,
  command: RegisterUserCommand
): Promise<void> {
  // Construction validates — throws descriptive errors on bad input
  const userId = UserId(command.rawId);
  const email = new Email(command.rawEmail);

  const existing = await repo.findByEmail(email.value);
  if (existing) {
    throw new Error(`Email already registered: ${email.value}`);
  }

  await repo.create({
    id: userId,           // TypeScript enforces UserId, not a plain string
    email: email.toD1(), // normalised, validated email
    displayName: command.displayName.trim(),
  });
}

// src/infrastructure/repositories/D1UserRepository.ts (excerpt)
// Demonstrates round-trip serialization through D1

import { Email } from '../../domain/valueObjects/Email';
import { UserId } from '../../domain/valueObjects/UserId';
import { Money } from '../../domain/valueObjects/Money';

// On write:
async function insertOrder(db: D1Database, order: {
  id: ReturnType<typeof UserId>;
  userEmail: Email;
  total: Money;
}): Promise<void> {
  const { amountCents, currency } = order.total.toD1();
  await db
    .prepare(
      'INSERT INTO orders (id, user_email, amount_cents, currency) VALUES (?1, ?2, ?3, ?4)'
    )
    .bind(order.id, order.userEmail.toD1(), amountCents, currency)
    .run();
}

// On read — reconstruct VOs from raw D1 row:
interface RawOrderRow {
  id: string;
  user_email: string;
  amount_cents: number;
  currency: string;
}

function rowToOrder(row: RawOrderRow) {
  return {
    id: UserId(row.id),
    userEmail: Email.fromD1(row.user_email),
    total: Money.fromD1(row.amount_cents, row.currency as import('../../domain/valueObjects/Money').Currency),
  };
}
```

---

## Anti-patterns

- **Mutating VOs after construction** — use `readonly` fields and `private` setters. Never expose a setter.
- **Validating the same rule in multiple places** — put all validation in the VO constructor; call the constructor everywhere.
- **Storing `Money` as a float** — floating-point arithmetic loses precision. Always store cents as INTEGER.
- **Comparing VOs with `===`** — for class-based VOs, `===` compares references. Always use `.equals()`.
- **Letting `Email` hold un-normalised values** — normalise (trim + lowercase) in the constructor, not at call sites.

## Gotchas

- Branded types are erased at runtime; `typeof userId` is `'string'`. Do not rely on `instanceof` checks for branded primitives.
- `JSON.stringify` calls `.toJSON()` automatically on class instances — make sure your VOs implement it to avoid `{}`.
- D1 stores integers up to 2^53 − 1 (JavaScript safe integer range). For very large monetary amounts, switch to `REAL` with explicit precision handling or use a string.
- When deserializing from D1, always reconstruct VOs rather than casting raw strings — this re-runs validation and catches data corruption.

## Verification

```bash
# Type-safety check: passing a plain string where UserId is required must fail
npx tsc --noEmit

# Unit tests for each VO
npx vitest run src/domain/valueObjects/

# D1 round-trip test
npx wrangler d1 execute DB --local --command \
  "SELECT amount_cents, currency FROM orders LIMIT 1;"
```

## Related

- `workers-repository-pattern-d1.md` — repositories that serialize/deserialize VOs
- `workers-unit-of-work-d1-batch.md` — UoW receiving VO-typed arguments
- `workers-anti-corruption-layer-legacy.md` — VOs used as targets of ACL translation

## Sources

- Evans, E. (2003). *Domain-Driven Design*. Addison-Wesley. Chapter 5: A Model Expressed in Software — Value Objects.
- [TypeScript Handbook: Branded Types](https://www.typescriptlang.org/play#example/nominal-typing)
- [Cloudflare D1 data types](https://developers.cloudflare.com/d1/learning/d1-and-orm/#data-types)
