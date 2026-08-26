# cloudflare-workflows-2026

- **Issue**: Cloudflare Workflows went GA in 2024 and got a major 2026 capability: **Dynamic Workflows** (MIT-licensed, May 2026) that let you ship per-tenant, per-agent durable code at runtime — the workflow code itself is data, not a deploy.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; supplements `documentation/categories/cloudflare/workflows-best-practices.md`.

## Symptom

- You want a long-running process (an approval flow, a retry loop, an agent that waits hours for human input) on Cloudflare. You wired up a Durable Object and hand-rolled sleep, retry, and state persistence.
- You want different workflow logic per tenant but your current platform makes you deploy one binding per workflow class per tenant. You have 40 bindings.
- An agent wants to write its own `run(event, step)` function as a durable plan, with every step independently retryable and every sleep hibernating for free.

## Root cause (the 2026 capability set)

### Workflows GA recap

Cloudflare Workflows is a **durable execution engine** on Workers. Each `step.do(...)` is independently retriable, state is auto-persisted, `step.sleep(...)` and `step.sleepUntil(...)` put the workflow to sleep without paying for compute, and `step.waitForEvent(...)` blocks until an external event arrives (webhook, approval, queue message).

Pricing (post-September-15-2025):
- **Workers Free**: 10 ms CPU per Workflow, 100,000 Workflow invocations per day (shared with Workers), 1 GB storage.
- **Workers Paid**: 30 million CPU ms included per month, 10 million invocations included per month, 1 GB storage. State expires after **30 days** (Free: 3 days) by default.

You do not pay for time your application is just waiting.

### Dynamic Workflows (May 2026)

A platform used to need one binding, one workflow class, per deploy. **Dynamic Workflows** (MIT-licensed npm package `@cloudflare/dynamic-workflows`, built on top of Dynamic Workers, open beta on Workers Paid) removes that constraint: a platform can route every `create()` call to a different tenant's code, and the engine dispatches `run(event, step)` back to that same code when the workflow executes seconds, hours, or days later.

The shape:

```
Agent platform  ─►  env.WORKFLOWS.create(...)    ─►  Worker Loader
                                                          │
                                                          ▼
                                                  Workflows engine
                                                  (persists payload)
                                                          │
                                                  wakes up hours later
                                                          │
                                                          ▼
                                                  Worker Loader routes
                                                  to correct tenant code
                                                  (Dynamic Worker)
```

Workflow IDs, pause/resume, retries, hibernation, `step.sleep('24 hours')`, and `step.waitForEvent()` all work unchanged. The platform loads the code dynamically, and each step runs with full durable execution semantics.

### Why this matters for agent platforms

An agent can literally **write its own `run(event, step)` function** as a durable plan, where every step is independently retryable, every sleep hibernates for free, and every `waitForEvent` pauses indefinitely for human approval. The agent writes the plan; the platform runs it. Neither needs to know ahead of time what the plan looks like.

## Patterns

### A step-based workflow

```ts
import { WorkflowEntrypoint } from "cloudflare:workflows";

export class CheckoutWorkflow extends WorkflowEntrypoint {
  async run(event, step) {
    const payment = await step.do("submit payment", async () => {
      const r = await submitToPaymentProcessor(event.params.payment);
      return r.json();
    });
    await step.do("send confirmation", sendConfirmation);
    await step.sleep("wait for feedback", "2 days");
    await step.do("send feedback email", sendFeedbackEmail);
    await step.sleep("delay before marketing", "30 days");
    await step.do("send marketing follow up", sendFollowUp);
  }
}
```

### Sleep and retry config

```ts
await step.do("call flaky api", fn, {
  retries: {
    limit: 10,
    delay: "10 seconds",
    backoff: "exponential",
  },
  timeout: "30 seconds",
});
```

`delay` may be a fixed number (ms), a string (`"10 seconds"`), or a function that takes `(ctx, error)` and returns a duration — useful for rate-limit-aware backoff.

### Wait for an event

```ts
const approval = await step.waitForEvent("approval", { type: "approval", timeout: "7 days" });
if (!approval) throw new NonRetryableError("approval timeout");
```

You can race multiple events with `Promise.race` and discriminate on `type`.

### Per-tenant durable plan (Dynamic Workflows)

```ts
// Platform code
import { DynamicWorkflow } from "@cloudflare/dynamic-workflows";

const result = await env.WORKFLOWS.create({
  id: `tenant-${tenantId}-${planId}`,
  params: { plan: agentPlan, tenantId },
});
// Worker Loader routes the eventual `run(event, step)` to that tenant's Dynamic Worker.
```

```ts
// Tenant's Dynamic Worker (loaded dynamically)
export class TenantPlanWorkflow extends DynamicWorkflow {
  async run(event, step) {
    const a = await step.do("step A", () => tenantA());
    await step.sleep("human approval", "12 hours");
    const b = await step.do("step B", () => tenantB(a));
    return b;
  }
}
```

### Rollback handlers

Throw `NonRetryableError` to fail without retry; earlier steps' registered rollback handlers still run.

## Verification

- **Cold start p95** — first invocation of a workflow class should warm in < 1 s.
- **Resume p95** — a workflow resuming from sleep or waitForEvent should be < 500 ms.
- **Retry correctness** — fixture a step that throws N times; verify it retries up to the limit, then either fails or succeeds based on policy.
- **Sleep duration accuracy** — fixture a 1-hour sleep; verify it wakes at 1 hour ± a few seconds.
- **WaitForEvent timeout** — fixture a `waitForEvent` with no incoming event; verify it times out cleanly.
- **State persistence** — fixture a step that returns 1 MB of state; verify subsequent steps see the full state.
- **Storage expiration** — verify the 30-day (Paid) or 3-day (Free) expiration behavior.

## Gotchas

- **Step retry limit is 10,000 per step.** Don't try to retry forever.
- **Storage expires by default** (30 days Paid, 3 days Free). Workflows that need longer state retention should persist externally to R2 or D1.
- **Free plan concurrent limit is shared with Workers.** Workflows on the Free plan can starve your Workers.
- **Dynamic Workflows is open beta on Workers Paid.** Free plan not yet supported.
- **The Worker Loader is the platform's responsibility** — Dynamic Workflows is a library, not a managed service. You wire the routing.
- **Sleep and waitForEvent cost $0 compute** — that is the whole point. If you see CPU billing for a sleeping workflow, something is wrong.
- **State lives in the workflow's built-in local DB.** There is no external database; do not try to query it from outside.
- **A `waitForEvent` with a past timestamp** returns the event immediately if it was sent before the workflow started waiting. Otherwise it waits.

## Related

- `documentation/categories/cloudflare/workflows-best-practices.md` — pre-2026 patterns
- `documentation/categories/cloudflare/durable-objects-best-practices.md` — the lower-level primitive
- `documentation/categories/cloudflare/workers-queues-patterns.md` — for non-durable async work
- `documentation/categories/cloudflare/agents-sdk-best-practices.md` — agents + workflows together
- `documentation/categories/lessons/human-in-the-loop.md` — `waitForEvent` is the durable HITL primitive

## Source URLs (verified 2026-08-09)

- "Cloudflare Workflows is now GA" — https://blog.cloudflare.com/workflows-ga-production-ready-durable-execution/
- "Sleeping and retrying" (Workflows docs) — https://developers.cloudflare.com/workflows/build/sleeping-and-retrying/
- "Cloudflare Ships Dynamic Workflows" (InfoQ, 2026-05) — https://www.infoq.com/news/2026/05/cloudflare-dynamic-workflows/
- "Cloudflare Workflows - Durable Execution Engine" — https://www.cloudflare.com/products/workflows/
- Workflows overview docs — https://developers.cloudflare.com/workflows/
- `@cloudflare/dynamic-workflows` npm — https://www.npmjs.com/package/@cloudflare/dynamic-workflows
