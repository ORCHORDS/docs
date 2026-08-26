# NSFW Content Soft-Launch & Gradual Visibility Rollout (Cloudflare Workers)

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project must gate adult content behind age verification and consent before making it visible to the general feed. A hard launch risks regulatory exposure if verification is incomplete; no launch risks creator churn. A gradual-visibility system starts with 0 % reach, expands to verified cohorts only, and gates full visibility on passing a configurable policy checklist — all controlled at the edge with zero redeploy cycles.

---

## Context

Cloudflare Workers KV holds a per-content visibility gate (a JSON envelope with rollout percentage, eligible cohorts, and policy status). When a feed Worker retrieves posts, it reads the gate and evaluates whether the requesting session belongs to the cohort. The content itself lives in R2; the Worker returns a signed R2 URL only if the gate passes. A separate Cron Trigger advances the rollout percentage autonomously when all policy checks are green.

---

## 1. Types & Shared Utilities

```typescript
// src/types/visibility.ts
export type PolicyStatus = 'pending' | 'approved' | 'rejected';
export type Cohort = 'staff' | 'verified_adult' | 'opted_in' | 'global';

export interface VisibilityGate {
  contentId: string;
  rolloutPct: number;              // 0–100
  eligibleCohorts: Cohort[];
  ageVerified: boolean;
  creatorConsent: boolean;
  moderationStatus: PolicyStatus;
  legalHold: boolean;
  createdAt: number;               // Unix epoch
  updatedAt: number;
}

export function defaultGate(contentId: string): VisibilityGate {
  return {
    contentId,
    rolloutPct: 0,
    eligibleCohorts: ['staff'],
    ageVerified: false,
    creatorConsent: false,
    moderationStatus: 'pending',
    legalHold: false,
    createdAt: Math.floor(Date.now() / 1000),
    updatedAt: Math.floor(Date.now() / 1000),
  };
}

export function gateIsGloballyVisible(gate: VisibilityGate): boolean {
  return (
    gate.rolloutPct === 100 &&
    gate.ageVerified &&
    gate.creatorConsent &&
    gate.moderationStatus === 'approved' &&
    !gate.legalHold &&
    gate.eligibleCohorts.includes('global')
  );
}
```

---

## 2. Gate Evaluation in the Feed Worker

```typescript
// src/workers/feed-nsfw-gate.ts
import { Env } from '../types';
import { VisibilityGate, Cohort } from '../types/visibility';
import { getSessionCohort } from '../lib/session';
import { signR2Url } from '../lib/r2';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const contentId = url.searchParams.get('contentId');
    if (!contentId) return new Response('Missing contentId', { status: 400 });

    // Read gate from KV (fresh, no edge cache — gate changes must be immediate)
    const raw = await env.VISIBILITY_KV.get(`gate:${contentId}`, { type: 'json' }) as VisibilityGate | null;
    if (!raw) return new Response('Not Found', { status: 404 });

    const sessionCohort: Cohort = await getSessionCohort(request, env);

    if (!raw.eligibleCohorts.includes(sessionCohort) && !raw.eligibleCohorts.includes('global')) {
      return new Response('Forbidden', { status: 403 });
    }

    // Probabilistic rollout: deterministic per (contentId, sessionId) so the
    // same user always sees or doesn't see the content consistently.
    const sessionId = request.headers.get('X-Session-Id') ?? 'anon';
    const bucket = await deterministicBucket(contentId + sessionId);
    if (bucket > raw.rolloutPct) {
      return new Response('Forbidden', { status: 403 });
    }

    if (raw.moderationStatus !== 'approved') {
      return new Response('Content under review', { status: 451 });
    }

    if (raw.legalHold) {
      return new Response('Content unavailable', { status: 451 });
    }

    const signedUrl = await signR2Url(env, `nsfw/${contentId}`, 300);
    return Response.redirect(signedUrl, 302);
  },
};

async function deterministicBucket(seed: string): Promise<number> {
  const data = new TextEncoder().encode(seed);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const view = new DataView(hashBuffer);
  // Use first 4 bytes as uint32, map to 0–100
  return (view.getUint32(0, false) % 101);
}
```

---

## 3. Gate Upsert API — Content Registration

```typescript
// src/workers/visibility-admin.ts
import { Env } from '../types';
import { defaultGate, VisibilityGate } from '../types/visibility';
import { requireInternalAuth } from '../lib/auth';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!requireInternalAuth(request, env)) return new Response('Unauthorized', { status: 401 });
    if (request.method !== 'PUT') return new Response('Method Not Allowed', { status: 405 });

    const url = new URL(request.url);
    const contentId = url.pathname.split('/').pop();
    if (!contentId) return new Response('Missing contentId', { status: 400 });

    const body = await request.json<Partial<VisibilityGate>>();
    const existing = (await env.VISIBILITY_KV.get(`gate:${contentId}`, { type: 'json' }) as VisibilityGate | null)
      ?? defaultGate(contentId);

    const updated: VisibilityGate = {
      ...existing,
      ...body,
      contentId,                         // never allow override
      updatedAt: Math.floor(Date.now() / 1000),
    };

    // Safety: never roll out to global if policy checks are incomplete
    if (updated.eligibleCohorts.includes('global')) {
      if (!updated.ageVerified || !updated.creatorConsent || updated.moderationStatus !== 'approved') {
        updated.eligibleCohorts = updated.eligibleCohorts.filter(c => c !== 'global');
      }
    }

    await env.VISIBILITY_KV.put(`gate:${contentId}`, JSON.stringify(updated));
    return new Response(JSON.stringify(updated), { status: 200 });
  },
};
```

---

## 4. Automatic Rollout Cron Trigger

```typescript
// src/cron/nsfw-rollout-advance.ts
import { Env } from '../types';
import { VisibilityGate } from '../types/visibility';

const ROLLOUT_STEPS: number[] = [0, 5, 20, 50, 100];
const STEP_INTERVAL_HOURS = 24;

export async function advanceNsfwRollout(env: Env): Promise<void> {
  // List all pending gates
  const list = await env.VISIBILITY_KV.list({ prefix: 'gate:' });

  for (const key of list.keys) {
    const gate = await env.VISIBILITY_KV.get<VisibilityGate>(key.name, { type: 'json' });
    if (!gate) continue;

    // Only advance if all policy preconditions are met
    if (!gate.ageVerified || !gate.creatorConsent || gate.moderationStatus !== 'approved' || gate.legalHold) {
      continue;
    }

    const hoursSinceUpdate = (Math.floor(Date.now() / 1000) - gate.updatedAt) / 3600;
    if (hoursSinceUpdate < STEP_INTERVAL_HOURS) continue;

    const currentIdx = ROLLOUT_STEPS.indexOf(gate.rolloutPct);
    if (currentIdx === -1 || currentIdx === ROLLOUT_STEPS.length - 1) continue;

    const nextPct = ROLLOUT_STEPS[currentIdx + 1];

    const updated: VisibilityGate = {
      ...gate,
      rolloutPct: nextPct,
      eligibleCohorts: nextPct === 100
        ? [...new Set([...gate.eligibleCohorts, 'global'])]
        : gate.eligibleCohorts,
      updatedAt: Math.floor(Date.now() / 1000),
    };

    await env.VISIBILITY_KV.put(key.name, JSON.stringify(updated));
    console.log(`[nsfw-rollout] ${gate.contentId}: ${gate.rolloutPct}% → ${nextPct}%`);
  }
}
```

---

## 5. Emergency Halt — Freeze All NSFW Visibility

```typescript
// src/workers/visibility-kill-switch.ts
import { Env } from '../types';
import { VisibilityGate } from '../types/visibility';
import { requireInternalAuth } from '../lib/auth';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!requireInternalAuth(request, env)) return new Response('Unauthorized', { status: 401 });
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const list = await env.VISIBILITY_KV.list({ prefix: 'gate:' });
    let frozen = 0;

    for (const key of list.keys) {
      const gate = await env.VISIBILITY_KV.get<VisibilityGate>(key.name, { type: 'json' });
      if (!gate) continue;
      if (gate.rolloutPct === 0) continue;

      await env.VISIBILITY_KV.put(key.name, JSON.stringify({
        ...gate,
        rolloutPct: 0,
        eligibleCohorts: ['staff'],
        legalHold: true,
        updatedAt: Math.floor(Date.now() / 1000),
      }));
      frozen++;
    }

    return new Response(JSON.stringify({ ok: true, frozen }), { status: 200 });
  },
};
```

---

## Anti-patterns

- **Caching the gate in the CDN.** Use `Cache-Control: no-store` or bypass the cache entirely. A stale gate can serve NSFW content to ineligible users after a freeze.
- **Client-side cohort evaluation.** The cohort check must happen inside the Worker; never expose the gate JSON to the browser.
- **Linear percentage rollout without deterministic hashing.** Without a stable hash, the same user can see content on one request and be denied on the next, creating a jarring UX.
- **Advancing rollout before moderation is complete.** The Cron Trigger must check every policy flag before incrementing `rolloutPct`.

---

## Gotchas

- `KV.list()` in the Cron Trigger can hit the 1 000-key default page limit; paginate with the `cursor` returned in the list result.
- R2 signed URLs use the Worker's `crypto.subtle`; ensure the signing key is stored in a Secret, not in a KV value that content moderators can read.
- A `451 Unavailable For Legal Reasons` response is preferred over `403` when `legalHold` is active; it signals the correct semantics to automated compliance scanners.
- `ROLLOUT_STEPS` must include `0` as the first element so `indexOf` returns a valid index for new content.

---

## Verification

```bash
# Confirm gate is created at 0 % for new content
curl -X PUT https://admin.example project.internal/visibility/content-abc \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ageVerified":false,"creatorConsent":false}' | jq .rolloutPct
# Expected: 0

# Confirm 451 is returned when legalHold = true
curl -o /dev/null -w "%{http_code}" \
  "https://feed.example project.internal/nsfw?contentId=content-abc"
# Expected: 451
```

---

## Related

- `age-verification-cloudflare-workers-kyc.md`
- `underage-user-detection-behavioral-signals.md`
- `shadow-banning-reach-limiting-d1-workers.md`
- `emergency-content-takedown-circuit-breaker-queues.md`
- `cross-border-data-localization-user-content.md`

---

## Sources

- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- Cloudflare R2 Presigned URLs: https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- BBFC Age Verification Guidance (UK): https://www.bbfc.co.uk/about-us/age-verification
- DSA Article 28 — Protection of Minors: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
