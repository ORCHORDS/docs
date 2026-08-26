# State Pattern: Durable Objects Moderation Workflow

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project content passes through several moderation stages — `pending`, `under_review`, `approved`, `rejected`, `appealed`, and `removed` — and the set of legal transitions differs per stage. Without a formal state machine, handlers accumulate `if` chains that allow illegal jumps (e.g., appealing already-approved content) and make it easy to forget side-effects that must fire on each transition.

## Context

Durable Objects provide a single-writer, strongly-consistent actor per entity. A `ModerationDO` holding one content item's state is the natural host for a moderation state machine: all transitions are serialised, hibernation keeps costs low between events, and the persistent `storage` API survives the DO sleeping between moderator actions.

## Pattern Overview — States and Transitions

Each state is a class implementing a `ModerationState` interface. The DO delegates every action to the current state object, which either executes the transition or throws if it is illegal.

```typescript
// moderation/state.ts
export type ModerationStatus =
  | 'pending'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'appealed'
  | 'removed';

export interface TransitionResult {
  nextStatus: ModerationStatus;
  auditEntry: string;
}

export interface ModerationState {
  readonly status: ModerationStatus;
  startReview(moderatorId: string): TransitionResult;
  approve(moderatorId: string): TransitionResult;
  reject(moderatorId: string, reason: string): TransitionResult;
  appeal(userId: string): TransitionResult;
  remove(adminId: string): TransitionResult;
}

function illegal(from: ModerationStatus, action: string): never {
  throw new Error(`Cannot ${action} from state "${from}"`);
}
```

## Implementation — Concrete State Classes

```typescript
// moderation/states/pending.ts
import { ModerationState, ModerationStatus, TransitionResult } from '../state';

export class PendingState implements ModerationState {
  readonly status: ModerationStatus = 'pending';

  startReview(moderatorId: string): TransitionResult {
    return { nextStatus: 'under_review', auditEntry: `review_started:${moderatorId}` };
  }
  approve(): TransitionResult { return illegal(this.status, 'approve'); }
  reject(): TransitionResult  { return illegal(this.status, 'reject'); }
  appeal(): TransitionResult  { return illegal(this.status, 'appeal'); }
  remove(adminId: string): TransitionResult {
    return { nextStatus: 'removed', auditEntry: `removed_by_admin:${adminId}` };
  }
}

// moderation/states/under-review.ts
import { ModerationState, ModerationStatus, TransitionResult } from '../state';

export class UnderReviewState implements ModerationState {
  readonly status: ModerationStatus = 'under_review';

  startReview(): TransitionResult { return illegal(this.status, 'startReview'); }
  approve(moderatorId: string): TransitionResult {
    return { nextStatus: 'approved', auditEntry: `approved:${moderatorId}` };
  }
  reject(moderatorId: string, reason: string): TransitionResult {
    return { nextStatus: 'rejected', auditEntry: `rejected:${moderatorId}:${reason}` };
  }
  appeal(): TransitionResult  { return illegal(this.status, 'appeal'); }
  remove(adminId: string): TransitionResult {
    return { nextStatus: 'removed', auditEntry: `removed_by_admin:${adminId}` };
  }
}

// moderation/states/rejected.ts
import { ModerationState, ModerationStatus, TransitionResult } from '../state';

export class RejectedState implements ModerationState {
  readonly status: ModerationStatus = 'rejected';

  startReview(): TransitionResult { return illegal(this.status, 'startReview'); }
  approve(): TransitionResult     { return illegal(this.status, 'approve'); }
  reject(): TransitionResult      { return illegal(this.status, 'reject'); }
  appeal(userId: string): TransitionResult {
    return { nextStatus: 'appealed', auditEntry: `appealed_by:${userId}` };
  }
  remove(adminId: string): TransitionResult {
    return { nextStatus: 'removed', auditEntry: `removed_by_admin:${adminId}` };
  }
}
```

## Durable Object Integration

The DO stores the current `ModerationStatus` string in its `storage` API and reconstructs the correct state class on each activation. All transitions are serialised automatically by the single-writer guarantee.

```typescript
// moderation/moderation-do.ts
import { PendingState }     from './states/pending';
import { UnderReviewState } from './states/under-review';
import { RejectedState }    from './states/rejected';
import { ModerationState, ModerationStatus } from './state';

interface Env { DB: D1Database; }

function stateFor(status: ModerationStatus): ModerationState {
  switch (status) {
    case 'pending':      return new PendingState();
    case 'under_review': return new UnderReviewState();
    case 'rejected':     return new RejectedState();
    // appealed re-enters under_review; approved/removed are terminal
    case 'appealed':     return new UnderReviewState();
    default:             throw new Error(`No state class for "${status}"`);
  }
}

export class ModerationDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env  = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url    = new URL(request.url);
    const action = url.searchParams.get('action') ?? '';
    const actor  = request.headers.get('x-actor-id') ?? 'unknown';
    const reason = url.searchParams.get('reason') ?? '';

    const rawStatus = (await this.state.storage.get<string>('status')) ?? 'pending';
    const current   = stateFor(rawStatus as ModerationStatus);

    let result;
    try {
      switch (action) {
        case 'start_review': result = current.startReview(actor); break;
        case 'approve':      result = current.approve(actor);     break;
        case 'reject':       result = current.reject(actor, reason); break;
        case 'appeal':       result = current.appeal(actor);      break;
        case 'remove':       result = current.remove(actor);      break;
        default:
          return new Response(JSON.stringify({ error: 'Unknown action' }), { status: 400 });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      return new Response(JSON.stringify({ error: msg }), { status: 409 });
    }

    // Persist new status and audit log atomically
    const auditLog = (await this.state.storage.get<string[]>('audit')) ?? [];
    auditLog.push(`${new Date().toISOString()} ${result.auditEntry}`);
    await this.state.storage.put('status',    result.nextStatus);
    await this.state.storage.put('audit',     auditLog);

    // Sync terminal states to D1 for query-side reads
    if (result.nextStatus === 'approved' || result.nextStatus === 'removed') {
      const contentId = url.searchParams.get('contentId') ?? '';
      await this.env.DB
        .prepare('UPDATE content SET moderation_status = ? WHERE id = ?')
        .bind(result.nextStatus, contentId)
        .run();
    }

    return Response.json({ status: result.nextStatus, audit: auditLog.at(-1) });
  }
}
```

## Anti-patterns

- Storing the entire state object graph in DO storage — only the status string is needed; reconstruct the class on activation
- Allowing direct writes to `status` from outside the DO — bypasses the legal-transition guard and breaks audit integrity
- Sharing one DO instance across multiple content items — each piece of content must have its own DO for isolation and independent hibernation
- Implementing transitions as a flat switch in the DO's `fetch` — eliminates the extensibility benefit; adding a new state requires modifying the central dispatch

## Gotchas

- Durable Object `storage.put` calls are batched per event loop tick; wrap multi-key writes in `storage.transaction()` if you need all-or-nothing semantics
- `stateFor` throws for `approved` and `removed` — callers should check status before calling the DO on terminal states to avoid unnecessary activation costs
- The `appeal` action transitions to `under_review` status; use the same `UnderReviewState` class rather than a separate `AppealedState` to avoid duplicating logic
- Alarm-based timeouts (DO alarms API) can auto-reject reviews that sit in `under_review` beyond an SLA window

## Verification

```typescript
// Vitest test
import { env } from 'cloudflare:test';

test('pending → under_review → rejected → appealed', async () => {
  const id = env.MODERATION_DO.idFromName('test-content-1');
  const stub = env.MODERATION_DO.get(id);

  let r = await stub.fetch('http://do/?action=start_review&contentId=1', {
    headers: { 'x-actor-id': 'mod1' },
  });
  expect((await r.json() as any).status).toBe('under_review');

  r = await stub.fetch('http://do/?action=reject&contentId=1&reason=spam', {
    headers: { 'x-actor-id': 'mod1' },
  });
  expect((await r.json() as any).status).toBe('rejected');

  r = await stub.fetch('http://do/?action=appeal&contentId=1', {
    headers: { 'x-actor-id': 'user42' },
  });
  expect((await r.json() as any).status).toBe('appealed');

  // Illegal: cannot approve from pending
  r = await stub.fetch('http://do/?action=approve&contentId=1');
  expect(r.status).toBe(409);
});
```

## Related

- `memento-pattern-durable-objects-state-snapshot.md` — snapshotting DO state for rollback
- `distributed-lock-durable-objects.md` — preventing concurrent action dispatch
- `event-sourcing-cloudflare-workers-d1.md` — append-only audit log as the source of truth
- `observer-pattern-workers-durable-objects-event-bus.md` — broadcasting moderation events to subscribers

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- https://developers.cloudflare.com/durable-objects/examples/alarms/
- https://refactoring.guru/design-patterns/state
