# Policy Pattern — Workers Domain Rules

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Business rules like "free shipping applies when cart total exceeds $50 AND the
customer is a loyalty member AND no hazardous items are present" keep leaking into
HTTP handlers, queue consumers, and D1 queries simultaneously. Each copy drifts.
A bug fix in one place leaves another stale. You need a first-class, named, testable
unit that encodes a single business rule and can be composed with other rules.

## Context

The **Policy** (also called *Specification* in some DDD literature, or *Rule* in
Evans) is a domain object with one responsibility: answer a yes/no question about
a domain concept. Policies are:

- **Named** after the business rule, not after their implementation.
- **Composable** — `and`, `or`, `not` combinators produce new policies from existing
  ones without touching the originals.
- **Side-effect-free** — evaluation reads state but never writes it.
- **Testable** in isolation without HTTP or database infrastructure.

In Workers, stateless policies live in plain TypeScript modules; policies that need
remote data (KV, D1, service binding) are async and receive an `Env` context.

## Core Policy Interface

```typescript
// domain/policy.ts
export interface Policy<T> {
  readonly name: string;
  isSatisfiedBy(candidate: T, env?: Env): Promise<boolean>;
}

export function and<T>(...policies: Policy<T>[]): Policy<T> {
  return {
    name: policies.map(p => p.name).join(' AND '),
    async isSatisfiedBy(candidate, env) {
      for (const p of policies) {
        if (!(await p.isSatisfiedBy(candidate, env))) return false;
      }
      return true;
    },
  };
}

export function or<T>(...policies: Policy<T>[]): Policy<T> {
  return {
    name: policies.map(p => p.name).join(' OR '),
    async isSatisfiedBy(candidate, env) {
      for (const p of policies) {
        if (await p.isSatisfiedBy(candidate, env)) return true;
      }
      return false;
    },
  };
}

export function not<T>(policy: Policy<T>): Policy<T> {
  return {
    name: `NOT (${policy.name})`,
    async isSatisfiedBy(candidate, env) {
      return !(await policy.isSatisfiedBy(candidate, env));
    },
  };
}
```

## Concrete Domain Policies

```typescript
// domain/policies/free-shipping-policies.ts
import type { Cart, Env } from '../types';
import type { Policy } from '../policy';

export const CartExceedsFreeShippingThreshold: Policy<Cart> = {
  name: 'CartExceedsFreeShippingThreshold',
  async isSatisfiedBy(cart) {
    return cart.subtotalCents >= 5000; // $50.00
  },
};

export const CustomerIsLoyaltyMember: Policy<Cart> = {
  name: 'CustomerIsLoyaltyMember',
  async isSatisfiedBy(cart, env) {
    const raw = await env!.KV.get(`loyalty:${cart.customerId}`);
    return raw !== null;
  },
};

export const CartContainsNoHazardousItems: Policy<Cart> = {
  name: 'CartContainsNoHazardousItems',
  async isSatisfiedBy(cart) {
    return !cart.items.some(i => i.hazardous);
  },
};
```

## Composing Policies into Business Rules

Named composite policies preserve the business vocabulary at the call site.

```typescript
// domain/policies/shipping-policy.ts
import { and } from '../policy';
import {
  CartExceedsFreeShippingThreshold,
  CustomerIsLoyaltyMember,
  CartContainsNoHazardousItems,
} from './free-shipping-policies';

export const EligibleForFreeShipping = and(
  CartExceedsFreeShippingThreshold,
  CustomerIsLoyaltyMember,
  CartContainsNoHazardousItems,
);
// EligibleForFreeShipping.name ===
//   'CartExceedsFreeShippingThreshold AND CustomerIsLoyaltyMember AND CartContainsNoHazardousItems'
```

## Applying Policies in a Worker Handler

```typescript
// handlers/checkout.ts
import { EligibleForFreeShipping } from '../domain/policies/shipping-policy';

export async function handleCheckout(request: Request, env: Env): Promise<Response> {
  const cart: Cart = await request.json();

  const freeShipping = await EligibleForFreeShipping.isSatisfiedBy(cart, env);
  const shippingCost = freeShipping ? 0 : calculateShipping(cart);

  return Response.json({
    subtotal: cart.subtotalCents,
    shipping: shippingCost,
    appliedPolicy: freeShipping ? EligibleForFreeShipping.name : null,
  });
}
```

## Policy as a Queue Gate

Queue consumers use policies to decide whether to process or skip a message, keeping
routing logic out of the consumer body.

```typescript
// consumers/order-confirmation.ts
import { EligibleForFreeShipping } from '../domain/policies/shipping-policy';

export default {
  async queue(batch: MessageBatch<OrderPlacedEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { cart } = msg.body;
      const addFreeShippingBadge = await EligibleForFreeShipping.isSatisfiedBy(cart, env);

      await sendConfirmationEmail({
        ...msg.body,
        freeShipping: addFreeShippingBadge,
        env,
      });
      msg.ack();
    }
  },
};
```

## Policy Audit Logging

When policies gate high-stakes decisions, log the policy name and result to D1 for
audit trails.

```typescript
async function evaluateAndAudit<T>(
  policy: Policy<T>,
  candidate: T,
  env: Env,
  context: string,
): Promise<boolean> {
  const result = await policy.isSatisfiedBy(candidate, env);
  await env.DB.prepare(
    `INSERT INTO policy_audit (policy_name, context, result, evaluated_at)
     VALUES (?, ?, ?, ?)`,
  )
    .bind(policy.name, context, result ? 1 : 0, new Date().toISOString())
    .run();
  return result;
}
```

## Anti-patterns

- **Inline boolean logic in handlers** — `if (cart.total > 50 && loyalty && !hazardous)`
  is unnamed, untestable, and duplicated; always wrap it in a named Policy object.
- **Policies with side effects** — a policy that sends an email or writes to D1 during
  evaluation is no longer a pure predicate; extract the side effect to the caller.
- **God policy** — one policy that encodes every business rule; break it into focused
  single-responsibility policies and compose them.
- **Hardcoded thresholds in policy bodies** — thresholds that change with business
  rules should come from KV config or constructor injection, not magic numbers.

## Gotchas

- Async policies that call KV or D1 add latency to every evaluation; cache results
  in the Worker's in-memory scope when the same policy is evaluated multiple times in
  a single request.
- Composition combinators short-circuit (`and` stops on first false, `or` on first
  true); ensure side-effect-free inner policies do not rely on all of them being
  evaluated.
- The `name` property of composite policies can grow long; truncate it in audit logs
  rather than shortening the composed name (the full name is the documentation).
- Policy evaluation inside a Durable Object that holds a lock can block other requests
  to the same DO; keep policy evaluation fast or move it to the calling Worker.

## Verification

```bash
# Unit-test policies without Workers runtime
npx vitest run src/domain/policies/

# Confirm composite name equals expected label
node -e "
const { EligibleForFreeShipping } = require('./dist/domain/policies/shipping-policy');
console.assert(EligibleForFreeShipping.name.includes('CartExceedsFreeShippingThreshold'));
"

# Check audit table for recent policy decisions
wrangler d1 execute DB \
  --command "SELECT policy_name, result, COUNT(*) FROM policy_audit GROUP BY 1,2"
```

## Related

- `specification-pattern-workers-d1-query-building.md`
- `domain-service-pattern-workers-d1.md`
- `value-objects.md`
- `bounded-context-design.md`
- `domain-events.md`

## Sources

- Eric Evans, *Domain-Driven Design*, ch. 9 (Specification)
- Martin Fowler, *Specification* pattern — https://martinfowler.com/apsupp/spec.pdf
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
