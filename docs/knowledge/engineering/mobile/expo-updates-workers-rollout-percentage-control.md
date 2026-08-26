# Expo Updates Rollout Percentage Control via Cloudflare Workers

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You ship OTA updates with Expo Updates but have no reliable way to do a graduated rollout — you want 5% of users on the new bundle for 24 hours before widening to 25%, 75%, then 100%. The default EAS Update `rollout` field is coarse, lives in the EAS dashboard, and cannot react to error-rate signals automatically. You need a Worker that gates bundle eligibility per device, increments rollout cohorts stored in KV, and can halt a rollout if crash rates spike.

---

## Context

Expo Updates clients call a manifest endpoint to discover the latest available update. By default that endpoint is EAS (`https://u.expo.dev/…`). You can override the `updates.url` in `app.config.ts` to point at your own Worker, which proxies to EAS but intercepts the eligibility decision.

The Worker holds rollout state in KV:

- `rollout:{updateId}:config` — `{ percentage: number, paused: boolean, createdAt: number }`
- `rollout:{updateId}:cohort:{deviceId}` — `"in" | "out"` (TTL = 7 days)

When a device requests a manifest the Worker deterministically assigns it to "in" or "out" based on a hash of `deviceId + updateId`, then validates that assignment against the current percentage. Cohort assignments are sticky once written to KV.

```toml
# wrangler.toml
name = "expo-rollout-gateway"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "ROLLOUT"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
EAS_PROJECT_ID = "YOUR_EAS_PROJECT_ID"
EAS_RUNTIME_VERSION = "1.0.0"
```

---

## 1. Rollout Config Management Endpoints

```typescript
// src/config.ts
export interface RolloutConfig {
  updateId: string;
  percentage: number; // 0-100
  paused: boolean;
  createdAt: number;
}

export async function getRolloutConfig(
  kv: KVNamespace,
  updateId: string,
): Promise<RolloutConfig | null> {
  return kv.get<RolloutConfig>(`rollout:${updateId}:config`, "json");
}

export async function setRolloutConfig(
  kv: KVNamespace,
  config: RolloutConfig,
): Promise<void> {
  await kv.put(
    `rollout:${config.updateId}:config`,
    JSON.stringify(config),
  );
}
```

---

## 2. Deterministic Cohort Assignment

```typescript
// src/cohort.ts

// Returns a float in [0, 1) deterministically from device+update pair.
async function stableHash(deviceId: string, updateId: string): Promise<number> {
  const data = new TextEncoder().encode(`${deviceId}:${updateId}`);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const view = new DataView(hashBuffer);
  // Use first 4 bytes as uint32, normalise to [0,1)
  return view.getUint32(0) / 0xffffffff;
}

export async function assignCohort(
  kv: KVNamespace,
  deviceId: string,
  updateId: string,
  percentage: number,
): Promise<"in" | "out"> {
  const cohortKey = `rollout:${updateId}:cohort:${deviceId}`;

  // Check for existing sticky assignment
  const existing = await kv.get<"in" | "out">(cohortKey, "json");
  if (existing) return existing;

  // Assign deterministically
  const h = await stableHash(deviceId, updateId);
  const assignment: "in" | "out" = h * 100 < percentage ? "in" : "out";

  await kv.put(cohortKey, JSON.stringify(assignment), {
    expirationTtl: 60 * 60 * 24 * 7, // 7 days
  });

  return assignment;
}
```

---

## 3. Manifest Proxy Worker

```typescript
// src/index.ts
import { getRolloutConfig } from "./config";
import { assignCohort } from "./cohort";

export interface Env {
  ROLLOUT: KVNamespace;
  EAS_PROJECT_ID: string;
}

const EAS_MANIFEST_BASE = "https://u.expo.dev";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Admin: set rollout percentage
    // PUT /admin/rollout/:updateId  body: { percentage, paused }
    if (request.method === "PUT" && url.pathname.startsWith("/admin/rollout/")) {
      const updateId = url.pathname.split("/").pop()!;
      const body = await request.json<{ percentage: number; paused?: boolean }>();
      await env.ROLLOUT.put(
        `rollout:${updateId}:config`,
        JSON.stringify({
          updateId,
          percentage: body.percentage,
          paused: body.paused ?? false,
          createdAt: Date.now(),
        }),
      );
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    // Expo Updates manifest request
    if (request.method === "GET" && url.pathname === "/manifest") {
      const deviceId = request.headers.get("expo-device-id") ?? "unknown";
      const runtimeVersion = request.headers.get("expo-runtime-version") ?? "";
      const platform = request.headers.get("expo-platform") ?? "";

      // Forward to EAS to get the latest manifest
      const easUrl = `${EAS_MANIFEST_BASE}/${env.EAS_PROJECT_ID}?channel-name=production&runtime-version=${runtimeVersion}&platform=${platform}`;
      const easResponse = await fetch(easUrl, {
        headers: {
          accept: "application/expo+json,application/json",
          "expo-runtime-version": runtimeVersion,
          "expo-platform": platform,
        },
      });

      if (!easResponse.ok) {
        return easResponse;
      }

      const manifest = await easResponse.json<{ id?: string; [k: string]: unknown }>();
      const updateId = manifest.id;

      if (!updateId) {
        // No update available — pass through
        return new Response(JSON.stringify(manifest), {
          status: 200,
          headers: { "content-type": "application/expo+json" },
        });
      }

      // Check rollout config
      const config = await getRolloutConfig(env.ROLLOUT, updateId);

      if (!config) {
        // No gating configured — serve the update to everyone
        return new Response(JSON.stringify(manifest), {
          status: 200,
          headers: { "content-type": "application/expo+json" },
        });
      }

      if (config.paused) {
        // Rollout paused — return no-update response
        return new Response(JSON.stringify(null), {
          status: 200,
          headers: {
            "content-type": "application/expo+json",
            "expo-update-id": "",
          },
        });
      }

      const cohort = await assignCohort(env.ROLLOUT, deviceId, updateId, config.percentage);

      if (cohort === "out") {
        return new Response(JSON.stringify(null), {
          status: 200,
          headers: { "content-type": "application/expo+json" },
        });
      }

      return new Response(JSON.stringify(manifest), {
        status: 200,
        headers: { "content-type": "application/expo+json" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## 4. Expo Client Configuration

```typescript
// app.config.ts
import { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: "MyApp",
  slug: "my-app",
  runtimeVersion: "1.0.0",
  updates: {
    // Point at your Worker instead of the default EAS endpoint
    url: "https://expo-rollout-gateway.YOUR_ACCOUNT.workers.dev/manifest",
    checkAutomatically: "ON_LOAD",
    fallbackToCacheTimeout: 5000,
  },
  extra: {
    eas: { projectId: "YOUR_EAS_PROJECT_ID" },
  },
};

export default config;
```

---

## 5. Automated Rollout Widening (Scheduled Worker)

```typescript
// src/scheduler.ts — attach as a Cron Trigger in wrangler.toml
// Cron: "0 */6 * * *"  (every 6 hours)
export async function scheduled(env: Env): Promise<void> {
  const keys = await env.ROLLOUT.list({ prefix: "rollout:", suffix: ":config" });
  for (const key of keys.keys) {
    const config = await env.ROLLOUT.get<{ updateId: string; percentage: number; paused: boolean; createdAt: number }>(key.name, "json");
    if (!config || config.paused || config.percentage >= 100) continue;

    // Auto-widen by 25 percentage points every 6 hours (max 100)
    const ageHours = (Date.now() - config.createdAt) / 3_600_000;
    const targetPct = Math.min(100, Math.floor(ageHours / 6) * 25 + 5);
    if (targetPct > config.percentage) {
      config.percentage = targetPct;
      await env.ROLLOUT.put(key.name, JSON.stringify(config));
    }
  }
}
```

---

## Anti-Patterns

- **Using random assignment on each request** — without KV stickiness a device flips between "in" and "out" on each app launch, causing update loops.
- **Storing the full bundle in Workers** — always proxy to EAS; Workers is gating logic only, not bundle storage.
- **Blocking the manifest response on slow KV reads** — set a 200 ms deadline with `Promise.race` and fall back to serving the update on timeout rather than blocking the app launch.
- **Widening automatically without error-rate signals** — wire up Cloudflare Analytics Engine or an external crash reporting webhook before enabling auto-widen.

---

## Gotchas

- `expo-device-id` is set by the Expo Updates client in SDK 50+; older clients send it as an empty string. Treat empty deviceId as a single synthetic bucket so you don't pollute KV with garbage keys.
- KV `list` with a suffix filter is not natively supported; keep a separate index key (`rollout:active-ids`) that you maintain alongside individual config keys.
- The EAS manifest response varies between `application/expo+json` and `application/json` depending on SDK version. Mirror the upstream `content-type` header exactly.

---

## Verification

1. Deploy the Worker, then run `expo start --clear` and watch the manifest request hit `wrangler tail`.
2. Set a rollout config with `percentage: 0` and confirm the app receives no update.
3. Set `percentage: 100` and confirm the app downloads the bundle.
4. Verify KV cohort stickiness: restart the app three times and confirm the same `"in"` or `"out"` value is returned for the same device.

---

## Related

- `expo-r2-ota-workers.md`
- `expo-eas-build-cloudflare-workers-secrets.md`
- `mobile-feature-flags-remote-config.md`
- `mobile-staged-rollout-phased-release.md`
- `mobile-forced-upgrade-minimum-version.md`

---

## Sources

- Expo Updates custom server: https://docs.expo.dev/eas-update/custom-server/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
