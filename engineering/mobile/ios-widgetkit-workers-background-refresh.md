# iOS WidgetKit Workers Background Refresh

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your iOS widget shows stale data because `TimelineProvider` calls a Workers API
that is rate-limited, cold-starting, or returning cached responses that don't
reflect latest database state. You need reliable, fresh widget content with
minimal battery and Workers invocation cost.

---

## Context

WidgetKit runs `TimelineProvider.getTimeline(in:completion:)` in a budget-constrained
background process. Each widget family is allotted ~40–70 background refreshes per day.
Exceeding the budget causes WidgetKit to throttle updates silently. Workers must respond
in under 15 seconds or the provider times out.

Stack:
- iOS 17+ / Swift 5.9
- WidgetKit + App Intents
- Cloudflare Workers (TypeScript) + KV

---

## 1. TimelineProvider Fetching from Workers

```swift
// Widget/Provider.swift
import WidgetKit
import SwiftUI

struct DashboardEntry: TimelineEntry {
    let date: Date
    let metric: Double
    let label: String
}

struct DashboardProvider: TimelineProvider {
    func placeholder(in context: Context) -> DashboardEntry {
        DashboardEntry(date: .now, metric: 0, label: "Loading…")
    }

    func getSnapshot(in context: Context, completion: @escaping (DashboardEntry) -> Void) {
        Task {
            let entry = (try? await fetchEntry()) ?? placeholder(in: context)
            completion(entry)
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<DashboardEntry>) -> Void) {
        Task {
            do {
                let entry = try await fetchEntry()
                // Refresh every 15 minutes — WidgetKit may honour this or throttle
                let nextRefresh = Calendar.current.date(byAdding: .minute, value: 15, to: .now)!
                let timeline = Timeline(entries: [entry], policy: .after(nextRefresh))
                completion(timeline)
            } catch {
                // On failure, retry in 5 minutes
                let retryDate = Calendar.current.date(byAdding: .minute, value: 5, to: .now)!
                let fallback = DashboardEntry(date: .now, metric: 0, label: "Unavailable")
                completion(Timeline(entries: [fallback], policy: .after(retryDate)))
            }
        }
    }

    private func fetchEntry() async throws -> DashboardEntry {
        let url = URL(string: "https://api.example.com/widget/dashboard")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 12   // under WidgetKit's 15-second limit
        // Attach cached credentials from shared App Group keychain
        if let token = SharedKeychain.read(key: "widgetToken") {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, _) = try await URLSession.shared.data(for: request)
        let payload = try JSONDecoder().decode(WidgetPayload.self, from: data)
        return DashboardEntry(date: .now, metric: payload.metric, label: payload.label)
    }
}

struct WidgetPayload: Decodable {
    let metric: Double
    let label: String
}
```

---

## 2. Workers Widget Endpoint with KV Cache

```typescript
// workers/src/widget.ts
import { Hono } from 'hono'
import { verify } from '@tsndr/cloudflare-worker-jwt'

interface Env {
  WIDGET_CACHE: KVNamespace
  DB: D1Database
  JWT_SECRET: string
}

const app = new Hono<{ Bindings: Env }>()

const CACHE_TTL = 60 * 5  // 5 minutes in KV

app.get('/widget/dashboard', async (c) => {
  // Auth: widget tokens are short-lived (24 h) read-only JWTs
  const authHeader = c.req.header('Authorization')
  if (!authHeader?.startsWith('Bearer ')) return c.json({ error: 'unauthorized' }, 401)
  const token = authHeader.slice(7)
  const valid = await verify(token, c.env.JWT_SECRET)
  if (!valid) return c.json({ error: 'invalid_token' }, 401)

  const { payload } = valid as { payload: { sub: string } }
  const userId = payload.sub
  const cacheKey = `widget:dashboard:${userId}`

  // Try KV cache first
  const cached = await c.env.WIDGET_CACHE.get(cacheKey, 'json') as WidgetData | null
  if (cached) {
    return c.json(cached, 200, { 'X-Cache': 'HIT' })
  }

  // Compute fresh data from D1
  const row = await c.env.DB.prepare(
    `SELECT metric_value, metric_label
       FROM user_metrics
      WHERE user_id = ?
      ORDER BY recorded_at DESC
      LIMIT 1`
  ).bind(userId).first<{ metric_value: number; metric_label: string }>()

  const data: WidgetData = {
    metric: row?.metric_value ?? 0,
    label: row?.metric_label ?? 'No data',
  }

  await c.env.WIDGET_CACHE.put(cacheKey, JSON.stringify(data), { expirationTtl: CACHE_TTL })
  return c.json(data, 200, { 'X-Cache': 'MISS' })
})

interface WidgetData { metric: number; label: string }

export default app
```

---

## 3. Shared App Group Keychain for Widget Token

```swift
// Shared/SharedKeychain.swift
import Security

enum SharedKeychain {
    private static let service = "group.com.example.app.widget"

    static func read(key: String) -> String? {
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: key,
            kSecReturnData: true
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func write(key: String, value: String) {
        let data = Data(value.utf8)
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: key,
            kSecValueData: data,
            kSecAttrAccessGroup: "$(AppIdentifierPrefix)group.com.example.app"
        ]
        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }
}
```

---

## 4. Issuing Widget Tokens from the Main App

```swift
// App/AuthService.swift
extension AuthService {
    /// Call after login to provision a read-only token for the widget process.
    func refreshWidgetToken() async throws {
        let widgetToken: String = try await api.post("/auth/widget-token")
        SharedKeychain.write(key: "widgetToken", value: widgetToken)
        WidgetCenter.shared.reloadAllTimelines()
    }
}
```

```typescript
// workers/src/auth.ts (snippet)
app.post('/auth/widget-token', async (c) => {
  // Validate the main session token first
  const mainToken = c.req.header('Authorization')?.slice(7)
  const session = await verifyMainToken(mainToken, c.env.JWT_SECRET)
  if (!session) return c.json({ error: 'unauthorized' }, 401)

  // Issue #<number>-hour read-only widget token
  const widgetToken = await sign(
    { sub: session.userId, scope: 'widget:read', exp: Math.floor(Date.now() / 1000) + 86400 },
    c.env.JWT_SECRET
  )
  return c.json({ token: widgetToken })
})
```

---

## 5. Forcing Refresh via Background App Refresh

```swift
// AppDelegate.swift
import BackgroundTasks

extension AppDelegate {
    func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: "com.example.app.widgetRefresh",
            using: nil
        ) { task in
            self.handleWidgetRefresh(task: task as! BGAppRefreshTask)
        }
    }

    func scheduleWidgetRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: "com.example.app.widgetRefresh")
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private func handleWidgetRefresh(task: BGAppRefreshTask) {
        scheduleWidgetRefresh()  // schedule the next one immediately
        Task {
            try? await AuthService.shared.refreshWidgetToken()
            task.setTaskCompleted(success: true)
        }
        task.expirationHandler = { task.setTaskCompleted(success: false) }
    }
}
```

---

## Anti-patterns

- **Fetching live data on every `getSnapshot` call**: `getSnapshot` should return
  near-instant placeholder data; heavy fetches belong in `getTimeline`.
- **Storing tokens in `UserDefaults`**: widget extensions run in a separate process
  and cannot read the main app's `UserDefaults`; use a shared App Group container or
  shared Keychain instead.
- **Ignoring KV cache**: each WidgetKit timeline reload triggers a fresh Workers
  invocation; without KV caching you'll burn Workers free-tier requests on low-traffic
  days.
- **Requesting `.atEnd` timeline reload policy**: WidgetKit may delay `.atEnd` by up to
  an hour; always supply an explicit `.after(date)` for time-sensitive content.

---

## Gotchas

- Widgets on StandBy (iOS 17 landscape bedside mode) refresh independently and have
  their own budget — test with StandBy enabled.
- `TimelineProvider` runs without an active network connection when the device is offline;
  handle `URLError.notConnectedToInternet` and return cached data gracefully.
- Workers KV values must be ≤25 MB; widget payloads are typically tiny, but if you embed
  images, store only the URL.
- Background App Refresh can be disabled by the user in Settings → Background App Refresh;
  `BGTaskScheduler.submit` silently succeeds even when it is disabled, but the task never
  runs — design for graceful degradation.

---

## Verification

```bash
# Simulate background task in Xcode debugger:
# Device -> Debug -> Simulate Background Fetch

# Check Workers KV cache hit rate
wrangler tail --format pretty | grep "X-Cache"

# Unit test timeline provider
swift test --filter DashboardProviderTests
```

---

## Related

- `ios-widget-extension.md`
- `ios-background-fetch.md`
- `ios-push-notifications-apns-workers.md`
- `ios-keychain-storage.md`
- `cloudflare-kv-read-latency-mobile-highlatency-vs-desktop.md`

---

## Sources

- WidgetKit documentation: https://developer.apple.com/documentation/widgetkit
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Apple BGTaskScheduler: https://developer.apple.com/documentation/backgroundtasks
- WidgetKit best practices WWDC23: https://developer.apple.com/videos/play/wwdc2023/10104/
