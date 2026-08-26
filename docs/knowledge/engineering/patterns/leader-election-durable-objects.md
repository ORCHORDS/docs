# Leader Election with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple Worker instances that must coordinate around a shared resource — a rate-limiter, a queue drain loop, or a cron-style task — and only one should act as the leader at any time. Stateless Workers cannot elect a leader themselves; you need a coordination primitive that survives across requests.

## Context

Durable Objects (DOs) provide a single-threaded, strongly-consistent execution environment with a stable ID. A single DO instance can serve as the coordinator for an arbitrary number of Workers: it owns the election state, issues a *fencing token* that monotonically increases with each term, and writes the current leader identity to Workers KV so all Workers can read it cheaply without hitting the DO on every request.

---

## Section 1 — Coordinator Durable Object

The DO holds election state in its in-memory variables (fast path) and persists to its own storage (durable path). Workers send heartbeats on a fixed interval; if the coordinator misses `MAX_MISSED` consecutive heartbeats it triggers a new election.

```typescript
// coordinator.ts
export interface ElectionState {
  leader: string | null;
  term: number;
  fencingToken: number;
  lastHeartbeatMs: number;
}

const HEARTBEAT_INTERVAL_MS = 5_000;
const MAX_MISSED = 3;

export class LeaderCoordinator implements DurableObject {
  private state: DurableObjectState;
  private env: Env;
  private election: ElectionState = {
    leader: null,
    term: 0,
    fencingToken: 0,
    lastHeartbeatMs: 0,
  };

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
    this.state.blockConcurrencyWhile(async () => {
      const stored = await this.state.storage.get<ElectionState>('election');
      if (stored) this.election = stored;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/heartbeat' && request.method === 'POST') {
      return this.handleHeartbeat(request);
    }
    if (path === '/nominate' && request.method === 'POST') {
      return this.handleNominate(request);
    }
    if (path === '/state' && request.method === 'GET') {
      return Response.json(this.election);
    }
    return new Response('Not found', { status: 404 });
  }

  private async handleHeartbeat(request: Request): Promise<Response> {
    const { candidateId } = await request.json<{ candidateId: string }>();
    const now = Date.now();

    if (candidateId !== this.election.leader) {
      return Response.json({ accepted: false, leader: this.election.leader }, { status: 409 });
    }

    this.election.lastHeartbeatMs = now;
    await this.persistAndBroadcast();
    return Response.json({ accepted: true, fencingToken: this.election.fencingToken });
  }

  private async handleNominate(request: Request): Promise<Response> {
    const { candidateId } = await request.json<{ candidateId: string }>();
    const now = Date.now();
    const deadline = this.election.lastHeartbeatMs + HEARTBEAT_INTERVAL_MS * MAX_MISSED;

    if (this.election.leader !== null && now < deadline) {
      return Response.json(
        { elected: false, leader: this.election.leader, retryAfterMs: deadline - now },
        { status: 409 },
      );
    }

    this.election.leader = candidateId;
    this.election.term += 1;
    this.election.fencingToken += 1;
    this.election.lastHeartbeatMs = now;

    await this.persistAndBroadcast();
    return Response.json(
      { elected: true, term: this.election.term, fencingToken: this.election.fencingToken },
      { status: 200 },
    );
  }

  private async persistAndBroadcast(): Promise<void> {
    await this.state.storage.put('election', this.election);
    await this.env.LEADER_KV.put(
      'current-leader',
      JSON.stringify({
        leader: this.election.leader,
        fencingToken: this.election.fencingToken,
        term: this.election.term,
        updatedAtMs: Date.now(),
      }),
      { expirationTtl: 30 },
    );
  }
}
```

## Section 2 — Candidate Worker

```typescript
// worker.ts
const CANDIDATE_ID = crypto.randomUUID();
let heartbeatScheduled = false;

async function tryElect(env: Env): Promise<{ leader: string; fencingToken: number } | null> {
  const id = env.COORDINATOR.idFromName('global-leader');
  const stub = env.COORDINATOR.get(id);
  const res = await stub.fetch('https://internal/nominate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidateId: CANDIDATE_ID }),
  });
  if (!res.ok) return null;
  const body = await res.json<{ elected: boolean; fencingToken: number }>();
  return body.elected ? { leader: CANDIDATE_ID, fencingToken: body.fencingToken } : null;
}

async function sendHeartbeat(env: Env): Promise<boolean> {
  const id = env.COORDINATOR.idFromName('global-leader');
  const stub = env.COORDINATOR.get(id);
  const res = await stub.fetch('https://internal/heartbeat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidateId: CANDIDATE_ID }),
  });
  return res.ok;
}

async function scheduleHeartbeat(ctx: ExecutionContext, env: Env): Promise<void> {
  if (heartbeatScheduled) return;
  heartbeatScheduled = true;
  ctx.waitUntil(
    (async () => {
      while (true) {
        await new Promise((r) => setTimeout(r, 4_500));
        const ok = await sendHeartbeat(env);
        if (!ok) await tryElect(env);
      }
    })(),
  );
}

async function currentLeader(env: Env): Promise<string | null> {
  const raw = await env.LEADER_KV.get('current-leader');
  if (!raw) return null;
  return (JSON.parse(raw) as { leader: string }).leader;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const leader = await currentLeader(env);
    if (!leader) await tryElect(env);
    scheduleHeartbeat(ctx, env);
    const isLeader = (await currentLeader(env)) === CANDIDATE_ID;
    return Response.json({ candidateId: CANDIDATE_ID, isLeader });
  },
};
```

## Section 3 — Fencing Token Enforcement

```typescript
// resource-writer.ts
export async function writeWithFencing(
  env: Env,
  key: string,
  value: string,
  fencingToken: number,
): Promise<{ ok: boolean; reason?: string }> {
  const raw = await env.LEADER_KV.get('current-leader');
  if (!raw) return { ok: false, reason: 'no-leader' };
  const { fencingToken: currentToken } = JSON.parse(raw) as { fencingToken: number };
  if (fencingToken < currentToken) {
    return { ok: false, reason: 'stale-fencing-token' };
  }
  await env.LEADER_KV.put(key, value);
  return { ok: true };
}
```

## Anti-patterns

- Using a plain KV key as a lock: KV is eventually consistent and two Workers can both read stale state simultaneously.
- Relying on DO alarms alone: alarms fire at most once and can be lost on crash.
- Not incrementing the fencing token on re-election: zombie leaders from a previous term can overwrite data.
- Embedding the heartbeat loop in the main fetch handler instead of `waitUntil`.

## Gotchas

- `blockConcurrencyWhile` is essential; without it, requests can race against storage hydration on cold start.
- `expirationTtl` on the KV key must exceed `HEARTBEAT_INTERVAL_MS * MAX_MISSED`.
- Workers isolates can be evicted; `CANDIDATE_ID` is module-scope and survives within an isolate lifetime only.

## Verification

```bash
# Deploy and fire concurrent requests; only one isolate should claim leadership
for i in $(seq 1 10); do
  curl -s https://your-worker.example.com/ | jq '{candidateId,isLeader}' &
done
wait

# Inspect KV
wrangler kv key get --namespace-id=<LEADER_KV_ID> current-leader
```

## Related

- documentation/docs/policies/patterns/idempotent-receiver-workers-kv.md
- documentation/docs/policies/patterns/two-phase-commit-workers-d1-kv.md

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/kv/
- Martin Kleppmann, *Designing Data-Intensive Applications*, Chapter 8
