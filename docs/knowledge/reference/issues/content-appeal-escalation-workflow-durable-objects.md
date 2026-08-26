# Content Appeal & Escalation Workflow (Durable Objects)

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A user whose post has been quarantined or removed by the automated rule engine needs to file an appeal. The appeal must flow through a defined lifecycle (filed → under review → escalated → resolved), with SLA timers, automatic escalation if the first-tier reviewer is idle, and a final human decision that either reinstates or confirms the removal. Stateless Workers cannot hold this lifecycle durably; Durable Objects can.

---

## Context

Each appeal is a Durable Object instance keyed on a UUID. The DO stores the full appeal state as a JSON blob in its storage. A Cron-triggered Worker periodically sweeps all active DOs via an index in D1, finds appeals that have breached their SLA, and sends an escalation message into the DO. Reviewers interact with the appeal via HTTP calls routed through a standard Worker → DO proxy.

---

## 1. Types — Appeal State Machine

```typescript
// src/types/appeal.ts
export type AppealStatus =
  | 'filed'
  | 'under_review'
  | 'escalated_tier2'
  | 'escalated_legal'
  | 'resolved_reinstated'
  | 'resolved_upheld'
  | 'withdrawn';

export type EscalationTier = 'tier1' | 'tier2' | 'legal';

export interface AppealEvent {
  timestamp: number;
  actor: string;       // reviewer ID or 'system'
  action: string;
  note?: string;
}

export interface AppealState {
  appealId: string;
  contentId: string;
  authorHash: string;
  removalReason: string;
  status: AppealStatus;
  tier: EscalationTier;
  assignedReviewer: string | null;
  filedAt: number;
  tierDeadline: number;    // Unix epoch — SLA deadline for current tier
  resolvedAt: number | null;
  events: AppealEvent[];
  userStatement: string;
}

export const SLA_HOURS: Record<EscalationTier, number> = {
  tier1:  24,
  tier2:  48,
  legal: 120,
};
```

---

## 2. Durable Object — AppealDO

```typescript
// src/durable-objects/AppealDO.ts
import { AppealState, AppealStatus, EscalationTier, SLA_HOURS, AppealEvent } from '../types/appeal';

export class AppealDO implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.pathname.split('/').pop();

    switch (action) {
      case 'init':       return this.handleInit(request);
      case 'assign':     return this.handleAssign(request);
      case 'review':     return this.handleReview(request);
      case 'escalate':   return this.handleEscalate(request);
      case 'resolve':    return this.handleResolve(request);
      case 'withdraw':   return this.handleWithdraw(request);
      case 'status':     return this.handleStatus();
      default:           return new Response('Not Found', { status: 404 });
    }
  }

  private async getAppeal(): Promise<AppealState | null> {
    return (await this.state.storage.get<AppealState>('appeal')) ?? null;
  }

  private async saveAppeal(appeal: AppealState): Promise<void> {
    await this.state.storage.put('appeal', appeal);
  }

  private nowEpoch(): number { return Math.floor(Date.now() / 1000); }

  private deadlineFromNow(tier: EscalationTier): number {
    return this.nowEpoch() + SLA_HOURS[tier] * 3600;
  }

  private addEvent(appeal: AppealState, actor: string, action: string, note?: string): void {
    const event: AppealEvent = { timestamp: this.nowEpoch(), actor, action, note };
    appeal.events.push(event);
  }

  private async handleInit(request: Request): Promise<Response> {
    const existing = await this.getAppeal();
    if (existing) return new Response('Conflict — appeal already initialised', { status: 409 });

    const body = await request.json<Omit<AppealState, 'status' | 'tier' | 'assignedReviewer' | 'filedAt' | 'tierDeadline' | 'resolvedAt' | 'events'>>();

    const appeal: AppealState = {
      ...body,
      status: 'filed',
      tier: 'tier1',
      assignedReviewer: null,
      filedAt: this.nowEpoch(),
      tierDeadline: this.deadlineFromNow('tier1'),
      resolvedAt: null,
      events: [],
    };

    this.addEvent(appeal, 'system', 'filed');
    await this.saveAppeal(appeal);
    return new Response(JSON.stringify(appeal), { status: 201 });
  }

  private async handleAssign(request: Request): Promise<Response> {
    const appeal = await this.getAppeal();
    if (!appeal) return new Response('Not Found', { status: 404 });
    if (appeal.status !== 'filed' && appeal.status !== 'escalated_tier2') {
      return new Response('Cannot assign in current state', { status: 409 });
    }

    const { reviewerId } = await request.json<{ reviewerId: string }>();
    appeal.assignedReviewer = reviewerId;
    appeal.status = 'under_review';
    this.addEvent(appeal, reviewerId, 'assigned');
    await this.saveAppeal(appeal);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }

  private async handleEscalate(request: Request): Promise<Response> {
    const appeal = await this.getAppeal();
    if (!appeal) return new Response('Not Found', { status: 404 });

    const { actor, reason, targetTier } = await request.json<{ actor: string; reason: string; targetTier: EscalationTier }>();

    const tierMap: Record<EscalationTier, AppealStatus> = {
      tier1: 'filed',          // fallback; shouldn't escalate to tier1
      tier2: 'escalated_tier2',
      legal: 'escalated_legal',
    };

    appeal.status = tierMap[targetTier];
    appeal.tier = targetTier;
    appeal.assignedReviewer = null;
    appeal.tierDeadline = this.deadlineFromNow(targetTier);
    this.addEvent(appeal, actor, `escalated_to_${targetTier}`, reason);
    await this.saveAppeal(appeal);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }

  private async handleReview(request: Request): Promise<Response> {
    const appeal = await this.getAppeal();
    if (!appeal || appeal.status !== 'under_review') {
      return new Response('Not in reviewable state', { status: 409 });
    }
    // Record reviewer note without resolving
    const { actor, note } = await request.json<{ actor: string; note: string }>();
    this.addEvent(appeal, actor, 'reviewed', note);
    await this.saveAppeal(appeal);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }

  private async handleResolve(request: Request): Promise<Response> {
    const appeal = await this.getAppeal();
    if (!appeal) return new Response('Not Found', { status: 404 });

    const terminalStates: AppealStatus[] = ['resolved_reinstated', 'resolved_upheld', 'withdrawn'];
    if (terminalStates.includes(appeal.status)) {
      return new Response('Appeal already resolved', { status: 409 });
    }

    const { actor, decision, note } = await request.json<{ actor: string; decision: 'reinstate' | 'uphold'; note?: string }>();
    appeal.status = decision === 'reinstate' ? 'resolved_reinstated' : 'resolved_upheld';
    appeal.resolvedAt = this.nowEpoch();
    this.addEvent(appeal, actor, `resolved_${decision}`, note);
    await this.saveAppeal(appeal);
    return new Response(JSON.stringify({ ok: true, status: appeal.status }), { status: 200 });
  }

  private async handleWithdraw(request: Request): Promise<Response> {
    const appeal = await this.getAppeal();
    if (!appeal) return new Response('Not Found', { status: 404 });
    const { actor } = await request.json<{ actor: string }>();
    appeal.status = 'withdrawn';
    appeal.resolvedAt = this.nowEpoch();
    this.addEvent(appeal, actor, 'withdrawn');
    await this.saveAppeal(appeal);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  }

  private async handleStatus(): Promise<Response> {
    const appeal = await this.getAppeal();
    if (!appeal) return new Response('Not Found', { status: 404 });
    return new Response(JSON.stringify(appeal), { status: 200 });
  }
}
```

---

## 3. Appeal Index in D1 — for Cron Sweep

```sql
-- migrations/0031_appeal_index.sql
CREATE TABLE IF NOT EXISTS appeal_index (
  appeal_id     TEXT    PRIMARY KEY,
  status        TEXT    NOT NULL,
  tier          TEXT    NOT NULL,
  tier_deadline INTEGER NOT NULL,
  content_id    TEXT    NOT NULL,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_ai_active_deadline ON appeal_index(status, tier_deadline)
  WHERE status NOT IN ('resolved_reinstated','resolved_upheld','withdrawn');
```

---

## 4. SLA Escalation Cron Worker

```typescript
// src/cron/appeal-sla-sweep.ts
import { Env } from '../types';

interface AppealIndexRow {
  appeal_id: string;
  tier: string;
  tier_deadline: number;
}

export async function sweepSlaBreaches(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  const { results } = await env.DB.prepare(
    `SELECT appeal_id, tier, tier_deadline
       FROM appeal_index
      WHERE status NOT IN ('resolved_reinstated','resolved_upheld','withdrawn')
        AND tier_deadline < ?`
  )
    .bind(now)
    .all<AppealIndexRow>();

  for (const row of results) {
    const targetTier = row.tier === 'tier1' ? 'tier2' : 'legal';

    const doId = env.APPEAL_DO.idFromName(row.appeal_id);
    const stub = env.APPEAL_DO.get(doId);

    const resp = await stub.fetch(`https://do/appeal/escalate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actor: 'system', reason: 'sla_breach', targetTier }),
    });

    if (resp.ok) {
      await env.DB.prepare(
        `UPDATE appeal_index SET status = ?, tier = ?,
                tier_deadline = ? WHERE appeal_id = ?`
      )
        .bind(
          targetTier === 'tier2' ? 'escalated_tier2' : 'escalated_legal',
          targetTier,
          now + (targetTier === 'tier2' ? 172_800 : 432_000),
          row.appeal_id
        )
        .run();
    }
  }
}
```

---

## 5. Proxy Worker — Routing HTTP to the DO

```typescript
// src/workers/appeal-router.ts
import { Env } from '../types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const parts = url.pathname.split('/').filter(Boolean);
    // Expected: /appeal/:id/:action
    if (parts.length < 2 || parts[0] !== 'appeal') {
      return new Response('Not Found', { status: 404 });
    }

    const [, appealId, action = 'status'] = parts;
    const doId = env.APPEAL_DO.idFromName(appealId);
    const stub = env.APPEAL_DO.get(doId);

    return stub.fetch(`https://do/appeal/${action}`, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });
  },
};
```

---

## Anti-patterns

- **Creating the DO after writing to D1.** Write to D1 first, then init the DO. If the DO init fails, re-try is safe. Reversing the order leaves orphaned DO state with no index entry.
- **Storing full post bodies inside the DO.** The DO storage quota is 128 KB per key. Store only IDs and metadata; retrieve content from R2 or D1 when needed.
- **Calling `idFromString` instead of `idFromName` for appeal IDs.** `idFromString` requires a valid DO-format ID, not a UUID; use `idFromName(uuid)` consistently.
- **Resolving appeals without updating the D1 index.** The Cron sweep reads the index; if the DO is resolved but the index still shows active, the sweep will incorrectly attempt re-escalation.

---

## Gotchas

- Durable Objects have a single-thread execution model per instance; concurrent HTTP requests to the same DO are serialised automatically — no locking needed, but long-running awaits inside `fetch` can queue up requests.
- The `appeal_index` row's `tier_deadline` must be kept in sync with the DO's internal `tierDeadline` field. Use the D1 update immediately after a successful DO escalation call, not before.
- The DO `init` endpoint must be idempotent-guarded (`if (existing) return 409`) to handle double-submissions from retry logic in the creation Worker.

---

## Verification

```bash
# Create an appeal
curl -X POST https://api.example project.internal/appeal/new-uuid-here/init \
  -H "Content-Type: application/json" \
  -d '{"appealId":"new-uuid-here","contentId":"post-123","authorHash":"abc","removalReason":"spam","userStatement":"My post is legitimate."}'

# Check status
curl https://api.example project.internal/appeal/new-uuid-here/status | jq .status
# Expected: "filed"

# Simulate SLA breach by manually escalating
curl -X POST https://api.example project.internal/appeal/new-uuid-here/escalate \
  -H "Content-Type: application/json" \
  -d '{"actor":"system","reason":"sla_breach","targetTier":"tier2"}'
```

---

## Related

- `automated-dispute-resolution-d1-appeals-workflow.md`
- `content-moderation-appeals-workflow.md`
- `account-suspension-appeals-worker-workflow.md`
- `platform-audit-log-immutable-d1-workers.md`
- `automated-content-policy-rule-engine-workers-d1.md`

---

## Sources

- Cloudflare Durable Objects: https://developers.cloudflare.com/durable-objects/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- DSA Article 20 — Internal Complaint Handling Systems
- DSA Article 21 — Out-of-Court Dispute Settlement
