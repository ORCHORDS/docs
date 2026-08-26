# Value Object Pattern in Workers TypeScript Domain Modeling

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Business logic in Workers handlers mixes raw primitives (`string`, `number`) with
domain concepts (`EmailAddress`, `Money`, `UserId`). Validation is scattered — the
same email regex appears in three files, money arithmetic is done with raw floats
causing rounding errors, and a function that expects a user ID silently accepts any
string. Bugs surface at runtime rather than at the type-checker.

Value Objects are small, immutable, self-validating domain types that wrap a primitive
and encode the rules that make it meaningful. They turn type errors into compile errors,
keep validation in one place, and make function signatures self-documenting.

---

## Context

A **Value Object** (Evans, "Domain-Driven Design") is an object defined by its value,
not its identity:

- `UserId("u_123")` equals `UserId("u_123")` regardless of which instance it is.
- It is **immutable** — once created, the wrapped value cannot change.
- It is **self-validating** — construction fails if the value is invalid.
- It carries domain-specific **behaviour** — `Money.add()`, `EmailAddress.domain()`.

In TypeScript the natural implementation is a class with a `private` constructor and
a static factory method that returns a `Result` or throws on invalid input. A nominal
type trick (`declare private readonly _brand`) prevents structural compatibility
between types that have the same underlying primitive.

In Cloudflare Workers the pattern is especially valuable because:

1. Workers are stateless — validation must happen at the boundary on every request.
2. D1 stores raw SQL types; reconstruction from DB rows needs a single trusted path.
3. KV and Queue payloads are untyped JSON — deserialization is the right place to
   enforce invariants.

---

## Core Implementation

### 1. Generic `ValueObject` base class

```typescript
// domain/ValueObject.ts

/**
 * Nominal brand prevents accidental structural compatibility.
 * `UserId` cannot be passed where `OrderId` is expected, even though
 * both wrap a string.
 */
export abstract class ValueObject<T, Brand extends string> {
  // Unreachable at runtime; exists only for the type-checker
  declare private readonly _brand: Brand;

  protected constructor(protected readonly _value: T) {}

  get value(): T {
    return this._value;
  }

  equals(other: ValueObject<T, Brand>): boolean {
    return this._value === other._value;
  }

  toString(): string {
    return String(this._value);
  }

  toJSON(): T {
    return this._value;
  }
}
```

### 2. `Result` type for explicit error handling

Value Object construction can fail. Throwing is acceptable, but a `Result` type makes
the failure path visible in the call site's type signature — no try/catch required.

```typescript
// domain/Result.ts
export type Result<T, E = string> =
  | { ok: true;  value: T }
  | { ok: false; error: E };

export function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

export function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

export function unwrap<T>(result: Result<T>): T {
  if (!result.ok) throw new Error(result.error);
  return result.value;
}
```

### 3. Concrete Value Objects

```typescript
// domain/EmailAddress.ts
import { ValueObject } from "./ValueObject";
import { type Result, ok, err } from "./Result";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export class EmailAddress extends ValueObject<string, "EmailAddress"> {
  private constructor(value: string) {
    super(value.toLowerCase().trim());
  }

  static create(raw: string): Result<EmailAddress> {
    const trimmed = (raw ?? "").toLowerCase().trim();
    if (!trimmed) return err("Email address must not be empty");
    if (!EMAIL_RE.test(trimmed)) return err(`Invalid email address: "${trimmed}"`);
    if (trimmed.length > 254) return err("Email address exceeds maximum length of 254 characters");
    return ok(new EmailAddress(trimmed));
  }

  /** Parse and throw — for contexts where failure is truly unexpected */
  static parse(raw: string): EmailAddress {
    const result = EmailAddress.create(raw);
    if (!result.ok) throw new TypeError(result.error);
    return result.value;
  }

  get domain(): string {
    return this._value.split("@")[1];
  }

  get localPart(): string {
    return this._value.split("@")[0];
  }
}
```

```typescript
// domain/Money.ts
import { ValueObject } from "./ValueObject";
import { type Result, ok, err } from "./Result";

/** Represents a monetary amount as integer cents to avoid floating-point errors. */
export class Money extends ValueObject<number, "Money"> {
  private constructor(
    private readonly _cents: number,
    readonly currency: string,
  ) {
    super(_cents);
  }

  static fromCents(cents: number, currency: string): Result<Money> {
    if (!Number.isInteger(cents))   return err("Money cents must be an integer");
    if (cents < 0)                  return err("Money amount cannot be negative");
    if (!/^[A-Z]{3}$/.test(currency)) return err(`Invalid ISO 4217 currency code: "${currency}"`);
    return ok(new Money(cents, currency));
  }

  static fromMajorUnits(amount: number, currency: string): Result<Money> {
    const cents = Math.round(amount * 100);
    return Money.fromCents(cents, currency);
  }

  get cents(): number { return this._cents; }

  get majorUnits(): number { return this._cents / 100; }

  add(other: Money): Money {
    if (other.currency !== this.currency) {
      throw new Error(`Cannot add ${other.currency} to ${this.currency}`);
    }
    return new Money(this._cents + other._cents, this.currency);
  }

  multiply(factor: number): Money {
    return new Money(Math.round(this._cents * factor), this.currency);
  }

  format(locale = "en-US"): string {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: this.currency,
    }).format(this.majorUnits);
  }

  toJSON() {
    return { cents: this._cents, currency: this.currency };
  }
}
```

```typescript
// domain/UserId.ts
import { ValueObject } from "./ValueObject";
import { type Result, ok, err } from "./Result";

// Example: "u_01J8…" — UUID v7 with "u_" prefix
const USER_ID_RE = /^u_[0-9a-z]{20,36}$/;

export class UserId extends ValueObject<string, "UserId"> {
  private constructor(value: string) { super(value); }

  static create(raw: string): Result<UserId> {
    if (!raw)                       return err("UserId must not be empty");
    if (!USER_ID_RE.test(raw))      return err(`Invalid UserId format: "${raw}"`);
    return ok(new UserId(raw));
  }

  static parse(raw: string): UserId {
    const r = UserId.create(raw);
    if (!r.ok) throw new TypeError(r.error);
    return r.value;
  }
}
```

---

## Integration with Workers Request Parsing

```typescript
// handlers/create-order.ts
import { EmailAddress } from "../domain/EmailAddress";
import { Money } from "../domain/Money";
import { UserId } from "../domain/UserId";
import { ok, err, type Result } from "../domain/Result";

interface CreateOrderInput {
  userId: UserId;
  email:  EmailAddress;
  amount: Money;
}

function parseCreateOrderBody(body: unknown): Result<CreateOrderInput> {
  if (typeof body !== "object" || body === null) {
    return err("Request body must be a JSON object");
  }
  const raw = body as Record<string, unknown>;

  const userIdResult = UserId.create(String(raw.userId ?? ""));
  if (!userIdResult.ok) return err(`userId: ${userIdResult.error}`);

  const emailResult = EmailAddress.create(String(raw.email ?? ""));
  if (!emailResult.ok) return err(`email: ${emailResult.error}`);

  const amountResult = Money.fromMajorUnits(Number(raw.amountUsd), "USD");
  if (!amountResult.ok) return err(`amountUsd: ${amountResult.error}`);

  return ok({
    userId: userIdResult.value,
    email:  emailResult.value,
    amount: amountResult.value,
  });
}

export async function handleCreateOrder(request: Request): Promise<Response> {
  const body = await request.json().catch(() => null);
  const parsed = parseCreateOrderBody(body);

  if (!parsed.ok) {
    return Response.json(
      { error: "Validation failed", detail: parsed.error },
      { status: 422 },
    );
  }

  const { userId, email, amount } = parsed.value;

  // Type-safe: userId, email, amount are domain types, not raw primitives
  console.log(`Order for ${email.value} (${userId}) — ${amount.format()}`);

  return Response.json({ created: true });
}
```

---

## Reconstruction from D1 Rows

```typescript
// repos/UserRepo.ts
import { UserId } from "../domain/UserId";
import { EmailAddress } from "../domain/EmailAddress";

export interface UserRecord {
  id:    UserId;
  email: EmailAddress;
}

interface UserRow {
  user_id: string;
  email:   string;
}

export function rowToUserRecord(row: UserRow): UserRecord {
  return {
    id:    UserId.parse(row.user_id),  // throws if DB data is corrupt
    email: EmailAddress.parse(row.email),
  };
}

export async function findUser(
  db: D1Database,
  id: UserId,
): Promise<UserRecord | null> {
  const row = await db
    .prepare("SELECT user_id, email FROM users WHERE user_id = ? LIMIT 1")
    .bind(id.value)          // .value unwraps safely
    .first<UserRow>();
  return row ? rowToUserRecord(row) : null;
}
```

---

## Serialisation for Queues and KV

Value Objects implement `toJSON()` so they serialise transparently:

```typescript
// Queue message composition
const message = {
  userId: userId,      // toJSON() → "u_01J8…"
  amount: amount,      // toJSON() → { cents: 4999, currency: "USD" }
  email:  email,       // toJSON() → "user@example.com"
};
await env.ORDER_QUEUE.send(message);

// Reconstruction from queue message body
const body = message as { userId: string; amount: { cents: number; currency: string }; email: string };
const orderId   = UserId.parse(body.userId);
const orderAmt  = Money.fromCents(body.amount.cents, body.amount.currency);
const orderEmail = EmailAddress.parse(body.email);
```

---

## Anti-patterns

- **Mutable Value Objects** — never expose a setter. Value Objects must be immutable;
  mutations produce a new instance.
- **Validation in multiple places** — if `EmailAddress.create()` exists, nothing else
  should contain an email regex. A single authoritative constructor is the whole point.
- **Using interfaces instead of classes** — TypeScript interfaces are structurally
  typed; `interface UserId { value: string }` and `interface OrderId { value: string }`
  are compatible. Classes with the `_brand` trick are not.
- **Throwing on every validation failure** — functions like `findUser` call `parse()`
  on DB data; a malformed row should throw (it is a programmer/data error). Functions
  that receive user input should use `create()` and return a `Result`.
- **Fat Value Objects** — a `User` with 10 fields is not a Value Object; it is an
  Entity. Keep Value Objects narrow — one concept, one primitive, its invariants, and
  a few pieces of derived behaviour.

---

## Gotchas

- `toJSON()` is called by `JSON.stringify` but not by Cloudflare's internal
  serialisers (e.g., when a Durable Object serialises its alarm state). Always
  `.value` unwrap before storing to DO storage.
- The `_brand` field is declared but never assigned — it only exists in the type
  system. The compiled JS has no `_brand` property at runtime. Do not check for it
  at runtime.
- `Money.fromMajorUnits(1.1, "USD")` → 110 cents. `Math.round` handles the
  floating-point imprecision of `1.1 * 100 = 110.00000000000001`. Never use
  `Math.floor` or direct integer cast.
- Tree-shaking: Value Object classes are referenced by type and value. Bundlers
  keep the full class. If bundle size matters, consider plain factory functions
  (`createUserId`) that return branded primitives instead of class instances.

---

## Verification

```typescript
// __tests__/domain.test.ts (Vitest)
import { describe, it, expect } from "vitest";
import { EmailAddress } from "../domain/EmailAddress";
import { Money } from "../domain/Money";
import { UserId } from "../domain/UserId";

describe("EmailAddress", () => {
  it("accepts valid emails", () => {
    const r = EmailAddress.create("  User@Example.COM  ");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.value).toBe("user@example.com");
  });

  it("rejects invalid emails", () => {
    expect(EmailAddress.create("not-an-email").ok).toBe(false);
    expect(EmailAddress.create("").ok).toBe(false);
  });

  it("exposes domain and localPart", () => {
    const email = EmailAddress.parse("alice@example.com");
    expect(email.domain).toBe("example.com");
    expect(email.localPart).toBe("alice");
  });
});

describe("Money", () => {
  it("adds amounts in the same currency", () => {
    const a = Money.fromCents(100, "USD");
    const b = Money.fromCents(250, "USD");
    if (a.ok && b.ok) {
      expect(a.value.add(b.value).cents).toBe(350);
    }
  });

  it("throws when adding different currencies", () => {
    const usd = Money.fromCents(100, "USD");
    const eur = Money.fromCents(100, "EUR");
    if (usd.ok && eur.ok) {
      expect(() => usd.value.add(eur.value)).toThrow();
    }
  });
});
```

---

## Related

- `specification-pattern-d1-query-building.md` — combining domain predicates into D1 queries
- `unit-of-work-pattern-d1-workers.md` — collecting domain changes before a single D1 commit
- `repository-pattern.md` — the layer that reconstructs domain types from raw DB rows
- `error-codes-and-responses.md` — surfacing Value Object validation errors as RFC 7807 problem details

---

## Sources

- Evans, E. "Domain-Driven Design: Tackling Complexity in the Heart of Software" (Addison-Wesley, 2003) — Chapter 5
- Milewski, B. "Domain Modeling Made Functional" (Pragmatic Programmers, 2018)
- TypeScript Handbook — Branded Types: www.typescriptlang.org/play#example/nominal-typing
- Cloudflare Workers TypeScript — developers.cloudflare.com/workers/languages/typescript/
