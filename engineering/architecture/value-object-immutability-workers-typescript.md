# Value Object Immutability — Workers TypeScript

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Currency amounts, email addresses, money values, coordinates, and date ranges are
passed as raw primitives (string, number) across Worker handlers, D1 queries, and
Queue messages. Validation is scattered, equality comparisons fail on structurally
identical objects, and mutating a shared "money" object in one branch silently
corrupts another. You need a way to model these concepts as first-class domain types
that are always valid and can never be changed after construction.

## Context

A **Value Object** is a domain concept identified solely by its attribute values,
not by an identity or reference. Two Money objects with the same amount and currency
are equal. Once constructed with valid state, a Value Object cannot be mutated —
any operation that "changes" it returns a **new** Value Object instead.

TypeScript's type system, combined with Cloudflare Workers' V8 isolate semantics,
makes Value Objects cheap: they are plain in-memory objects with zero I/O cost.
Freeze them at construction time and the runtime enforces the invariant structurally.

## Base Value Object Pattern

```typescript
// domain/value-object.ts
export abstract class ValueObject<T extends object> {
  protected readonly props: Readonly<T>;

  protected constructor(props: T) {
    this.props = Object.freeze({ ...props });
  }

  equals(other: ValueObject<T>): boolean {
    return JSON.stringify(this.props) === JSON.stringify(other.props);
  }

  toJSON(): T {
    return this.props;
  }
}
```

## Money Value Object

```typescript
// domain/value-objects/money.ts
import { ValueObject } from '../value-object';

interface MoneyProps {
  readonly amountCents: number;
  readonly currency: 'USD' | 'EUR' | 'GBP';
}

export class Money extends ValueObject<MoneyProps> {
  private constructor(props: MoneyProps) {
    super(props);
  }

  static create(amountCents: number, currency: MoneyProps['currency']): Money {
    if (!Number.isInteger(amountCents)) {
      throw new Error(`Money amount must be an integer of cents, got: ${amountCents}`);
    }
    if (amountCents < 0) {
      throw new Error(`Money amount cannot be negative: ${amountCents}`);
    }
    return new Money({ amountCents, currency });
  }

  get amountCents(): number { return this.props.amountCents; }
  get currency(): string { return this.props.currency; }

  add(other: Money): Money {
    if (other.currency !== this.currency) {
      throw new Error(`Cannot add ${this.currency} and ${other.currency}`);
    }
    return Money.create(this.amountCents + other.amountCents, this.props.currency);
  }

  multiply(factor: number): Money {
    return Money.create(Math.round(this.amountCents * factor), this.props.currency);
  }

  isGreaterThan(other: Money): boolean {
    return this.amountCents > other.amountCents;
  }
}
```

## Email Address Value Object

```typescript
// domain/value-objects/email-address.ts
import { ValueObject } from '../value-object';

interface EmailProps { readonly value: string }

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export class EmailAddress extends ValueObject<EmailProps> {
  private constructor(props: EmailProps) { super(props); }

  static create(raw: string): EmailAddress {
    const normalised = raw.trim().toLowerCase();
    if (!EMAIL_RE.test(normalised)) {
      throw new Error(`Invalid email address: ${raw}`);
    }
    return new EmailAddress({ value: normalised });
  }

  get value(): string { return this.props.value; }
  get domain(): string { return this.props.value.split('@')[1]; }
}
```

## DateRange Value Object

```typescript
// domain/value-objects/date-range.ts
import { ValueObject } from '../value-object';

interface DateRangeProps { readonly from: string; readonly to: string }

export class DateRange extends ValueObject<DateRangeProps> {
  private constructor(props: DateRangeProps) { super(props); }

  static create(from: Date, to: Date): DateRange {
    if (to <= from) throw new Error('DateRange: "to" must be after "from"');
    return new DateRange({
      from: from.toISOString(),
      to: to.toISOString(),
    });
  }

  get from(): Date { return new Date(this.props.from); }
  get to(): Date { return new Date(this.props.to); }

  contains(date: Date): boolean {
    return date >= this.from && date <= this.to;
  }

  overlaps(other: DateRange): boolean {
    return this.from < other.to && this.to > other.from;
  }
}
```

## Using Value Objects in a Worker Handler

```typescript
// handlers/create-subscription.ts
import { Money } from '../domain/value-objects/money';
import { EmailAddress } from '../domain/value-objects/email-address';
import { DateRange } from '../domain/value-objects/date-range';

export async function handleCreateSubscription(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<{
    email: string; priceUsd: number; startDate: string; endDate: string;
  }>();

  const email = EmailAddress.create(body.email);
  const price = Money.create(Math.round(body.priceUsd * 100), 'USD');
  const period = DateRange.create(new Date(body.startDate), new Date(body.endDate));

  await env.DB.prepare(
    `INSERT INTO subscriptions (email, price_cents, currency, period_from, period_to)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(email.value, price.amountCents, price.currency, period.from.toISOString(), period.to.toISOString())
    .run();

  return Response.json({ email: email.value, price: price.toJSON() }, { status: 201 });
}
```

## Serialising Value Objects Through Queues

```typescript
// Extend Money with fromJSON
static fromJSON(props: MoneyProps): Money {
  return Money.create(props.amountCents, props.currency);
}

// Producer
await env.PAYMENT_QUEUE.send({ amount: price.toJSON(), email: email.value });

// Consumer
const amount = Money.fromJSON(msg.body.amount);
const discounted = amount.multiply(0.9);
```

## Anti-patterns

- **Mutable VO fields** — any public setter or non-readonly property breaks the contract.
- **Identity comparison** — `voA === voB` always returns `false`; always use `.equals()`.
- **Primitive obsession** — passing raw `string` or `number` where a VO is called for.
- **Fat Value Objects with I/O** — a VO that calls KV or D1 in its constructor is no longer pure.

## Gotchas

- `Object.freeze` is shallow; nested objects remain mutable unless you deep-freeze recursively.
- JSON serialisation of class instances does not include methods; consumers must call `fromJSON`.
- Equality via `JSON.stringify` is sensitive to key insertion order.

## Verification

```bash
npx vitest run src/domain/value-objects/

wrangler d1 execute DB \
  --command "SELECT email, price_cents, currency FROM subscriptions LIMIT 100" \
  | node scripts/validate-vos.js
```

## Related

- `value-objects.md`
- `aggregate-root-pattern.md`
- `domain-service-pattern-workers-d1.md`
- `policy-pattern-workers-domain-rules.md`
- `repository-pattern-ddd.md`

## Sources

- Eric Evans, *Domain-Driven Design*, ch. 5 (Value Objects)
- TypeScript `Readonly<T>` — https://www.typescriptlang.org/docs/handbook/utility-types.html
- Cloudflare Workers TypeScript support — https://developers.cloudflare.com/workers/languages/typescript/
