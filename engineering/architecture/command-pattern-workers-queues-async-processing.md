# Command Pattern: Workers + Queues Async Processing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

HTTP request handlers must complete within Cloudflare's 30-second CPU limit, but business operations like bulk email dispatch, report generation, or data-export pipelines routinely exceed that budget. You need a way to enqueue a richly described operation so a background consumer can execute it reliably and idempotently, with full retry semantics, without the caller waiting.

## Context

The Command pattern encapsulates a request as a serialisable object that carries everything the executor needs: the operation name, its arguments, metadata for idempotency, and an optional correlation id. On Cloudflare this maps naturally to Cloudflare Queues: the Worker that receives the HTTP request publishes a command message; a separate consumer Worker (or the same Worker in its `queue` handler) deserialises and dispatches it. Because Queue messages are durably stored and retried automatically, the pattern gives you at-least-once execution without a dedicated scheduler.

## Command Schema and Publisher

```typescript
// types/commands.ts
export type CommandName =
  | "SEND_BULK_EMAIL"
  | "GENERATE_REPORT"
  | "EXPORT_DATASET"
  | "SYNC_INVENTORY";

export interface Command<N extends CommandName = CommandName, P = unknown> {
  id: string;           // UUIDv4 — idempotency key
  name: N;
  payload: P;
  issuedAt: string;     // ISO-8601
  correlationId?: string;
  retryCount?: number;  // populated by consumer on each attempt
}

export interface SendBulkEmailPayload {
  templateId: string;
  recipientListId: string;
  scheduledAt?: string;
}

// api/handler.ts
import { Command, SendBulkEmailPayload } from "../types/commands";

export async function handleSendBulkEmailRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{ templateId: string; recipientListId: string }>();

  const command: Command<"SEND_BULK_EMAIL", SendBulkEmailPayload> = {
    id: crypto.randomUUID(),
    name: "SEND_BULK_EMAIL",
    payload: {
      templateId: body.templateId,
      recipientListId: body.recipientListId,
    },
    issuedAt: new Date().toISOString(),
    correlationId: request.headers.get("x-correlation-id") ?? undefined,
  };

  await env.COMMAND_QUEUE.send(command);

  return Response.json({ commandId: command.id, status: "QUEUED" }, { status: 202 });
}
```

## Command Registry and Consumer

```typescript
// commands/registry.ts
import { Command } from "../types/commands";

type Handler<P> = (payload: P, env: Env) => Promise<void>;

const registry = new Map<string, Handler<unknown>>();

export function registerCommand<P>(name: string, handler: Handler<P>): void {
  registry.set(name, handler as Handler<unknown>);
}

export async function dispatchCommand(command: Command, env: Env): Promise<void> {
  const handler = registry.get(command.name);
  if (!handler) {
    throw new Error(`No handler registered for command: ${command.name}`);
  }
  await handler(command.payload, env);
}

// commands/handlers/send-bulk-email.ts
import { registerCommand } from "../registry";
import { SendBulkEmailPayload } from "../../types/commands";

registerCommand<SendBulkEmailPayload>("SEND_BULK_EMAIL", async (payload, env) => {
  // Idempotency check via D1
  const existing = await env.DB.prepare(
    "SELECT id FROM email_jobs WHERE id = ?"
  ).first<{ id: string }>();

  if (existing) return; // already processed

  const recipients = await env.DB.prepare(
    "SELECT email FROM recipient_lists WHERE list_id = ?"
  ).bind(payload.recipientListId).all<{ email: string }>();

  for (const { email } of recipients.results) {
    await env.EMAIL_QUEUE.send({ templateId: payload.templateId, to: email });
  }

  await env.DB.prepare(
    "INSERT INTO email_jobs (id, template_id, list_id, completed_at) VALUES (?, ?, ?, ?)"
  ).bind(crypto.randomUUID(), payload.templateId, payload.recipientListId, new Date().toISOString()).run();
});

// worker.ts — queue consumer entry point
import "./commands/handlers/send-bulk-email";
import "./commands/handlers/generate-report";
import { dispatchCommand } from "./commands/registry";
import { Command } from "./types/commands";

export default {
  async queue(batch: MessageBatch<Command>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await dispatchCommand(message.body, env);
        message.ack();
      } catch (err) {
        console.error("Command failed", { id: message.body.id, error: String(err) });
        message.retry({ delaySeconds: Math.min(60 * 2 ** (message.body.retryCount ?? 0), 3600) });
      }
    }
  },
};
```

## Idempotency Tracking in D1

```typescript
// lib/idempotency.ts
export async function ensureOnce(
  commandId: string,
  commandName: string,
  env: Env,
  fn: () => Promise<void>
): Promise<void> {
  const inserted = await env.DB.prepare(`
    INSERT OR IGNORE INTO processed_commands (id, name, processed_at)
    VALUES (?, ?, ?)
  `).bind(commandId, commandName, new Date().toISOString()).run();

  // changes === 0 means the row already existed — skip execution
  if (inserted.meta.changes === 0) {
    console.log("Skipping duplicate command", commandId);
    return;
  }

  try {
    await fn();
  } catch (err) {
    // Roll back the idempotency record so the command can be retried
    await env.DB.prepare("DELETE FROM processed_commands WHERE id = ?")
      .bind(commandId).run();
    throw err;
  }
}
```

## Anti-patterns

- Putting mutable DB state into the command payload instead of fetching it fresh inside the handler — the payload may be stale by execution time.
- Skipping the idempotency check and relying solely on Queue's at-least-once delivery guarantee, leading to double sends or duplicate writes.
- Using a single monolithic `switch` block to dispatch commands instead of a registry; it couples all handlers and prevents tree-shaking.

## Gotchas

- Cloudflare Queues deliver messages in batches; handlers must `ack()` or `retry()` each message individually or the entire batch is retried after the visibility timeout.
- Exponential backoff via `retry({ delaySeconds })` only works when the consumer explicitly calls `message.retry()`; if the consumer throws without calling either, the default retry schedule applies.

## Verification

```bash
# Publish a test command and tail the consumer logs
curl -X POST https://api.example.com/emails/bulk \
  -H "Content-Type: application/json" \
  -H "x-correlation-id: test-001" \
  -d '{"templateId":"t_welcome","recipientListId":"list_beta"}'

wrangler tail --format pretty

# Check idempotency table
wrangler d1 execute DB --command "SELECT * FROM processed_commands ORDER BY processed_at DESC LIMIT 10;"
```

## Related

- `architecture/outbox-pattern.md`
- `architecture/dead-letter-queue-architecture.md`
- `architecture/async-job-queue-cloudflare-queues-do.md`
- `architecture/idempotency-design.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://refactoring.guru/design-patterns/command
- https://developers.cloudflare.com/d1/
