# Account Suspension Appeals Worker Workflow

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Suspended example project accounts have no structured path to appeal a moderation decision.
Moderators manually check a spreadsheet, DM back through a secondary channel, or forget
the case entirely.  Accounts pile up in a "suspended" state with no audit trail,
creating legal exposure under DSA Article 17 (redress mechanisms) and increasing
churn from false positives on legitimate adult users.

## Context

example project's account lifecycle is managed through a D1 database.  Suspension decisions are
written by automated abuse detection Workers and by human moderators via an internal
dashboard.  The appeals flow must: (1) allow a suspended user to submit a counter-claim
within the app, (2) lock the case so two moderators cannot process the same appeal
simultaneously, (3) produce an immutable audit trail, and (4) expose a mobile-friendly
review queue.  Durable Objects are used to provide the per-appeal lock primitive that
D1 alone cannot safely supply under concurrent moderator access.

## D1 Suspension State Machine

All account state transitions live in the `account_events` table.  The `accounts`
table holds only the current computed state; the event log is the source of truth.

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS account_events (
  id          TEXT    PRIMARY KEY,   -- UUIDv7
  account_id  TEXT    NOT NULL,
  event_type  TEXT    NOT NULL,      -- see enum below
  actor_id    TEXT,                  -- moderator account_id or NULL for system
  reason      TEXT,
  metadata    TEXT,                  -- JSON blob
  created_at  INTEGER NOT NULL       -- Unix ms
);

CREATE INDEX idx_ae_account ON account_events(account_id, created_at DESC);

-- Allowed event_type values
-- active | warned | suspended | appeal_submitted | appeal_locked
-- appeal_approved | appeal_rejected | appeal_escalated | permanently_banned
```

State transition table:

```
┌──────────────────────┬────────────────────────────────────────────────────┐
│ Current State        │ Allowed Transitions                                │
├──────────────────────┼────────────────────────────────────────────────────┤
│ active               │ warned, suspended                                  │
│ warned               │ active (cleared), suspended                        │
│ suspended            │ appeal_submitted, permanently_banned               │
│ appeal_submitted     │ appeal_locked                                      │
│ appeal_locked        │ appeal_approved, appeal_rejected, appeal_escalated │
│ appeal_approved      │ active                                             │
│ appeal_rejected      │ permanently_banned (after grace period)            │
│ appeal_escalated     │ appeal_approved, permanently_banned                │
│ permanently_banned   │ (terminal)                                         │
└──────────────────────┴────────────────────────────────────────────────────┘
```

## Durable Object Appeal Lock

Race conditions between concurrent moderators are prevented by a Durable Object that
holds an in-memory lock for the duration of a review session (max 15 minutes).

```ts
// worker/durableObjects/AppealLock.ts
export class AppealLock implements DurableObject {
  private lockedBy: string | null = null;
  private lockedAt: number = 0;
  private readonly TTL_MS = 15 * 60 * 1000;

  async fetch(request: Request): Promise<Response> {
    const { action, moderatorId } = await request.json<{
      action: "acquire" | "release" | "status";
      moderatorId: string;
    }>();

    const now = Date.now();
    const expired = this.lockedBy !== null && now - this.lockedAt > this.TTL_MS;
    if (expired) this.lockedBy = null;

    if (action === "acquire") {
      if (this.lockedBy && this.lockedBy !== moderatorId) {
        return Response.json({ ok: false, lockedBy: this.lockedBy });
      }
      this.lockedBy = moderatorId;
      this.lockedAt = now;
      return Response.json({ ok: true });
    }

    if (action === "release") {
      if (this.lockedBy === moderatorId) this.lockedBy = null;
      return Response.json({ ok: true });
    }

    return Response.json({ lockedBy: this.lockedBy, expiresAt: this.lockedAt + this.TTL_MS });
  }
}
```

The DO is addressed by appeal ID so each appeal gets its own lock namespace:

```ts
const stub = env.APPEAL_LOCK.get(env.APPEAL_LOCK.idFromName(`appeal:${appealId}`));
const result = await stub.fetch("https://do/", {
  method: "POST",
  body: JSON.stringify({ action: "acquire", moderatorId }),
});
```

## Worker API Endpoints

```
┌───────────────────────────────────────┬────────────┬──────────────────────────────┐
│ Route                                 │ Auth       │ Purpose                      │
├───────────────────────────────────────┼────────────┼──────────────────────────────┤
│ POST /api/appeals                     │ Session JWT│ Submit appeal (suspended usr) │
│ GET  /api/appeals/:id                 │ Session JWT│ Check own appeal status       │
│ GET  /api/mod/appeals                 │ Mod JWT    │ Paginated review queue        │
│ POST /api/mod/appeals/:id/lock        │ Mod JWT    │ Acquire DO lock               │
│ POST /api/mod/appeals/:id/decision    │ Mod JWT    │ Approve / reject / escalate   │
│ DELETE /api/mod/appeals/:id/lock      │ Mod JWT    │ Release DO lock               │
└───────────────────────────────────────┴────────────┴──────────────────────────────┘
```

Moderator JWT authentication uses a short-lived RS256 token issued at login, verified
in every Worker handler without a D1 round-trip:

```ts
// worker/lib/modAuth.ts
import { importSPKI, jwtVerify } from "jose";

export async function requireModJwt(request: Request, env: Env): Promise<string> {
  const auth = request.headers.get("Authorization") ?? "";
  if (!auth.startsWith("Bearer ")) throw new Response("Unauthorized", { status: 401 });
  const token = auth.slice(7);
  const key = await importSPKI(env.MOD_JWT_PUBLIC_KEY, "RS256");
  const { payload } = await jwtVerify(token, key, {
    issuer: "example project-mod-auth",
    audience: "example project-mod-dashboard",
  });
  if (payload.role !== "moderator" && payload.role !== "senior_moderator") {
    throw new Response("Forbidden", { status: 403 });
  }
  return payload.sub as string;
}
```

## Moderator Dashboard Mobile UX

The internal dashboard is a Cloudflare Pages app.  On mobile (viewport < 640 px)
the review queue switches from a split-pane layout to a swipe-card interface.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ Mobile queue card layout (375 px)                                              │
├────────────────────────────────────────────────────────────────────────────────┤
│  [Avatar]  @handle — suspended 3d ago                           [LOCKED by you]│
│  Reason: repeated harassment reports (×4)                                      │
│  User appeal: "I did not write those posts, my account was compromised."       │
│  Evidence: [View 4 reports ▸]  [Account history ▸]                            │
│                                                                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │   ✓ Approve     │  │   ✗ Reject      │  │   ⬆ Escalate    │               │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘               │
│  Lock expires in 12:43                           [Release lock]               │
└────────────────────────────────────────────────────────────────────────────────┘
```

Decision buttons dispatch to `POST /api/mod/appeals/:id/decision` and optimistically
update the card list.  If the lock has expired the server returns `409 Conflict` and
the UI shows a re-lock prompt rather than silently discarding the decision.

## Anti-patterns

- Writing suspension state directly to the `accounts.status` column without an event
  log — loses audit trail required by DSA Article 17 and makes state reconstruction
  impossible after a data incident.
- Using a D1 `SELECT FOR UPDATE` pattern — D1 does not support row-level locking;
  concurrent reads return stale state and cause double-processing of the same appeal.
- Issuing moderator JWTs with long expiry (>4 h) — a leaked token grants full
  moderation authority; 1-hour expiry with silent refresh is the safe default.
- Sending suspension reasons to the user's registered email — example project accounts are
  anonymous; emailing reveals the link between the anonymous handle and the email
  address used for age verification.  In-app notification only.
- Re-using the same Durable Object ID for all appeals — serializes all moderator
  actions globally and eliminates concurrency benefits.

## Gotchas

- `jwtVerify` from `jose` requires the public key as a CryptoKey or KeyLike.
  `env.MOD_JWT_PUBLIC_KEY` must be a PEM string; `importSPKI` converts it.
  Calling `jwtVerify` with the raw PEM string throws a non-obvious type error.
- Durable Objects reset in-memory state on eviction (after ~10 s of inactivity).
  The lock object will lose `lockedBy` on eviction.  Always check the DO state
  at the start of a decision submission, not only at lock-acquire time.
- `appeal_submitted` → `appeal_locked` is a server-side transition, not a user action.
  Insert the `appeal_locked` event in the same D1 batch as the DO acquire to keep
  the event log consistent even if the Worker crashes between the two operations.
- DSA Article 17 requires the platform to notify the user of a suspension decision
  within a "reasonable time" and in plain language.  The appeal rejection notification
  must include the specific rule violated, not just "violation of community guidelines".

## Verification

```bash
# 1. Submit an appeal as a suspended user
curl -X POST https://example.com/api/appeals \
  -H "Authorization: Bearer $USER_JWT" \
  -d '{"statement":"My account was compromised."}'
# Expect: 201 Created with appealId

# 2. Acquire the DO lock as a moderator
curl -X POST https://example.com/api/mod/appeals/$APPEAL_ID/lock \
  -H "Authorization: Bearer $MOD_JWT"
# Expect: {"ok":true}

# 3. Concurrent lock attempt from a different moderator should fail
curl -X POST https://example.com/api/mod/appeals/$APPEAL_ID/lock \
  -H "Authorization: Bearer $MOD_JWT_2"
# Expect: {"ok":false,"lockedBy":"mod-uuid-1"}

# 4. Submit a decision
curl -X POST https://example.com/api/mod/appeals/$APPEAL_ID/decision \
  -H "Authorization: Bearer $MOD_JWT" \
  -d '{"decision":"approved","note":"Account compromise confirmed."}'
# Expect: 200; account_events row with event_type=appeal_approved
```

## Related

- `content-moderation-appeals-workflow.md`
- `anonymous-platform-abuse-prevention.md`
- `digital-services-act-platform-compliance.md`
- `dsa-risk-assessment.md`
- `d1-column-affinity-gotcha.md`

## Sources

- DSA Article 17 — eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32022R2065
- Cloudflare Durable Objects — developers.cloudflare.com/durable-objects/
- Cloudflare D1 — developers.cloudflare.com/d1/
- `jose` library — github.com/panva/jose
- Cloudflare Pages — developers.cloudflare.com/pages/
