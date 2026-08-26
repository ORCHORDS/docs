# Command Pattern: Workers Queues Action Log

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project needs a reliable, replayable record of every user action — upvotes, post creations, follows, reports — for audit trails, undo support, and analytics fan-out. Executing these actions inline in the request handler couples latency to downstream writes and drops history when a step fails halfway through.

## Context

Cloudflare Queues decouple the command from its execution: the Worker serialises a command object and enqueues it; a consumer Worker processes it durably with automatic retry. D1 stores the canonical action log; KV provides a fast read-side projection. The pattern lets new consumers (notifications, ranking) subscribe without touching the producer.

## Pattern Overview — Command Interface

Each action is a typed command object with a stable `type` discriminant. Commands are serialised to JSON for queue transport and stored verbatim in D1 as the source of truth.

```typescript
// commands/types.ts
export type ActionCommand =
  | { type: 'UPVOTE';        postId: string; authorHash: string; ts: number }
  | { type: 'CREATE_POST';   postId: string; boardSlug: string;  body: string;   authorHash: string; ts: number }
  | { type: 'FOLLOW_BOARD';  boardSlug: string; authorHash: string; ts: number }
  | { type: 'REPORT_CONTENT'; contentId: string; reason: string; reporterHash: string; ts: number }
  | { type: 'DELETE_POST';   postId: string; actorHash: string; ts: number };

export interface CommandHandler<T extends ActionCommand> {
  handle(cmd: T, env: Env): Promise<void>;
}

export interface Env {
  DB:           D1Database;
  KV:           KVNamespace;
  ACTION_QUEUE: Queue<ActionCommand>;
}
```

## Implementation — Concrete Command Handlers

Each handler is a pure class responsible for one command type. Handlers can be tested independently by injecting mock `Env` bindings.

```typescript
// commands/handlers/upvote.ts
import { CommandHandler, Env, ActionCommand } from '../types';

type UpvoteCmd = Extract<ActionCommand, { type: 'UPVOTE' }>;

export class UpvoteHandler implements CommandHandler<UpvoteCmd> {
  async handle(cmd: UpvoteCmd, env: Env): Promise<void> {
    // Idempotent upsert — replay-safe
    await env.DB
      .prepare(`
        INSERT INTO upvotes (post_id, author_hash, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT (post_id, author_hash) DO NOTHING
      `)
      .bind(cmd.postId, cmd.authorHash, cmd.ts)
      .run();

    // Update KV counter for fast reads
    const key   = `upvotes:${cmd.postId}`;
    const raw   = await env.KV.get(key);
    const count = raw ? parseInt(raw, 10) + 1 : 1;
    await env.KV.put(key, String(count), { expirationTtl: 86_400 });
  }
}

// commands/handlers/create-post.ts
import { CommandHandler, Env, ActionCommand } from '../types';

type CreatePostCmd = Extract<ActionCommand, { type: 'CREATE_POST' }>;

export class CreatePostHandler implements CommandHandler<CreatePostCmd> {
  async handle(cmd: CreatePostCmd, env: Env): Promise<void> {
    await env.DB
      .prepare(`
        INSERT INTO posts (id, board_slug, body, author_hash, created_at, moderation_status)
        VALUES (?, ?, ?, ?, ?, 'pending')
        ON CONFLICT (id) DO NOTHING
      `)
      .bind(cmd.postId, cmd.boardSlug, cmd.body, cmd.authorHash, cmd.ts)
      .run();
  }
}

// commands/handlers/report-content.ts
import { CommandHandler, Env, ActionCommand } from '../types';

type ReportCmd = Extract<ActionCommand, { type: 'REPORT_CONTENT' }>;

export class ReportContentHandler implements CommandHandler<ReportCmd> {
  async handle(cmd: ReportCmd, env: Env): Promise<void> {
    await env.DB
      .prepare(`
        INSERT INTO reports (content_id, reason, reporter_hash, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (content_id, reporter_hash) DO NOTHING
      `)
      .bind(cmd.contentId, cmd.reason, cmd.reporterHash, cmd.ts)
      .run();

    // Auto-escalate when report threshold reached
    const { results } = await env.DB
      .prepare('SELECT COUNT(*) as cnt FROM reports WHERE content_id = ?')
      .bind(cmd.contentId)
      .all<{ cnt: number }>();

    if ((results[0]?.cnt ?? 0) >= 5) {
      await env.DB
        .prepare(`UPDATE content SET moderation_status = 'under_review' WHERE id = ?`)
        .bind(cmd.contentId)
        .run();
    }
  }
}
```

## Workers Integration — Producer and Consumer

The producer Worker serialises the command and appends it to D1 before enqueuing, ensuring the log is written even if the queue send fails.

```typescript
// producer-worker.ts
import { ActionCommand, Env } from './commands/types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('', { status: 405 });

    const cmd = (await request.json()) as ActionCommand;
    cmd.ts ??= Date.now();

    // Append to D1 action log first — durable before queue send
    await env.DB
      .prepare('INSERT INTO action_log (type, payload, queued_at) VALUES (?, ?, ?)')
      .bind(cmd.type, JSON.stringify(cmd), cmd.ts)
      .run();

    await env.ACTION_QUEUE.send(cmd);
    return Response.json({ ok: true, queued: cmd.type }, { status: 202 });
  },
};

// consumer-worker.ts
import { ActionCommand, Env } from './commands/types';
import { UpvoteHandler }        from './commands/handlers/upvote';
import { CreatePostHandler }    from './commands/handlers/create-post';
import { ReportContentHandler } from './commands/handlers/report-content';

type AnyHandler = { handle(cmd: ActionCommand, env: Env): Promise<void> };

const registry = new Map<ActionCommand['type'], AnyHandler>([
  ['UPVOTE',          new UpvoteHandler()],
  ['CREATE_POST',     new CreatePostHandler()],
  ['REPORT_CONTENT',  new ReportContentHandler()],
]);

export default {
  async queue(batch: MessageBatch<ActionCommand>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const handler = registry.get(msg.body.type);
      if (!handler) {
        // Unknown command type — ack to avoid infinite retry
        msg.ack();
        console.warn('No handler for command:', msg.body.type);
        continue;
      }
      try {
        await handler.handle(msg.body, env);
        msg.ack();
      } catch (err) {
        // Retry — msg.retry() is the default on throw, explicit here for clarity
        console.error('Command failed, will retry:', msg.body.type, err);
        msg.retry();
      }
    }
  },
};
```

## Anti-patterns

- Mutating the command object before enqueuing — the D1 log and the queue payload must be identical; serialise once, use twice
- Using a single giant handler with nested `switch` — one class per command type keeps handlers unit-testable and independently deployable
- Skipping the D1 pre-write — if the queue send fails, the action is lost; write-before-enqueue gives at-least-once delivery at the log level
- Storing large blobs (e.g., full post HTML) in the queue message — keep messages small; store large content in R2 and put only the key in the command

## Gotchas

- Cloudflare Queues deliver at-least-once; handlers must be idempotent (`ON CONFLICT DO NOTHING` in D1 inserts achieves this)
- `batch.messages` may contain a mix of command types if multiple producers share one queue; the registry pattern handles this cleanly
- `msg.retry()` respects the queue's `max_retries` and `delay_seconds` settings in `wrangler.toml`; set sensible values to avoid thundering herds
- D1 is eventually consistent between replicas — use `DB.prepare().run()` (not `.first()`) for writes; reads after writes in the same Worker invocation may not reflect the write yet in read replicas

## Verification

```bash
# Publish a command locally
curl -X POST http://localhost:8787/ \
  -H 'Content-Type: application/json' \
  -d '{"type":"UPVOTE","postId":"post-1","authorHash":"h1"}'
# Expect: {"ok":true,"queued":"UPVOTE"}

# Check action_log
npx wrangler d1 execute example project-db --local \
  --command "SELECT * FROM action_log ORDER BY queued_at DESC LIMIT 5"

# Replay a failed command (re-enqueue from log)
npx wrangler d1 execute example project-db --local \
  --command "SELECT payload FROM action_log WHERE type='UPVOTE' LIMIT 1" \
  | jq -r '.[0].results[0].payload' | curl -X POST http://localhost:8787/ -d @-
```

## Related

- `event-sourcing-cloudflare-workers-d1.md` — using the action log as the authoritative event stream
- `dead-letter-queue-pattern.md` — handling commands that exhaust retries
- `competing-consumers-workers-queues.md` — scaling queue consumers horizontally
- `idempotency-key-pattern-workers-d1.md` — preventing duplicate command execution
- `outbox-pattern-d1-reliable-publishing.md` — alternative transactional outbox instead of pre-write

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/batching-retries/
- https://developers.cloudflare.com/d1/
- https://refactoring.guru/design-patterns/command
