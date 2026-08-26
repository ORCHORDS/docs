# App Update Checker API in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Mobile apps need to know whether a user is running an outdated version — and whether that outdatedness is severe enough to force an upgrade before the app proceeds. Without a centralised update-check endpoint you end up with hard-coded version strings in the client, no ability to lower the minimum required version after a rollback, and no data on how quickly users actually adopt new builds.

## Context

A lightweight Cloudflare Worker exposes a `GET /update-check?platform=ios&version=2.3.1` endpoint. Current and minimum-required versions live in KV (fast global reads, editable from the dashboard or CI). Changelog entries are stored in D1 and returned alongside the update decision. An A/B flag in KV controls whether to show the update prompt immediately on launch or defer it to a natural breakpoint. Every check is counted in Analytics Engine so you can track adoption curves without third-party APM.

## Solution

```typescript
// update-checker/src/index.ts
import { Hono } from 'hono';

export interface Env {
  APP_VERSIONS: KVNamespace;       // keys: ios:current, ios:min, android:current, android:min
  CHANGELOGS: D1Database;
  AB_FLAGS: KVNamespace;           // key: update_prompt_timing => "immediate" | "natural"
  UPDATE_ANALYTICS: AnalyticsEngineDataset;
}

type Platform = 'ios' | 'android';
type UpdateDecision = 'force_update' | 'soft_update' | 'current';

interface VersionBundle {
  current: string;
  minimum: string;
}

interface UpdateCheckResponse {
  decision: UpdateDecision;
  current_version: string;
  latest_version: string;
  prompt_timing: 'immediate' | 'natural';
  changelog: ChangelogEntry[];
}

interface ChangelogEntry {
  version: string;
  released_at: string;
  highlights: string[];
}

// Semantic version comparison: returns negative if a < b, 0 if equal, positive if a > b
function semverCompare(a: string, b: string): number {
  const parse = (v: string) => v.split('.').map(Number);
  const [aMaj, aMin, aPatch] = parse(a);
  const [bMaj, bMin, bPatch] = parse(b);
  return aMaj - bMaj || aMin - bMin || aPatch - bPatch;
}

async function loadVersionBundle(kv: KVNamespace, platform: Platform): Promise<VersionBundle> {
  const [current, minimum] = await Promise.all([
    kv.get(`${platform}:current`),
    kv.get(`${platform}:min`),
  ]);
  if (!current || !minimum) {
    throw new Error(`Version data missing for platform: ${platform}`);
  }
  return { current, minimum };
}

async function fetchChangelog(
  db: D1Database,
  platform: Platform,
  sinceVersion: string,
  limit = 5,
): Promise<ChangelogEntry[]> {
  const { results } = await db
    .prepare(
      `SELECT version, released_at, highlights
       FROM changelogs
       WHERE platform = ? AND sort_key > (
         SELECT sort_key FROM changelogs WHERE platform = ? AND version = ? LIMIT 1
       )
       ORDER BY sort_key ASC
       LIMIT ?`,
    )
    .bind(platform, platform, sinceVersion, limit)
    .all<{ version: string; released_at: string; highlights: string }>();

  return (results ?? []).map((row) => ({
    version: row.version,
    released_at: row.released_at,
    highlights: JSON.parse(row.highlights),
  }));
}

const app = new Hono<{ Bindings: Env }>();

app.get('/update-check', async (c) => {
  const platform = c.req.query('platform') as Platform | undefined;
  const clientVersion = c.req.query('version');

  if (!platform || !['ios', 'android'].includes(platform)) {
    return c.json({ error: 'Invalid or missing platform' }, 400);
  }
  if (!clientVersion || !/^\d+\.\d+\.\d+$/.test(clientVersion)) {
    return c.json({ error: 'Invalid or missing version' }, 400);
  }

  let bundle: VersionBundle;
  try {
    bundle = await loadVersionBundle(c.env.APP_VERSIONS, platform);
  } catch (err) {
    return c.json({ error: (err as Error).message }, 503);
  }

  let decision: UpdateDecision;
  if (semverCompare(clientVersion, bundle.minimum) < 0) {
    decision = 'force_update';
  } else if (semverCompare(clientVersion, bundle.current) < 0) {
    decision = 'soft_update';
  } else {
    decision = 'current';
  }

  const [promptTiming, changelog] = await Promise.all([
    c.env.AB_FLAGS.get('update_prompt_timing').then(
      (v) => (v ?? 'immediate') as 'immediate' | 'natural',
    ),
    decision !== 'current'
      ? fetchChangelog(c.env.CHANGELOGS, platform, clientVersion)
      : Promise.resolve([]),
  ]);

  // Fire-and-forget analytics
  c.env.UPDATE_ANALYTICS.writeDataPoint({
    blobs: [platform, clientVersion, decision],
    doubles: [1],
    indexes: [`${platform}:${decision}`],
  });

  const response: UpdateCheckResponse = {
    decision,
    current_version: clientVersion,
    latest_version: bundle.current,
    prompt_timing: promptTiming,
    changelog,
  };

  // Cache "current" responses aggressively; update responses only briefly
  const maxAge = decision === 'current' ? 300 : 60;
  c.header('Cache-Control', `public, max-age=${maxAge}`);
  return c.json(response);
});

// Admin endpoint — update version strings from CI
app.put('/admin/version', async (c) => {
  const authHeader = c.req.header('Authorization');
  const token = c.env.AB_FLAGS.get('admin_token'); // reuse KV for simplicity
  if (!authHeader || authHeader !== `Bearer ${await token}`) {
    return c.json({ error: 'Unauthorized' }, 401);
  }

  const body = await c.req.json<{
    platform: Platform;
    current?: string;
    minimum?: string;
  }>();

  const writes: Promise<void>[] = [];
  if (body.current) writes.push(c.env.APP_VERSIONS.put(`${body.platform}:current`, body.current));
  if (body.minimum) writes.push(c.env.APP_VERSIONS.put(`${body.platform}:min`, body.minimum));
  await Promise.all(writes);

  return c.json({ ok: true });
});

export default app;
```

## Implementation Details

**KV layout** — four keys cover both platforms: `ios:current`, `ios:min`, `android:current`, `android:min`. Values are plain semver strings (`2.4.0`). CI pipelines call the admin `PUT /admin/version` endpoint immediately after a successful App Store / Play Store submission.

**D1 schema** — `changelogs` table has columns `(id INTEGER PRIMARY KEY, platform TEXT, version TEXT, sort_key TEXT, released_at TEXT, highlights TEXT)`. `sort_key` is a zero-padded concatenation of major/minor/patch (`002004000`) enabling simple string ordering without a semver SQL extension.

**A/B test** — the `update_prompt_timing` KV key is toggled by your experimentation system. The mobile client reads the `prompt_timing` field and either shows the modal on cold start (`immediate`) or waits until the user finishes their current flow (`natural`). Because the flag is per-request, you can use a percentage rollout by adding a thin routing layer that reads a user-segment cookie.

**Analytics Engine** — each check writes one data point. The `indexes` array enables fast group-by in `SELECT blob1, blob3, sum(double1) FROM UPDATE_ANALYTICS GROUP BY blob1, blob3` (platform + decision). Run this query daily from a Scheduled Worker to build a rolling adoption dashboard.

**Cache headers** — `current` responses are safe to cache for 5 minutes at the CDN edge. Stale `current` responses do no harm. `force_update` / `soft_update` responses use a 60-second TTL so a version bump is propagated quickly.

## Anti-patterns

- **Hard-coding versions in the bundle.** Any version change requires a new app submission. Use the KV-backed endpoint instead.
- **Returning `force_update` for all older versions.** Reserve forced updates only for versions with known security vulnerabilities or broken API contracts. Overusing it kills retention.
- **Querying D1 synchronously for every check.** Changelog data changes rarely; cache the D1 result in KV with a 10-minute TTL to avoid unnecessary D1 reads at high volume.
- **Ignoring the A/B timing field on the client.** If the client always shows the modal immediately, the A/B test produces no signal.

## Gotchas

- `KVNamespace.get()` returns `null` (not `undefined`) when a key is absent. Guard with a null check, not a falsy check, if an empty string is a valid value.
- Semver pre-release suffixes (`2.4.0-beta.1`) break the simple `split('.')` approach. Strip pre-release identifiers before comparison, or disallow them in the KV values.
- Analytics Engine `writeDataPoint` is asynchronous but Cloudflare batches and flushes it automatically — do **not** `await` it on the critical path; assign the call without awaiting so the response is not delayed.
- `d1.prepare().bind().all()` throws on a D1 error rather than returning an error field; wrap in try/catch and return a partial response rather than a 500.

## Verification

```bash
# Seed KV via wrangler
wrangler kv key put --binding=APP_VERSIONS "ios:current" "2.5.0"
wrangler kv key put --binding=APP_VERSIONS "ios:min"     "2.3.0"

# Current — expect decision: "current"
curl "https://api.example.com/update-check?platform=ios&version=2.5.0"

# Soft update — expect decision: "soft_update"
curl "https://api.example.com/update-check?platform=ios&version=2.4.1"

# Force update — expect decision: "force_update"
curl "https://api.example.com/update-check?platform=ios&version=2.2.9"

# Bad input — expect 400
curl "https://api.example.com/update-check?platform=ios&version=notasemver"
```

## Related

- `documentation/categories/mobile/workers-app-config-remote.md` — feature flags & remote config complement update gating
- `documentation/categories/mobile/mobile-api-versioning.md` — API deprecation strategy that pairs with forced updates
- `documentation/categories/mobile/workers-session-refresh-token-rotation.md` — force-logout on version-gated auth changes

## Sources

- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Semantic Versioning specification: https://semver.org/
