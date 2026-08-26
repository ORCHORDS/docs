# iOS TestFlight + Workers A/B Testing Feature Flags

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team ships a new UI flow or algorithm change and wants to test it exclusively on TestFlight
beta users before a full App Store rollout. Existing feature-flag services (LaunchDarkly,
Statsig) work, but you want the flag evaluation logic and targeting rules to live in Cloudflare
Workers so the same edge function powers both mobile and web — and you want to correlate flag
assignment with the TestFlight build number your testers are running.

---

## Context

TestFlight exposes two signals the app can read at runtime:

1. **Build number** (`CFBundleVersion`) — the numeric build identifier set at compile time.
2. **`isInTestFlight` heuristic** — detectable by checking the app's receipt URL path.

There is no official Apple API that returns "this device is a TestFlight install" but the
receipt sandbox URL is a reliable proxy. Combined with a Cloudflare Workers endpoint backed by
KV for flag definitions and D1 for assignment logging, you can:

- Gate features by build-number range (e.g. builds 200–249 = cohort A).
- Assign a stable random bucket (0–99) per `identifierForVendor` for percentage rollouts.
- Override individual testers by Apple ID hash stored in KV.
- Automatically graduate flags from TestFlight to production by changing the KV value without
  a new app release.

---

## Detecting TestFlight at Runtime (Swift)

```swift
// Sources/AppEnvironment.swift
import Foundation

enum AppChannel: String, Codable {
    case testFlight = "testflight"
    case appStore  = "appstore"
    case simulator = "simulator"
    case debug     = "debug"
}

struct AppEnvironment {
    static var channel: AppChannel {
        #if targetEnvironment(simulator)
        return .simulator
        #elseif DEBUG
        return .debug
        #else
        guard let receiptURL = Bundle.main.appStoreReceiptURL else { return .appStore }
        if receiptURL.path.contains("sandboxReceipt") { return .testFlight }
        return .appStore
        #endif
    }

    static var buildNumber: Int {
        Int(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "0") ?? 0
    }

    /// Stable per-device bucket 0–99 derived from identifierForVendor.
    static var assignmentBucket: Int {
        guard let idfv = UIDevice.current.identifierForVendor?.uuidString else { return 50 }
        let hash = idfv.utf8.reduce(0) { ($0 &* 31) &+ Int($1) }
        return abs(hash) % 100
    }
}
```

---

## Workers: Flag Evaluation Endpoint

```typescript
// workers/src/flags.ts
import { KVNamespace, D1Database } from "@cloudflare/workers-types";

interface Env {
  FLAGS: KVNamespace;      // flag definitions
  FLAG_LOG: D1Database;    // assignment audit log
}

interface FlagRequest {
  flagKeys: string[];
  context: {
    channel: "testflight" | "appstore" | "simulator" | "debug";
    buildNumber: number;
    bucket: number;        // 0–99
    deviceId: string;      // SHA-256 of identifierForVendor
    appVersion: string;
  };
}

interface FlagDefinition {
  enabled: boolean;
  channels: string[];
  buildRange?: { min: number; max: number };
  rolloutPct: number;      // 0–100
  overrides?: Record<string, boolean>; // deviceId hash → forced value
  variant?: string;
}

interface FlagResponse {
  flags: Record<string, { enabled: boolean; variant?: string }>;
  evaluatedAt: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = (await request.json()) as FlagRequest;
    const { flagKeys, context } = body;

    if (!flagKeys?.length || !context) {
      return new Response("Bad Request", { status: 400 });
    }

    const result: FlagResponse = { flags: {}, evaluatedAt: new Date().toISOString() };

    for (const key of flagKeys) {
      const raw = await env.FLAGS.get(key, { type: "json" }) as FlagDefinition | null;

      if (!raw) {
        result.flags[key] = { enabled: false };
        continue;
      }

      const enabled = evaluateFlag(raw, context);
      result.flags[key] = { enabled, variant: enabled ? raw.variant : undefined };
    }

    // Log assignment to D1 asynchronously (non-blocking)
    const insertStmt = env.FLAG_LOG.prepare(
      `INSERT INTO flag_assignments (device_id, channel, build_number, bucket, flags_json, evaluated_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    ).bind(
      context.deviceId,
      context.channel,
      context.buildNumber,
      context.bucket,
      JSON.stringify(result.flags)
    );

    // Fire-and-forget log
    const ctx = (globalThis as unknown as { waitUntil?: (p: Promise<unknown>) => void }).waitUntil;
    if (ctx) {
      // Inside a fetch handler that has ExecutionContext:
      // pass executionCtx.waitUntil(insertStmt.run()) in actual wiring
    }
    await insertStmt.run(); // simplified — use waitUntil in real Workers

    return Response.json(result);
  },
};

function evaluateFlag(def: FlagDefinition, ctx: FlagRequest["context"]): boolean {
  if (!def.enabled) return false;

  // Per-device override
  if (def.overrides && ctx.deviceId in def.overrides) {
    return def.overrides[ctx.deviceId];
  }

  // Channel gate
  if (def.channels.length && !def.channels.includes(ctx.channel)) return false;

  // Build range gate (for TestFlight canary builds)
  if (def.buildRange) {
    if (ctx.buildNumber < def.buildRange.min || ctx.buildNumber > def.buildRange.max) {
      return false;
    }
  }

  // Percentage rollout using stable device bucket
  if (ctx.bucket >= def.rolloutPct) return false;

  return true;
}
```

---

## KV Flag Definition Format

Store each flag as a KV key `flag:<name>` with a JSON value:

```json
{
  "enabled": true,
  "channels": ["testflight"],
  "buildRange": { "min": 200, "max": 249 },
  "rolloutPct": 50,
  "variant": "new_checkout_v2",
  "overrides": {
    "a1b2c3d4e5f6...": true
  }
}
```

Graduating to App Store: change `"channels": ["testflight", "appstore"]` and bump `rolloutPct`
to 100. No new release required.

---

## iOS Client: Flag SDK Wrapper

```swift
// Sources/FeatureFlags/FlagClient.swift
import CryptoKit
import Foundation

actor FlagClient {
    private let endpoint = URL(string: "https://api.example.com/flags")!
    private var cache: [String: Bool] = [:]
    private var cacheExpiry: Date = .distantPast

    func isEnabled(_ key: String) async -> Bool {
        if Date() < cacheExpiry, let v = cache[key] { return v }
        await refreshCache(keys: Array(cache.keys.isEmpty ? [key] : cache.keys))
        return cache[key] ?? false
    }

    func prefetch(keys: [String]) async {
        await refreshCache(keys: keys)
    }

    private func refreshCache(keys: [String]) async {
        guard let body = try? JSONEncoder().encode(makeFlagRequest(keys: keys)) else { return }
        guard let resp = try? await URLSession.shared.data(
            for: makeRequest(body: body)
        ) else { return }

        guard let decoded = try? JSONDecoder().decode(FlagResponse.self, from: resp.0) else { return }
        for (k, v) in decoded.flags { cache[k] = v.enabled }
        cacheExpiry = Date().addingTimeInterval(60) // 1-minute local cache
    }

    private func makeFlagRequest(keys: [String]) -> FlagRequest {
        FlagRequest(
            flagKeys: keys,
            context: .init(
                channel: AppEnvironment.channel.rawValue,
                buildNumber: AppEnvironment.buildNumber,
                bucket: AppEnvironment.assignmentBucket,
                deviceId: hashedDeviceId(),
                appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? ""
            )
        )
    }

    private func makeRequest(body: Data) -> URLRequest {
        var req = URLRequest(url: endpoint)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    private func hashedDeviceId() -> String {
        let idfv = UIDevice.current.identifierForVendor?.uuidString ?? "unknown"
        let digest = SHA256.hash(data: Data(idfv.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}

// Codable models matching Workers API shape
struct FlagRequest: Codable {
    let flagKeys: [String]
    let context: FlagContext
    struct FlagContext: Codable {
        let channel: String
        let buildNumber: Int
        let bucket: Int
        let deviceId: String
        let appVersion: String
    }
}

struct FlagResponse: Codable {
    let flags: [String: FlagValue]
    struct FlagValue: Codable {
        let enabled: Bool
        let variant: String?
    }
}
```

---

## D1 Schema for Assignment Logging

```sql
CREATE TABLE IF NOT EXISTS flag_assignments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL,
    channel         TEXT NOT NULL,
    build_number    INTEGER NOT NULL,
    bucket          INTEGER NOT NULL,
    flags_json      TEXT NOT NULL,
    evaluated_at    TEXT NOT NULL
);

CREATE INDEX idx_flag_assignments_device ON flag_assignments (device_id);
CREATE INDEX idx_flag_assignments_channel ON flag_assignments (channel, evaluated_at);
```

Query conversion rates per channel:

```sql
SELECT
  channel,
  json_extract(flags_json, '$.new_checkout_v2.enabled') AS in_treatment,
  COUNT(*) AS assignments
FROM flag_assignments
WHERE evaluated_at > datetime('now', '-7 days')
GROUP BY channel, in_treatment;
```

---

## Anti-patterns

- **Using `advertisingIdentifier` (IDFA) for bucket assignment.** Requires ATT permission and is
  blocked on TestFlight without explicit user consent. Use `identifierForVendor` instead.
- **Putting flag secrets (admin tokens) in the mobile app.** The flag evaluation endpoint should
  be read-only and keyed only by context. Admin mutations to KV definitions belong behind an
  authenticated internal endpoint.
- **Evaluating flags locally in the app from a downloaded JSON bundle.** You lose the ability
  to change targeting rules without a new release. Edge evaluation via Workers lets you update
  rules live.
- **Calling the flags endpoint on every app launch synchronously.** This adds latency to cold
  start. Prefetch async at startup and serve from the 1-minute in-memory cache.
- **Not gating by channel and assuming build number is sufficient.** After graduation to the App
  Store, `buildRange` alone would mis-target production users on the same build number.

---

## Gotchas

- The sandbox receipt URL trick fails for builds installed via Xcode directly; those return no
  receipt at all. Guard with `#if DEBUG` or the `targetEnvironment(simulator)` check first.
- TestFlight builds can be installed on production devices — the `channel` from `sandboxReceipt`
  is the ground truth, not the device type.
- KV has eventual consistency; flag changes propagate to all edge nodes within ~60 seconds.
  Do not rely on sub-second flag propagation for safety-critical gates.
- `identifierForVendor` resets on app reinstall and when all apps from your team ID are removed.
  Bucket assignment will shift for that user — acceptable for A/B tests, not for entitlements.

---

## Verification

```bash
# Write a test flag to KV
wrangler kv key put --namespace-id=<FLAGS_ID> "flag:new_checkout_v2" \
  '{"enabled":true,"channels":["testflight"],"buildRange":{"min":200,"max":999},"rolloutPct":50,"variant":"v2"}'

# Simulate flag evaluation
curl -X POST https://api.example.com/flags \
  -H "Content-Type: application/json" \
  -d '{"flagKeys":["new_checkout_v2"],"context":{"channel":"testflight","buildNumber":210,"bucket":25,"deviceId":"abc123","appVersion":"2.1.0"}}'

# Query D1 assignment log
wrangler d1 execute my-db --command \
  "SELECT channel, COUNT(*) FROM flag_assignments GROUP BY channel"
```

---

## Related

- `mobile-feature-flags-remote-config.md` — general feature flags overview
- `mobile-staged-rollout-phased-release.md` — App Store phased release mechanics
- `mobile-version-gating-workers-edge-flags.md` — version-based flag gating
- `expo-updates-workers-rollout-percentage-control.md` — OTA update percentage rollouts

---

## Sources

- https://developer.apple.com/documentation/xcode/distributing-your-app-to-beta-testers-using-testflight
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
- https://developer.apple.com/documentation/uikit/uidevice/1620059-identifierforvendor
