# Cloudflare Workflows Deploy State Machine Versioning

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a long-running Cloudflare Workflow (multi-step durable execution) in production
and need to ship a new version of the state machine logic without corrupting in-flight
instances. A naive `wrangler deploy` overwrites the running class and breaks every workflow
instance that is mid-sleep or waiting on an external event.

---

## Context

Cloudflare Workflows (GA 2025) run inside a Workers class that extends `WorkflowEntrypoint`.
Unlike a stateless Worker, a Workflow instance persists its execution state—steps completed,
return values stored—across arbitrary wall-clock time. The runtime replays the step log
against the current code on every wake, so a code change that alters completed-step
signatures causes immediate replay failures.

Key primitives:

- `workflow_class` binding in `wrangler.toml` maps a binding name to a class export.
- Instances are created with `env.MY_WORKFLOW.create({ id, params })`.
- Worker Versions (Gradual Rollouts API) apply to the surrounding Worker but do **not**
  protect in-flight Workflow instances from a class-level change.
- `instance.status()` returns `{ status: "running" | "complete" | "errored" | "terminated" }`.

---

## Versioned Class Strategy

The safest versioning model is to maintain parallel named classes for each breaking change.

```toml
# wrangler.toml
name = "order-processor"
compatibility_date = "2026-01-01"

[[workflows]]
name = "ORDER_FLOW_V1"
binding = "ORDER_FLOW_V1"
class_name = "OrderFlowV1"

[[workflows]]
name = "ORDER_FLOW_V2"
binding = "ORDER_FLOW_V2"
class_name = "OrderFlowV2"
```

```typescript
// src/workflows/order-flow-v1.ts
import { WorkflowEntrypoint, WorkflowStep, WorkflowEvent } from "cloudflare:workers";

export interface OrderParams {
  orderId: string;
  userId: string;
}

export class OrderFlowV1 extends WorkflowEntrypoint<Env, OrderParams> {
  async run(event: WorkflowEvent<OrderParams>, step: WorkflowStep) {
    const charge = await step.do("charge-card", async () => {
      return await chargeCard(event.payload.orderId);
    });

    await step.do("send-confirmation", async () => {
      return await sendEmail(event.payload.userId, charge.receiptId);
    });
  }
}

// src/workflows/order-flow-v2.ts  — adds a fraud-check step
export class OrderFlowV2 extends WorkflowEntrypoint<Env, OrderParams> {
  async run(event: WorkflowEvent<OrderParams>, step: WorkflowStep) {
    // New step: fraud check before charging
    const fraud = await step.do("fraud-check", async () => {
      return await checkFraud(event.payload.userId);
    });

    if (fraud.blocked) {
      return { blocked: true, reason: fraud.reason };
    }

    const charge = await step.do("charge-card", async () => {
      return await chargeCard(event.payload.orderId);
    });

    await step.do("send-confirmation", async () => {
      return await sendEmail(event.payload.userId, charge.receiptId);
    });
  }
}
```

```typescript
// src/index.ts  — dispatcher picks version per new instance
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{ orderId: string; userId: string }>();

    // New orders always get V2; existing in-flight instances remain on V1.
    const instance = await env.ORDER_FLOW_V2.create({
      id: `order-${body.orderId}`,
      params: body,
    });

    return Response.json({ instanceId: instance.id });
  },
};

export { OrderFlowV1, OrderFlowV2 };
```

---

## Drain Gate: Waiting for V1 Instances to Complete

Before removing the V1 class, confirm no instances remain running.

```typescript
// scripts/drain-workflow-v1.ts
// Run via: npx ts-node scripts/drain-workflow-v1.ts
// Requires CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID env vars.

const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const WORKFLOW_NAME = "ORDER_FLOW_V1";

async function countRunning(): Promise<number> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workflows/${WORKFLOW_NAME}/instances?status=running`,
    { headers: { Authorization: `Bearer ${TOKEN}` } }
  );
  const json = (await res.json()) as { result: { instances: unknown[] } };
  return json.result.instances.length;
}

async function drainGate(maxWaitMs = 30 * 60 * 1000): Promise<void> {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const running = await countRunning();
    console.log(`[drain] V1 running instances: ${running}`);
    if (running === 0) {
      console.log("[drain] All V1 instances complete. Safe to remove class.");
      return;
    }
    await new Promise((r) => setTimeout(r, 30_000));
  }
  throw new Error("Drain timeout: V1 instances still running after 30 minutes");
}

drainGate().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
```

---

## CI/CD Pipeline: Rolling Class Promotion

```yaml
# .github/workflows/deploy-workflow.yml
name: Deploy Cloudflare Workflow

on:
  push:
    branches: [main]

jobs:
  deploy-new-version:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy Worker (both V1 + V2 classes present)
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  drain-old-version:
    needs: deploy-new-version
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install deps
        run: npm ci

      - name: Wait for V1 drain
        run: npx ts-node scripts/drain-workflow-v1.ts
        timeout-minutes: 45
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  remove-old-class:
    needs: drain-old-version
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Remove V1 binding from wrangler.toml and redeploy
        run: |
          # Strip the V1 workflow block from config (idempotent sed)
          sed -i '/ORDER_FLOW_V1/,+4d' wrangler.toml
          npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Step Name Compatibility Rules

Replay safety depends on step names. These rules must be enforced in code review:

| Change type | Safe? | Notes |
|---|---|---|
| Add a new step at the end | Yes | Existing instances skip straight to the new step on next wake |
| Rename a completed step | No | Runtime treats it as a new step; old result is lost |
| Change a step's return type | No | Replay will deserialize wrong shape |
| Add a step before existing steps | No | Shifts all step indices |
| Change retry config on a step | Yes | Only affects future attempts |

Enforce step name stability with a TypeScript type test:

```typescript
// src/workflows/order-flow-v2.test-types.ts
import type { OrderFlowV2 } from "./order-flow-v2";

// Compile-time guard: ensure known step names are stable
type StepNames = "fraud-check" | "charge-card" | "send-confirmation";
// If you accidentally rename a step, update this union and add a migration note.
type _assertSteps = StepNames extends string ? true : never;
```

---

## Terminating Stuck Instances Before Removal

If an older version has stuck (error-looping) instances, terminate them before removing
the class to avoid log noise and billing.

```typescript
// scripts/terminate-v1-errors.ts
async function terminateErrored(): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workflows/${WORKFLOW_NAME}/instances?status=errored`,
    { headers: { Authorization: `Bearer ${TOKEN}` } }
  );
  const { result } = (await res.json()) as { result: { instances: Array<{ id: string }> } };

  for (const inst of result.instances) {
    await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workflows/${WORKFLOW_NAME}/instances/${inst.id}/terminate`,
      { method: "POST", headers: { Authorization: `Bearer ${TOKEN}` } }
    );
    console.log(`Terminated errored instance: ${inst.id}`);
  }
}
```

---

## Anti-patterns

- **Editing step logic in-place without a version bump** — Any change that alters a
  completed step's output shape or name corrupts in-flight instances silently.
- **Deploying V2 before V1 drain** — Instances created on V1 logic will replay against V2
  code and fail if step names differ.
- **Using `Date.now()` inside a step for idempotency keys** — Steps replay; wall-clock
  time varies across replays. Use `event.timestamp` or a deterministic hash.
- **Keeping >2 class versions in wrangler.toml long-term** — Binding slots add cold-start
  overhead; prune aggressively.

---

## Gotchas

- `step.sleep()` durations are stored in the replay log. Changing a sleep duration mid-
  flight has no effect on running instances; it only applies to new instances.
- The Workflows API `GET /instances` endpoint is eventually consistent; allow ~5 seconds
  after instance completion before relying on a zero count.
- Workflow class names in `wrangler.toml` must match the exported class name exactly
  (case-sensitive). A mismatch causes a silent deploy with no Workflow binding at runtime.
- Instances created with `env.WORKFLOW.create({ id })` are idempotent on `id`; re-creating
  with the same ID returns the existing instance, not a new one.

---

## Verification

```bash
# Confirm both workflow bindings are live
npx wrangler workflows list

# Check V1 instance count post-deploy
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workflows/ORDER_FLOW_V1/instances?status=running" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.instances | length'

# Trigger a smoke test V2 instance
curl -X POST https://order-processor.example.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"orderId":"test-001","userId":"u-smoke"}' | jq .instanceId
```

---

## Related

- `worker-versioning-gradual-rollout.md`
- `durable-objects-live-migration-deploy-strategy.md`
- `durable-objects-namespace-migration-zero-downtime.md`
- `workers-binding-version-management.md`
- `d1-zero-downtime-schema-migration-workers-compatibility.md`

---

## Sources

- https://developers.cloudflare.com/workflows/
- https://developers.cloudflare.com/workflows/reference/state-and-storage/
- https://developers.cloudflare.com/workflows/reference/api/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
