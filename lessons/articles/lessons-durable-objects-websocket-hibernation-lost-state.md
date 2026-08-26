# Durable Objects WebSocket Hibernation: Lost In-Memory Game State

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The multiplayer chord-quiz game experienced random state resets during active sessions: players would be mid-game when the scoreboard and current question index suddenly reverted to zero. The bug was non-deterministic and correlated with periods of low message frequency — roughly 15–30 seconds of silence on the WebSocket connection before a player submitted an answer. No errors appeared in the Worker logs; from the client's perspective the WebSocket remained connected but the server-side game state had been silently erased.

---

## Context

Cloudflare Durable Objects support WebSocket Hibernation: when all WebSocket connections on a DO become idle (no messages for ~15–30 s), the runtime can evict the V8 isolate to reclaim memory. When the next message arrives, the runtime transparently wakes the DO, restores its WebSocket connections, and invokes the appropriate `webSocketMessage` handler — but the V8 heap is freshly initialised. Any state stored only in JavaScript class properties (instance variables) is gone. Hibernation is opt-in (via `ctx.acceptWebSocket(ws)` instead of the legacy pair pattern) but is the default in newer DO code that uses the Hibernation API.

---

## Root Cause: State Stored Only in JS Instance Variables

The original implementation stored all game state in class properties:

```typescript
// BEFORE — state lost on hibernation
export class ChordQuizGameDO implements DurableObject {
  // All of these live ONLY on the V8 heap.
  // They are wiped to their initial values on every hibernation wake.
  private players: Map<WebSocket, PlayerState> = new Map();
  private currentQuestion = 0;
  private scores: Map<string, number> = new Map();
  private questionStartedAt = 0;
  private phase: 'lobby' | 'question' | 'reveal' | 'finished' = 'lobby';

  constructor(
    private readonly state: DurableObjectState,
    private readonly env: Env
  ) {}

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') === 'websocket') {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      // Legacy approach — does NOT enable hibernation
      server.accept();
      server.addEventListener('message', (evt) => this.handleMessage(server, evt.data as string));
      return new Response(null, { status: 101, webSocket: client });
    }
    return new Response('Not a WebSocket upgrade', { status: 400 });
  }

  private handleMessage(ws: WebSocket, raw: string): void {
    const msg = JSON.parse(raw) as ClientMessage;
    if (msg.type === 'submit_answer') {
      // scores is empty after hibernation — bug!
      const current = this.scores.get(msg.playerId) ?? 0;
      this.scores.set(msg.playerId, current + (msg.correct ? 10 : 0));
      this.broadcast({ type: 'score_update', scores: Object.fromEntries(this.scores) });
    }
  }

  private broadcast(data: unknown): void {
    const json = JSON.stringify(data);
    for (const ws of this.players.keys()) {
      ws.send(json);
    }
  }
}
```

The failure sequence:

```
1. Players connect → game starts → state lives in class properties
2. Players pause for 20s (reading a chord diagram)
3. DO hibernation evicts the V8 isolate
4. A player submits an answer → WebSocket wake → DO restarts
5. `this.scores`, `this.currentQuestion`, `this.phase` → back to defaults
6. Player receives a score update showing 0 for all players
```

---

## Fix: Persist State to `ctx.storage` on Every Mutation, Restore in `webSocketMessage`

Use the Hibernation API (`ctx.acceptWebSocket`) and persist all mutable state to `ctx.storage` synchronously on every change. Restore state from storage at the top of `webSocketMessage` and `webSocketClose`:

```typescript
// types.ts
export interface GameState {
  currentQuestion: number;
  scores: Record<string, number>;       // playerId → score
  phase: 'lobby' | 'question' | 'reveal' | 'finished';
  questionStartedAt: number;
  playerIds: string[];                  // ordered list for reconnection
}

export interface PlayerAttachment {
  playerId: string;
  displayName: string;
}

export type ClientMessage =
  | { type: 'submit_answer'; playerId: string; answer: string; correct: boolean }
  | { type: 'request_state'; playerId: string }
  | { type: 'join'; playerId: string; displayName: string };

export type ServerMessage =
  | { type: 'score_update'; scores: Record<string, number> }
  | { type: 'state_sync'; state: GameState }
  | { type: 'error'; message: string };
```

```typescript
// ChordQuizGameDO.ts
import type { GameState, PlayerAttachment, ClientMessage, ServerMessage } from './types';

const STORAGE_KEY = 'game_state';

export class ChordQuizGameDO implements DurableObject {
  constructor(
    private readonly ctx: DurableObjectState,
    private readonly env: Env
  ) {}

  // --- Connection Upgrade ---

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Expected WebSocket upgrade', { status: 426 });
    }

    const url = new URL(request.url);
    const playerId = url.searchParams.get('playerId');
    const displayName = url.searchParams.get('displayName') ?? 'Anonymous';

    if (!playerId) {
      return new Response('Missing playerId', { status: 400 });
    }

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair) as [WebSocket, WebSocket];

    // acceptWebSocket enables hibernation — the DO can be evicted when idle
    this.ctx.acceptWebSocket(server, [playerId, displayName]);

    // Record this player in persistent state immediately
    await this.updateState(async (state) => {
      if (!state.playerIds.includes(playerId)) {
        state.playerIds.push(playerId);
        state.scores[playerId] = 0;
      }
      return state;
    });

    // Send current state to the joining player
    const state = await this.loadState();
    const msg: ServerMessage = { type: 'state_sync', state };
    server.send(JSON.stringify(msg));

    return new Response(null, { status: 101, webSocket: client });
  }

  // --- Hibernation Handlers ---
  // These are called after a hibernation wake — instance variables are gone.
  // We MUST reload all state from ctx.storage here.

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    // Reload state from durable storage — heap state is unreliable after hibernation
    const state = await this.loadState();
    const [playerId] = this.ctx.getTags(ws) as [string, string];

    let msg: ClientMessage;
    try {
      msg = JSON.parse(message as string) as ClientMessage;
    } catch {
      ws.send(JSON.stringify({ type: 'error', message: 'Invalid JSON' } satisfies ServerMessage));
      return;
    }

    const nextState = await this.applyMessage(state, playerId, msg);

    // Persist BEFORE broadcasting — if broadcast fails, state is still safe
    await this.ctx.storage.put(STORAGE_KEY, nextState);
    this.broadcastToAll({ type: 'state_sync', state: nextState });
  }

  async webSocketClose(
    ws: WebSocket,
    code: number,
    reason: string,
    wasClean: boolean
  ): Promise<void> {
    const [playerId] = this.ctx.getTags(ws) as [string, string];
    console.log(`[DO] player ${playerId} disconnected: code=${code} clean=${wasClean}`);
    // Optionally mark player as disconnected in state without removing scores
    await this.updateState((state) => {
      // Keep scores; game can continue with disconnected players
      return state;
    });
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    console.error('[DO] WebSocket error:', error);
  }

  // --- State Helpers ---

  private async loadState(): Promise<GameState> {
    const stored = await this.ctx.storage.get<GameState>(STORAGE_KEY);
    return stored ?? {
      currentQuestion: 0,
      scores: {},
      phase: 'lobby',
      questionStartedAt: 0,
      playerIds: [],
    };
  }

  private async updateState(
    updater: (state: GameState) => GameState | Promise<GameState>
  ): Promise<GameState> {
    const current = await this.loadState();
    const next = await updater(current);
    await this.ctx.storage.put(STORAGE_KEY, next);
    return next;
  }

  private async applyMessage(
    state: GameState,
    playerId: string,
    msg: ClientMessage
  ): Promise<GameState> {
    switch (msg.type) {
      case 'submit_answer': {
        const delta = msg.correct ? 10 : 0;
        return {
          ...state,
          scores: {
            ...state.scores,
 ?? 0) + delta,
          },
        };
      }
      case 'request_state':
        return state; // No mutation — just return current state for broadcast
      case 'join':
        if (!state.playerIds.includes(playerId)) {
          return {
            ...state,
            playerIds: [...state.playerIds, playerId],
            scores: { ...state.scores, [playerId]: 0 },
          };
        }
        return state;
      default:
        console.warn('[DO] Unknown message type:', (msg as ClientMessage).type);
        return state;
    }
  }

  private broadcastToAll(msg: ServerMessage): void {
    const json = JSON.stringify(msg);
    for (const ws of this.ctx.getWebSockets()) {
      try {
        ws.send(json);
      } catch (err) {
        console.warn('[DO] Failed to send to WebSocket:', err);
      }
    }
  }
}
```

---

## Monitoring / Detection

```typescript
// Add hibernation wake detection by tracking whether loadState returned the
// default (freshly-initialised) state on a connection that should have existing state.

export class InstrumentedChordQuizGameDO extends ChordQuizGameDO {
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const stateBeforeLoad = await this.ctx.storage.get<GameState>('game_state');
    const isWakeFromHibernation = stateBeforeLoad !== undefined;
    // If stateBeforeLoad is undefined for a game that should have state,
    // the storage write on a previous message may have failed.
    if (!isWakeFromHibernation) {
      console.warn('[DO] WARN: game_state missing from storage on message receipt');
      this.env.ANALYTICS.writeDataPoint({
        blobs: ['do_hibernation', 'missing_state'],
        doubles: [1],
        indexes: ['do_health'],
      });
    }
    await super.webSocketMessage(ws, message);
  }
}

// Track DO hibernation wake-ups via storage read latency increase
export async function measureStorageReadLatency(ctx: DurableObjectState): Promise<number> {
  const start = Date.now();
  await ctx.storage.get('game_state');
  const latency = Date.now() - start;
  if (latency > 50) {
    console.warn(`[DO] Storage read latency ${latency}ms — possible cold wake from hibernation`);
  }
  return latency;
}
```

---

## Anti-patterns

- **Storing mutable state only in class instance variables** — Any property on `this` that is not restored from `ctx.storage` will be reset to its initial value after hibernation. Treat class properties as caches of storage, never as the source of truth.
- **Using the legacy WebSocket pair pattern (`server.accept()`)** — The legacy pattern does not support hibernation; it keeps the isolate alive permanently (billing you for idle time) or loses connections on eviction. Migrate to `ctx.acceptWebSocket()`.
- **Calling `ctx.storage.put()` after broadcasting** — If the broadcast succeeds but the storage write fails (or the isolate is evicted between the two), the broadcast will reflect state that was never persisted. Always persist before broadcasting.
- **Storing WebSocket references in the class instead of using `ctx.getWebSockets()`** — After hibernation wake, the `Map<WebSocket, ...>` is empty. Use `ctx.getWebSockets()` to obtain the live connections, and `ctx.getTags(ws)` to retrieve the player metadata set at `acceptWebSocket` time.

---

## Gotchas

- `ctx.acceptWebSocket(ws, tags)` accepts an optional string-array of tags. Tags survive hibernation and are the correct way to associate player metadata with a WebSocket connection. The metadata must be serialisable as strings.
- `ctx.storage` reads return `undefined` for keys that were never written — always supply defaults in `loadState()`.
- Durable Object storage `put` and `get` calls execute transactionally within a single event handler invocation; multiple `put` calls in one handler are atomic. Across handler invocations they are not — design accordingly.
- The DO's hibernation timer is approximately 15–30 seconds but is not guaranteed. Do not rely on the timer for any application logic; always reload from storage.
- `ctx.storage.put()` is durable — it persists to disk before the promise resolves. However, if the Worker process is killed between calling `put` and the promise resolving, the write may be lost. Use `ctx.storage.transaction()` for writes that must be atomic with other operations.
- WebSocket close codes in the 4000–4999 range are application-defined. Use them to signal specific game events (e.g., 4001 = game over) to clients.

---

## Verification

```bash
# Confirm DO hibernation is enabled in wrangler.toml
grep -A3 'durable_objects' wrangler.toml

# Test hibernation locally using Miniflare
npx miniflare --do ChordQuizGameDO=src/ChordQuizGameDO.ts -- node test/hibernation.mjs

# Manual hibernation test:
# 1. Connect a WebSocket and send some game messages
wscat -c 'wss://your-worker.example.com/game?playerId=player1&displayName=Alice'
# 2. Send: {"type":"join","playerId":"player1","displayName":"Alice"}
# 3. Send: {"type":"submit_answer","playerId":"player1","answer":"C","correct":true}
# 4. Wait 30 seconds (hibernation window)
# 5. Send: {"type":"request_state","playerId":"player1"}
# 6. Verify: scores should still show 10 for player1

# Check DO storage content directly
npx wrangler durable-object storage get <DO_CLASS> <DO_ID> game_state
```

---

## Related

- `lessons-kv-cache-stampede-production.md`
- `lessons-d1-eventual-consistency-production-incident.md`

---

## Sources

- Cloudflare Durable Objects WebSocket Hibernation — https://developers.cloudflare.com/durable-objects/examples/websocket-hibernation-server/
- Cloudflare DO Storage API — https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- Durable Objects `getTags` / `getWebSockets` — https://developers.cloudflare.com/durable-objects/api/websockets/
