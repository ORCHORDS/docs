# Retry Budget Pattern — Workers Queues

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers Queue consumer retries a failing message up to `maxRetries` times, but that budget is shared with every message on the queue. Under a partial outage an upstream dependency starts failing at 30 %; now every message burns through its full retry allowance, flooding the queue with exponentially more attempts, starving healthy messages, and turning a recoverable blip into a sustained queue storm.

The retry *budget* pattern decouples "how many times may *all messages in a window* retry" from "how many times may *this one message* retry". A Durable Object tracks aggregate retry spend; once the budget is exhausted new messages are park-delayed rather than immediately re-enqueued.

---

## Context

Cloudflare Queues allow up to 3 `retryAll()` / per-message `retry()` calls before a message is dead-lettered. The consumer receives a `MessageBatch`; each `Message` exposes `.retry()` and `.ack()`. There is no built-in cross-message budget. Durable Objects provide the low-latency shared counter and alarm needed to replenish the budget each window.

---

## Budget Counter Durable Object

```typescript
// src/retry-budget.ts
export class RetryBudget implements DurableObject {
  private budget: number;
  private readonly WINDOW_MS = 60_000;
  private readonly MAX_BUDGET = 50;

  constructor(private state: DurableObjectState) {
    this.budget = this.MAX_BUDGET;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/consume') {
      const cost = Number(url.searchParams.get('cost') ?? '1');
      if (this.budget >= cost) {
        this.budget -= cost;
        await this.state.storage.put('budget', this.budget);
        return Response.json({ allowed: true, remaining: this.budget });
      }
      return Response.json({ allowed: false, remaining: this.budget }, { status: 429 });
    }

    if (url.pathname === '/replenish') {
      this.budget = this.MAX_BUDGET;
      await this.state.storage.put('budget', this.budget);
      await this.state.storage.deleteAlarm();
      return Response.json({ budget: this.budget });
    }

    return new Response('Not found', { status: 404 });
  }

  async alarm(): Promise<void> {
    // Window expired — replenish automatically
    this.budget = this.MAX_BUDGET;
    await this.state.storage.put('budget', this.budget);
  }

  async initialize(): Promise<void> {
    const stored = await this.state.storage.get<number>('budget');
    this.budget = stored ?? this.MAX_BUDGET;
    const alarm = await this.state.storage.getAlarm();
    if (!alarm) {
      await this.state.storage.setAlarm(Date.now() + this.WINDOW_MS);
    }
  }
}
```

---

## Queue Consumer with Budget Check

```typescript
// src/queue-consumer.ts
import type { MessageBatch, Message } from '@cloudflare/workers-types';

interface Env {
  RETRY_BUDGET: DurableObjectNamespace;
  MY_QUEUE: Queue;
}

async function checkRetryBudget(env: Env, cost = 1): Promise<boolean> {
  const id = env.RETRY_BUDGET.idFromName('global');
  const stub = env.RETRY_BUDGET.get(id);
  const resp = await stub.fetch(`http://do/consume?cost=${cost}`);
  const { allowed } = await resp.json<{ allowed: boolean }>();
  return allowed;
}

export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processMessage(message);
        message.ack();
      } catch (err) {
        const attemptsUsed = message.attempts; // 1-based
        const remainingAttempts = 3 - attemptsUsed;

        if (remainingAttempts <= 0) {
          // Let it dead-letter — no budget needed
          message.retry();
          continue;
        }

        const budgetAvailable = await checkRetryBudget(env);
        if (budgetAvailable) {
          message.retry({ delaySeconds: backoffSeconds(attemptsUsed) });
        } else {
          // Park the message with maximum delay to not spam the queue
          message.retry({ delaySeconds: 300 });
        }
      }
    }
  },
};

function backoffSeconds(attempt: number): number {
  return Math.min(2 ** attempt * 5, 120);
}

async function processMessage(message: Message): Promise<void> {
  // business logic
}
```

---

## Budget Initialisation on Cold Start

```typescript
// Ensure the alarm is armed on first access
export class RetryBudget implements DurableObject {
  constructor(private state: DurableObjectState) {
    // blockConcurrencyWhile guarantees single-flight init
    this.state.blockConcurrencyWhile(async () => {
      const stored = await this.state.storage.get<number>('budget');
      this.budget = stored ?? this.MAX_BUDGET;
      const alarm = await this.state.storage.getAlarm();
      if (!alarm) {
        await this.state.storage.setAlarm(Date.now() + this.WINDOW_MS);
      }
    });
  }
  private budget = 50;
  private readonly WINDOW_MS = 60_000;
  private readonly MAX_BUDGET = 50;
  // ...fetch and alarm as above
}
```

---

## Wrangler Configuration

```toml
# wrangler.toml
[[queues.consumers]]
queue = "my-queue"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "my-dlq"

[[durable_objects.bindings]]
name = "RETRY_BUDGET"
class_name = "RetryBudget"

[[migrations]]
tag = "v1"
new_classes = ["RetryBudget"]
```

---

## Per-Message-Type Budget Segmentation

Different message types have different costs. High-value payment events should never be starved by cheaper notification retries.

```typescript
type MessageType = 'payment' | 'notification' | 'analytics';

const BUDGET_COST: Record<MessageType, number> = {
  payment: 1,        // always allowed — low volume
  notification: 3,   // medium cost
  analytics: 10,     // batch retries are expensive
};

async function checkTypedBudget(env: Env, type: MessageType): Promise<boolean> {
  const cost = BUDGET_COST[type];
  const id = env.RETRY_BUDGET.idFromName(`segment:${type}`);
  const stub = env.RETRY_BUDGET.get(id);
  const resp = await stub.fetch(`http://do/consume?cost=${cost}`);
  const { allowed } = await resp.json<{ allowed: boolean }>();
  return allowed;
}
```

---

## Anti-patterns

- **Ignoring `message.attempts`**: checking the budget even on the final permitted attempt wastes budget on a message that will dead-letter regardless.
- **Shared singleton for multi-queue setups**: name the DO by queue name, not just `'global'`, or one queue's storm exhausts budget for all.
- **Replenishing too fast**: a 10-second window turns the budget into noise. Windows of 60 s–5 min match real outage recovery cycles.
- **Storing budget in KV**: KV eventual consistency means two Workers can both read the same value and both decrement past zero. The DO serialises all access.

---

## Gotchas

- `message.attempts` is 1-indexed: on the first delivery it is `1`, not `0`.
- Durable Object alarms fire *at least once*, not exactly once. Make `alarm()` idempotent (setting budget to `MAX_BUDGET` always works).
- `message.retry({ delaySeconds })` requires Queues with delay support enabled; ensure `compatibility_date` >= `2023-03-01`.
- The DO `fetch` call inside a queue consumer counts against the 50 subrequest limit per invocation.

---

## Verification

```bash
# Publish 200 messages that will fail
npx wrangler queues publish --queue my-queue --messages "$(seq 1 200 | jq -nR '[inputs | {body: .}]')"

# Tail worker logs and verify "park" (delaySeconds=300) appears after budget
# exhaustion rather than immediate retries
npx wrangler tail --format pretty

# Check DO budget state
curl https://my-worker.example.workers.dev/__debug/budget
# {"allowed":false,"remaining":0}
```

---

## Related

- `exponential-backoff-jitter-workers.md`
- `dead-letter-queue-pattern.md`
- `adaptive-backpressure-workers-queues.md`
- `priority-queue-workers-queues.md`
- `token-bucket-durable-objects.md`

---

## Sources

- Cloudflare Queues docs — `maxRetries`, `retry()`, `delaySeconds` (2026)
- AWS re:Invent 2019, "Retry Budgets" — Marc Brooker
- Release It!, Michael Nygard — ch. 5 Stability Patterns
