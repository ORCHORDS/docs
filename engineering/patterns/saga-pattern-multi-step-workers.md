# saga-pattern-multi-step-workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

A user purchases a example project Pro subscription on a mobile device.
The checkout flow must:
1. Reserve the plan slot (inventory)
2. Charge the payment method (Stripe)
3. Provision the tenant upgrade (D1 write)
4. Send a confirmation email (Mailgun)

Step 3 completes but the Worker crashes before step 4. On retry,
steps 1-3 run again. The user gets charged twice and their tenant
state is applied twice. Support escalates.

## Context

Cloudflare Workers do not have persistent long-running processes —
each invocation is stateless and bound to a wall-clock limit.
A multi-step mutation that spans external services and D1 cannot
rely on a single database transaction for atomicity.

The Saga pattern replaces distributed atomicity with a sequence of
local transactions and compensating actions. A Durable Object
acts as the saga coordinator: it holds durable state across
the steps and survives Worker restarts.

This document covers the **orchestration** variant (a single
coordinator drives all steps), which is easier to monitor and
debug than choreography for payment flows.

## Saga State Machine

```
PENDING
  │
  ▼
RESERVE_PLAN ──(fail)──► COMPENSATE_RESERVE ──► FAILED
  │
  ▼
CHARGE_PAYMENT ──(fail)──► COMPENSATE_CHARGE ──► FAILED
  │
  ▼
PROVISION_TENANT ──(fail)──► COMPENSATE_PROVISION ──► FAILED
  │
  ▼
SEND_EMAIL ──(fail, no compensate — irreversible)──► EMAIL_FAILED (loggable, not critical)
  │
  ▼
COMPLETE
```

Each step is idempotent. The coordinator stores the current step
and result of each completed step in Durable Object storage.

## Durable Object Coordinator

```ts
export class SubscriptionSaga implements DurableObject {
  constructor(private readonly state: DurableObjectState, private readonly env: Env) {}

  async fetch(req: Request): Promise<Response> {
    const body = await req.json<SagaRequest>();
    switch (body.action) {
      case 'start':  return this.start(body.context);
      case 'status': return this.status();
      default:       return Response.json({ error: 'unknown_action' }, { status: 400 });
    }
  }

  private async start(ctx: SagaContext): Promise<Response> {
    const existing = await this.state.storage.get<SagaState>('saga');
    if (existing?.step === 'COMPLETE') {
      return Response.json(existing); // idempotent: already done
    }

    const saga: SagaState = existing ?? {
      sagaId: ctx.sagaId,
      tenantId: ctx.tenantId,
      planId: ctx.planId,
      paymentMethodId: ctx.paymentMethodId,
      step: 'PENDING',
      reservationId: null,
      chargeId: null,
      startedAt: Date.now(),
      completedAt: null,
      error: null,
    };

    await this.state.storage.put('saga', saga);

    // Execute steps sequentially — each step reads the saved saga
    // so resuming after a crash continues from the right point
    try {
      if (saga.step === 'PENDING' || saga.step === 'RESERVE_PLAN') {
        await this.stepReservePlan(saga);
      }
      if (saga.step === 'CHARGE_PAYMENT') {
        await this.stepCharge(saga);
      }
      if (saga.step === 'PROVISION_TENANT') {
        await this.stepProvision(saga);
      }
      if (saga.step === 'SEND_EMAIL') {
        await this.stepEmail(saga);
      }
    } catch (err: any) {
      // Compensation runs in the catch path
      await this.compensate(saga, err);
      return Response.json(saga, { status: 500 });
    }

    return Response.json(saga);
  }

  private async stepReservePlan(saga: SagaState): Promise<void> {
    saga.step = 'RESERVE_PLAN';
    await this.state.storage.put('saga', saga);

    // Idempotent reservation — returns existing if already reserved
    const reservationId = await reservePlan(this.env, saga.planId, saga.sagaId);
    saga.reservationId = reservationId;
    saga.step = 'CHARGE_PAYMENT';
    await this.state.storage.put('saga', saga);
  }

  private async stepCharge(saga: SagaState): Promise<void> {
    // Idempotency key ties this charge to the saga — safe to retry
    const chargeId = await chargePayment(
      this.env,
      saga.paymentMethodId,
      saga.sagaId,  // used as Stripe idempotency key
    );
    saga.chargeId = chargeId;
    saga.step = 'PROVISION_TENANT';
    await this.state.storage.put('saga', saga);
  }

  private async stepProvision(saga: SagaState): Promise<void> {
    await provisionTenant(this.env, saga.tenantId, saga.planId, saga.sagaId);
    saga.step = 'SEND_EMAIL';
    await this.state.storage.put('saga', saga);
  }

  private async stepEmail(saga: SagaState): Promise<void> {
    // Best-effort: email failure does not roll back the saga
    try {
      await sendConfirmationEmail(this.env, saga.tenantId);
    } catch {
      // Log but continue
    }
    saga.step = 'COMPLETE';
    saga.completedAt = Date.now();
    await this.state.storage.put('saga', saga);
  }

  private async compensate(saga: SagaState, err: Error): Promise<void> {
    saga.error = err.message;
    // Reverse steps in order
    if (saga.chargeId) {
      await refundCharge(this.env, saga.chargeId).catch(() => {/* log; manual queue */});
    }
    if (saga.reservationId) {
      await releaseReservation(this.env, saga.reservationId).catch(() => {});
    }
    saga.step = 'FAILED';
    await this.state.storage.put('saga', saga);
  }

  private async status(): Promise<Response> {
    const saga = await this.state.storage.get<SagaState>('saga');
    return Response.json(saga ?? { error: 'not_found' }, { status: saga ? 200 : 404 });
  }
}
```

## Invoking the Saga from a Worker

```ts
export async function handleCheckout(req: Request, env: Env, ctx: McContext): Promise<Response> {
  const body = await req.json<CheckoutBody>();

  // Saga ID = idempotency key for the entire checkout attempt
  const sagaId = req.headers.get('Idempotency-Key') ?? crypto.randomUUID();

  // One DO per saga — name is the sagaId
  const id = env.SUBSCRIPTION_SAGA.idFromName(sagaId);
  const coordinator = env.SUBSCRIPTION_SAGA.get(id);

  const result = await coordinator.fetch(new Request('https://do/saga', {
    method: 'POST',
    body: JSON.stringify({
      action: 'start',
      context: {
        sagaId,
        tenantId: ctx.tenant.id,
        planId: body.plan_id,
        paymentMethodId: body.payment_method_id,
      },
    }),
  }));

  const sagaState = await result.json<SagaState>();

  if (sagaState.step === 'COMPLETE') return Response.json({ sagaId, status: 'complete' }, { status: 201 });
  if (sagaState.step === 'FAILED')   return Response.json({ sagaId, status: 'failed', error: sagaState.error }, { status: 409 });
  return Response.json({ sagaId, status: 'in_progress' }, { status: 202 });
}
```

## Compensating Transaction Table

| Step               | Forward action         | Compensating action          | Reversible? |
|--------------------|------------------------|------------------------------|-------------|
| Reserve plan slot  | Mark slot reserved     | Release reservation          | Yes         |
| Charge payment     | Stripe charge          | Stripe refund (chargeId)     | Yes (24h)   |
| Provision tenant   | D1 plan upgrade row    | D1 downgrade row (same txn)  | Yes         |
| Send email         | POST to Mailgun        | Cannot unsend                | No (log it) |

Irreversible steps (email) must come last. Accept the failure and
alert; never let an irreversible step block compensation of earlier
reversible steps.

## Mobile Payment Saga UX

The mobile client polls the saga status endpoint with exponential
backoff. The saga step is surfaced in the UI:

```ts
const STEP_LABELS: Record<string, string> = {
  PENDING:           'Starting checkout…',
  RESERVE_PLAN:      'Reserving your plan…',
  CHARGE_PAYMENT:    'Processing payment…',
  PROVISION_TENANT:  'Activating subscription…',
  SEND_EMAIL:        'Sending confirmation…',
  COMPLETE:          'All done!',
  FAILED:            'Checkout failed — please try again.',
};

async function pollSagaStatus(sagaId: string): Promise<void> {
  let delay = 500;
  for (let attempt = 0; attempt < 12; attempt++) {
    const res = await fetch(`/v1/checkout/${sagaId}/status`);
    const { step } = await res.json<{ step: string }>();
    updateUI(STEP_LABELS[step] ?? step);
    if (step === 'COMPLETE' || step === 'FAILED') return;
    await sleep(delay);
    delay = Math.min(delay * 1.5, 5_000);
  }
}
```

## Anti-patterns

- **Synchronous multi-step saga in a single Worker.** The 30s
  wall-clock limit will fire on slow external calls. Use a DO.
- **No idempotency on individual steps.** If a step runs twice,
  the user is charged twice. Each step must be idempotent.
- **Compensation without logging.** If the refund fails, there
  is no record. Log compensation failures to a dead-letter D1
  table for manual resolution.
- **Email as a non-last step.** Irreversible steps must be the
  last action so compensation can unwind everything before them.
- **Sharing one DO instance across all sagas.** Name the DO by
  `sagaId`, not by `tenantId`, so each checkout gets its own
  isolated coordinator.

## Gotchas

- DO storage has a 128KB value limit per key. If saga state
  grows (e.g. storing full API responses), store references to
  D1 rows instead of raw responses in the saga object.
- Cloudflare Workflows (2025+) is the managed alternative to
  hand-rolled DO sagas. Evaluate it first for new projects —
  it handles retries, timeouts, and state persistence natively.
- A stuck saga (DO never reaches COMPLETE or FAILED) is invisible
  without monitoring. Log every step transition and alert on sagas
  older than 5 minutes without completing.
- Stripe idempotency keys expire after 24 hours. A saga that
  stays in `CHARGE_PAYMENT` for >24 hours must generate a new
  Stripe idempotency key.

## Verification

```bash
# Start a checkout
SAGA_ID=$(uuidgen)
curl -s -X POST https://api.example.com/v1/checkout \
  -H "Idempotency-Key: $SAGA_ID" \
  -H "Content-Type: application/json" \
  -d '{"plan_id":"pro","payment_method_id":"pm_test_visa"}'

# Poll status
curl -s https://api.example.com/v1/checkout/${SAGA_ID}/status | jq .step

# Retry same checkout — should replay from stored step
curl -s -X POST https://api.example.com/v1/checkout \
  -H "Idempotency-Key: $SAGA_ID" \
  -d '{"plan_id":"pro","payment_method_id":"pm_test_visa"}' | jq .step
# Expected: "COMPLETE" (idempotent replay)
```

## Related

- `saga-pattern.md` — generic saga pattern reference
- `idempotency-key-pattern-workers-d1.md` — idempotency at each step
- `per-tenant-durable-object.md` — DO patterns for Workers
- `event-sourcing-cloudflare-workers-d1.md` — saga steps as events

## Sources

- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare Workflows: https://developers.cloudflare.com/workflows/
- Chris Richardson, Saga Pattern: https://microservices.io/patterns/data/saga.html
- Release It! — Michael T. Nygard (Chapter 5)
