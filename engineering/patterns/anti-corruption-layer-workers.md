# Anti-Corruption Layer: Workers as External API Translation Boundary

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your application integrates with a third-party API (payment provider, ERP, CRM, legacy service) whose data model, naming conventions, error codes, and authentication scheme differ from your own domain model. Over time, the external model bleeds into your codebase: you reference their field names, check their error codes, and build logic around their quirks. A provider switch means touching dozens of files.

Classic signs:
- Variable names like `stripeCustomerId`, `hubspotContactId`, `salesforceOpportunityExternalId` scattered across your domain layer
- Third-party HTTP errors handled with `if (err.code === "card_declined")` deep in business logic
- A provider migration causes a 2-week rewrite
- Tests mock the third-party HTTP API directly rather than an internal interface

---

## Context

The Anti-Corruption Layer (ACL) is a DDD tactical pattern. A Workers service binding (or a dedicated subdomain Worker) acts as the translation boundary: it speaks the external provider's protocol inbound, translates to your domain model, and exposes a stable internal API to the rest of your system. Your domain code never imports or knows about the external provider.

```
Your Workers ──(service binding)──▶ ACL Worker ──(fetch)──▶ Stripe / Salesforce / Legacy API
                                       │
                                  translates:
                                  - request shape
                                  - response shape
                                  - auth headers
                                  - error codes → domain errors
```

---

## Defining the Domain Interface

```typescript
// src/billing/types.ts — your domain model, zero provider terms
export interface Customer {
  customerId: string;           // your internal ID
  email: string;
  planId: string;
  status: "active" | "past_due" | "cancelled";
  trialEndsAt: string | null;
}

export interface PaymentResult {
  success: boolean;
  chargeId: string;             // your internal charge reference
  errorCode?: "insufficient_funds" | "card_expired" | "provider_error";
}

export interface BillingPort {
  getCustomer(customerId: string): Promise<Customer | null>;
  charge(customerId: string, amountCents: number, currency: string): Promise<PaymentResult>;
  cancelSubscription(customerId: string): Promise<void>;
}
```

---

## ACL Worker: Stripe Adapter

```typescript
// src/billing-acl/stripe-adapter.ts
import type { Customer, PaymentResult, BillingPort } from "../billing/types";

export interface Env {
  STRIPE_SECRET: string;
  CUSTOMER_ID_MAP: KVNamespace; // maps internal ID ↔ stripe customer ID
}

export class StripeBillingAdapter implements BillingPort {
  constructor(private env: Env) {}

  async getCustomer(customerId: string): Promise<Customer | null> {
    const stripeId = await this.env.CUSTOMER_ID_MAP.get(`internal:${customerId}`);
    if (!stripeId) return null;

    const res = await this.stripe(`/v1/customers/${stripeId}`);
    if (res.status === 404) return null;

    const sc = await res.json<StripeCustomer>();
    return this.toDomainCustomer(customerId, sc);
  }

  async charge(
    customerId: string,
    amountCents: number,
    currency: string
  ): Promise<PaymentResult> {
    const stripeId = await this.env.CUSTOMER_ID_MAP.get(`internal:${customerId}`);
    if (!stripeId) throw new Error(`No stripe mapping for ${customerId}`);

    const res = await this.stripe("/v1/payment_intents", {
      method: "POST",
      body: new URLSearchParams({
        amount: String(amountCents),
        currency,
        customer: stripeId,
        confirm: "true",
        payment_method: "pm_card_visa", // resolved externally in prod
      }),
    });

    const pi = await res.json<StripePaymentIntent | StripeError>();
    return this.toDomainPaymentResult(pi);
  }

  async cancelSubscription(customerId: string): Promise<void> {
    const stripeId = await this.env.CUSTOMER_ID_MAP.get(`internal:${customerId}`);
    if (!stripeId) return;

    const subRes = await this.stripe(
      `/v1/subscriptions?customer=${stripeId}&limit=1`
    );
    const list = await subRes.json<{ data: Array<{ id: string }> }>();
    const subId = list.data[0]?.id;
    if (!subId) return;

    await this.stripe(`/v1/subscriptions/${subId}`, { method: "DELETE" });
  }

  // ── translation helpers ──────────────────────────────────────────────────

  private toDomainCustomer(customerId: string, sc: StripeCustomer): Customer {
    return {
      customerId,
      email: sc.email,
      planId: sc.metadata?.["plan_id"] ?? "unknown",
      status: this.mapStripeStatus(sc.subscriptions?.data?.[0]?.status),
      trialEndsAt: sc.subscriptions?.data?.[0]?.trial_end
        ? new Date(sc.subscriptions.data[0].trial_end * 1000).toISOString()
        : null,
    };
  }

  private mapStripeStatus(
    s?: string
  ): Customer["status"] {
    switch (s) {
      case "active": return "active";
      case "past_due": return "past_due";
      case "canceled": return "cancelled"; // Stripe spells it differently
      default: return "cancelled";
    }
  }

  private toDomainPaymentResult(
    pi: StripePaymentIntent | StripeError
  ): PaymentResult {
    if ("error" in pi) {
      return {
        success: false,
        chargeId: "",
        errorCode: this.mapStripeDecline(pi.error.decline_code ?? pi.error.code),
      };
    }
    return { success: true, chargeId: pi.id };
  }

  private mapStripeDecline(
    code?: string
  ): PaymentResult["errorCode"] {
    if (code === "insufficient_funds") return "insufficient_funds";
    if (code === "expired_card") return "card_expired";
    return "provider_error";
  }

  private stripe(path: string, init: RequestInit = {}): Promise<Response> {
    return fetch(`https://api.stripe.com${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.env.STRIPE_SECRET}`,
        "Content-Type": "application/x-www-form-urlencoded",
        ...(init.headers ?? {}),
      },
    });
  }
}

// Stripe-specific types — contained entirely inside the ACL
interface StripeCustomer {
  id: string;
  email: string;
  metadata?: Record<string, string>;
  subscriptions?: { data: Array<{ id: string; status: string; trial_end?: number }> };
}
interface StripePaymentIntent { id: string; status: string }
interface StripeError { error: { code?: string; decline_code?: string; message: string } }
```

---

## ACL as a Service-Binding Worker

```typescript
// src/billing-acl/index.ts — exposed via service binding
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const adapter = new StripeBillingAdapter(env);

    if (request.method === "GET" && url.pathname.startsWith("/customer/")) {
      const customerId = url.pathname.split("/")[2];
      const customer = await adapter.getCustomer(customerId);
      return customer
        ? Response.json(customer)
        : new Response("Not found", { status: 404 });
    }

    if (request.method === "POST" && url.pathname === "/charge") {
      const { customerId, amountCents, currency } = await request.json<{
        customerId: string;
        amountCents: number;
        currency: string;
      }>();
      const result = await adapter.charge(customerId, amountCents, currency);
      return Response.json(result, { status: result.success ? 200 : 402 });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Consuming the ACL from Domain Workers

```typescript
// src/order-worker/index.ts — never imports Stripe
export interface Env {
  BILLING: Fetcher; // service binding to billing-acl worker
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { orderId, customerId, totalCents } = await request.json<{
      orderId: string;
      customerId: string;
      totalCents: number;
    }>();

    // Speaks only domain terms — no Stripe anywhere
    const res = await env.BILLING.fetch("https://billing/charge", {
      method: "POST",
      body: JSON.stringify({ customerId, amountCents: totalCents, currency: "usd" }),
      headers: { "Content-Type": "application/json" },
    });

    const result = await res.json<{ success: boolean; chargeId: string; errorCode?: string }>();

    if (!result.success) {
      return Response.json(
        { error: result.errorCode ?? "payment_failed" },
        { status: 402 }
      );
    }

    return Response.json({ orderId, chargeId: result.chargeId });
  },
};
```

---

## Anti-patterns

- **Leaking provider types across the ACL boundary**: If `StripeCustomer` or Stripe error codes appear in files outside the ACL, the layer is leaking. Keep provider types private to the ACL package.
- **Building the ACL as a pass-through proxy**: A proxy that just forwards requests adds latency without adding translation. The ACL must actively translate the model.
- **One ACL for all providers**: A single "integration" Worker that handles Stripe, HubSpot, and Salesforce becomes a god object. One ACL per bounded context or per provider.
- **Mocking the external API in domain tests**: Domain tests should mock the `BillingPort` interface, not Stripe's HTTP API. Testing through Stripe in unit tests couples your test suite to the external model.
- **Storing the provider's ID as your primary key**: Use a mapping table (KV or D1) between your internal ID and the provider's ID. This allows provider migration without changing your data model.

---

## Gotchas

- Service bindings bypass the internet—requests to the ACL Worker are in-process and free. However, the ACL Worker's calls to the external provider still incur network latency and count against your subrequest limit (50 per Worker invocation on free, 1000 on paid).
- KV reads for the ID mapping add latency. Cache the mapping in the Worker's module-level `Map` with a short TTL if mapping lookups are hot.
- The ACL is the right place to implement provider-specific retry and circuit-breaker logic, not the calling domain Worker. Keep error-handling concerns encapsulated.
- Stripe webhooks arrive at your public endpoint and must be translated before they reach domain Workers. Add a separate webhook ACL Worker that converts Stripe event shapes into domain events.

---

## Verification

1. Call the domain Worker and confirm no Stripe field names appear in its request/response schema.
2. Swap the `BILLING` service binding to a mock ACL Worker that returns domain-model responses; confirm domain tests pass unchanged.
3. Simulate a Stripe `card_declined` response (use a test card) and confirm the domain Worker receives `errorCode: "insufficient_funds"`, not a Stripe error object.
4. Rename a field in the Stripe response (simulate a provider API change) and confirm only the ACL Worker's translation helper needs updating.
5. Check that `src/order-worker/` contains zero imports from `stripe` or any Stripe-specific module.

---

## Related

- `strangler-fig-workers-migration.md` — gradually replacing a legacy system
- `circuit-breaker-workers-d1-fetch.md` — protecting your system from provider outages
- `correlation-id-propagation-workers.md` — tracing requests across the ACL boundary
- `error-codes-and-responses.md` — designing stable internal error vocabularies

---

## Sources

- Evans, Eric — Domain-Driven Design (2003), Chapter 14: Maintaining Model Integrity
- Fowler, Martin — Anti-Corruption Layer: https://martinfowler.com/bliki/AntiCorruptionLayer.html
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
