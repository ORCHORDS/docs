# workflows-best-practices

**Issue:** Cloudflare Workflows — durable execution, retries, steps
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a multi-step user onboarding flow that takes
days. The user signs up, gets a welcome email, fills
out their profile, gets a tutorial, etc. You put it
all in a Worker. The Worker times out. Half the flow
breaks.

## Root cause
**Long-running, multi-step processes don't fit in a
single Worker.** Use Cloudflare Workflows.

**Source:** CF Workflows docs:
https://developers.cloudflare.com/workflows/

## The "Workflow" concept

A Workflow is a durable execution engine:
- **Step-based:** Every step is retryable + memoized
- **Stateful:** State persists automatically
- **Long-running:** Minutes, hours, days, weeks
- **Event-aware:** Can wait for webhooks + approvals

The workflow "keeps going" past a single request.

## The "Workflow class" pattern

For a Workflow:
```ts
import { WorkflowEntrypoint, WorkflowStep, WorkflowEvent } from 'cloudflare:workers';

type Params = { userId: string };
type State = { emailSent: boolean; profileCompleted: boolean };

export class OnboardingWorkflow extends WorkflowEntrypoint<Env, Params> {
  async run(event: WorkflowEvent<Params>, step: WorkflowStep) {
    // Each step is durable
    const user = await step.do('load user', async () => {
      return getUser(event.payload.userId, this.env);
    });

    await step.do('send welcome email', async () => {
      await sendEmail(user.email, { subject: 'Welcome!' }, this.env);
    });

    // Wait for the user to complete their profile
    const profile = await step.waitForEvent('wait for profile', {
      type: 'profile.completed',
      timeout: '7 days',
    });

    await step.do('send tutorial', async () => {
      await sendEmail(user.email, { subject: 'Tutorial' }, this.env);
    });
  }
}
```

Each step is durable + retryable.

## The "Workflow binding" pattern

For the binding:
```toml
[[workflows]]
name = "onboarding"
binding = "ONBOARDING"
class_name = "OnboardingWorkflow"
```

The binding is in `wrangler.toml`.

## The "create" pattern

For creating a workflow:
```ts
const instance = await env.ONBOARDING.create({
  params: { userId: 'u_123' },
});

console.log(instance.id, instance.status);
```

The workflow is created.

## The "step.do" pattern

For a durable step:
```ts
const result = await step.do('operation name', async () => {
  return await doWork(this.env);
});
```

The step is retryable + memoized.

## The "step.sleep" pattern

For sleep:
```ts
await step.sleep('wait 1 day', '1 day');
await step.sleep('wait 1 hour', '1 hour');
await step.sleep('wait 30 seconds', '30 seconds');
```

The workflow sleeps.

## The "step.waitForEvent" pattern

For waiting for an event:
```ts
const result = await step.waitForEvent<ProfileEvent>('wait for profile', {
  type: 'profile.completed',
  timeout: '7 days',
});
```

The workflow waits.

```ts
// Trigger the event from elsewhere
await env.ONBOARDING.get(instanceId).sendEvent({
  type: 'profile.completed',
  payload: { ... },
});
```

The event is sent.

## The "idempotency" pattern

For idempotency, `step.do` is naturally idempotent:
- **First call:** Runs the function
- **Retry:** Returns the cached result

```ts
const result = await step.do('charge user', async () => {
  // Even if this is retried, only charges once
  return await chargeUser(amount);
});
```

The step is idempotent.

## The "Dynamic Workflows" pattern (new 2026)

For per-tenant code:
```ts
import { createDynamicWorkflow, DynamicWorkflow } from '@cloudflare/dynamic-workflows';

// Worker Loader: routes to the right tenant
const workflow = createDynamicWorkflow<Params>(env, 'onboarding');
const instance = await workflow.create({ params: { userId } });
```

The workflow is per-tenant.

**Source:** Dynamic Workflows:
https://blog.cloudflare.com/dynamic-workflows/

## The "Workflow limits" pattern

For limits:
- **Concurrent instances:** 50,000 (V2)
- **New instances:** 300 per second
- **Step duration:** Configurable
- **State storage:** Per instance

The limits are checked.

## The "Workflow observability" pattern

For observability:
- **Step status:** Pending / running / completed / failed
- **Retry count:** Per step
- **Instance status:** Per workflow
- **Logs:** Per step

The metrics are in the CF dashboard.

## The "Workflow error handling" pattern

For errors, retries are automatic:
```ts
await step.do('risky operation', {
  retries: {
    limit: 5,
    delay: '1 second',
    backoff: 'exponential',
  },
  timeout: '5 minutes',
}, async () => {
  return await doRiskyWork();
});
```

The step is retried.

## The "Workflow vs Queue" choice

| Use case | Use |
|---|---|
| **Long-running, multi-step** | Workflow |
| **One-off async task** | Queue |
| **Need to wait for events** | Workflow |
| **Parallel processing** | Queue |
| **State machine** | Workflow |

For most multi-step flows, **Workflow** is the right answer.

## The "Workflow anti-pattern" anti-patterns

### 1. Long-running in Worker
- **Issue:** Worker timeout
- **Fix:** Workflow

### 2. No retries
- **Issue:** Transient failure = lost
- **Fix:** Use step.do with retries

### 3. No events
- **Issue:** Can't wait for human
- **Fix:** step.waitForEvent

### 4. No idempotency
- **Issue:** Retries do the work twice
- **Fix:** step.do (naturally idempotent)

## Verification
- **Test:** Workflow completes
- **Test:** Step is retried
- **Test:** Sleep works
- **Test:** waitForEvent works
- **Live:** Workflow status is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "long-running in Worker" anti-pattern.** Use
  Workflow.
- **The "no retries" anti-pattern.** Use step.do.
- **The "no events" anti-pattern.** Use waitForEvent.

## Related
- `cloudflare/workers-workers-queues-patterns.md`
- `cloudflare/durable-objects-best-practices.md`
- `feature-cookbook-saga.md`
- `feature-cookbook-onboarding.md`
- CF Workflows: https://developers.cloudflare.com/workflows/
- Dynamic Workflows: https://blog.cloudflare.com/dynamic-workflows/
