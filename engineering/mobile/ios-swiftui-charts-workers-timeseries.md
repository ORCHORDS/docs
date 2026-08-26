# iOS SwiftUI Charts Workers Realtime Timeseries

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

iOS dashboards need live-updating line charts showing metrics (orders per minute, active
sessions, revenue) that originate from a Cloudflare Workers + D1 aggregation pipeline.
Swift Charts (iOS 16+) is the native rendering solution, but wiring it to a live Workers
endpoint — including initial snapshot load and incremental Server-Sent Events (SSE) delta
updates — requires a disciplined data-flow pattern that avoids memory leaks and main-thread
violations.

## Context

`Swift Charts` renders `LineMark`, `AreaMark`, and `PointMark` from an `Identifiable`
data array bound to an `@Observable` store (iOS 17+) or `@StateObject` (iOS 16). A
Cloudflare Worker exposes two endpoints: a REST snapshot for initial load and an SSE stream
for 5-second delta pushes. `URLSessionDataDelegate` on iOS processes the SSE byte stream
without third-party dependencies. The store prunes old data points to bound memory growth.

---

## 1. Workers Timeseries Endpoints

```typescript
// worker/src/timeseries.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const metric = url.searchParams.get('metric') ?? 'orders';
    const rangeMin = parseInt(url.searchParams.get('range') ?? '60', 10);
    const since = Date.now() - rangeMin * 60_000;

    // --- snapshot ---
    if (url.pathname === '/timeseries/snapshot') {
      const { results } = await env.DB.prepare(
        'SELECT bucket_ts, value FROM metrics WHERE metric = ? AND bucket_ts > ? ORDER BY bucket_ts ASC'
      ).bind(metric, since).all();
      return Response.json(results, { headers: { 'Cache-Control': 'private, max-age=5' } });
    }

    // --- SSE stream ---
    if (url.pathname === '/timeseries/stream') {
      const { readable, writable } = new TransformStream();
      const writer = writable.getWriter();
      const enc = new TextEncoder();

      (async () => {
        let last = since;
        while (true) {
          const { results } = await env.DB.prepare(
            'SELECT bucket_ts, value FROM metrics WHERE metric = ? AND bucket_ts > ? ORDER BY bucket_ts ASC LIMIT 100'
          ).bind(metric, last).all() as { results: Array<{ bucket_ts: number; value: number }> };
          for (const row of results) {
            await writer.write(enc.encode(`data: ${JSON.stringify(row)}\n\n`));
            if (row.bucket_ts > last) last = row.bucket_ts;
          }
          await scheduler.wait(5_000);
        }
      })().catch(() => writer.close());

      return new Response(readable, {
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
      });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## 2. Swift Observable Data Store

```swift
// TimeseriesStore.swift
import Foundation
import Observation

struct DataPoint: Identifiable, Decodable {
    let id = UUID()
    let bucketTs: Int       // milliseconds epoch
    let value: Double

    enum CodingKeys: String, CodingKey {
        case bucketTs = "bucket_ts"
        case value
    }
}

@Observable
final class TimeseriesStore: NSObject, URLSessionDataDelegate {
    var points: [DataPoint] = []
    private var sseBuffer = Data()
    private var sseSession: URLSession?

    // MARK: - Snapshot

    func loadSnapshot(metric: String, workerBase: String) async throws {
        let url = URL(string: "\(workerBase)/timeseries/snapshot?metric=\(metric)")!
        let (data, _) = try await URLSession.shared.data(from: url)
        let decoded = try JSONDecoder().decode([DataPoint].self, from: data)
        await MainActor.run { points = decoded }

        // Persist for offline fallback
        UserDefaults.standard.set(data, forKey: "ts_\(metric)")
    }

    func loadSnapshotOfflineFallback(metric: String, workerBase: String) async {
        do {
            try await loadSnapshot(metric: metric, workerBase: workerBase)
        } catch {
            if let cached = UserDefaults.standard.data(forKey: "ts_\(metric)"),
               let decoded = try? JSONDecoder().decode([DataPoint].self, from: cached) {
                await MainActor.run { points = decoded }
            }
        }
    }

    // MARK: - SSE Stream

    func startStreaming(metric: String, workerBase: String) {
        let config = URLSessionConfiguration.default
        sseSession = URLSession(configuration: config, delegate: self, delegateQueue: nil)
        let url = URL(string: "\(workerBase)/timeseries/stream?metric=\(metric)")!
        sseSession?.dataTask(with: URLRequest(url: url)).resume()
    }

    // MARK: - URLSessionDataDelegate

    func urlSession(
        _ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data
    ) {
        sseBuffer.append(data)
        let separator = Data("\n\n".utf8)
        while let range = sseBuffer.range(of: separator) {
            let chunk = sseBuffer[..<range.lowerBound]
            sseBuffer.removeSubrange(..<range.upperBound)
            guard
                let line = String(data: chunk, encoding: .utf8),
                line.hasPrefix("data: "),
                let json = String(line.dropFirst(6)).data(using: .utf8),
                let point = try? JSONDecoder().decode(DataPoint.self, from: json)
            else { continue }

            DispatchQueue.main.async {
                self.points.append(point)
                self.pruneIfNeeded()
            }
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        // Reconnect on drop (Cloudflare enforces a 100 s request timeout)
        guard error != nil else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
            guard let self else { return }
            // Caller must re-call startStreaming; store the metric externally
        }
    }

    // MARK: - Memory management

    private func pruneIfNeeded(maxPoints: Int = 300) {
        if points.count > maxPoints {
            points = Array(points.suffix(maxPoints))
        }
    }
}
```

---

## 3. SwiftUI Chart View

```swift
// MetricsChartView.swift
import SwiftUI
import Charts

struct MetricsChartView: View {
    @State private var store = TimeseriesStore()
    @State private var metric: String
    private let workerBase: String

    init(metric: String, workerBase: String) {
        self.metric = metric
        self.workerBase = workerBase
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(metric.capitalized)
                .font(.headline)

            Chart(store.points) { point in
                let ts = Date(timeIntervalSince1970: Double(point.bucketTs) / 1_000)
                LineMark(
                    x: .value("Time", ts),
                    y: .value("Value", point.value)
                )
                .foregroundStyle(.blue)

                AreaMark(
                    x: .value("Time", ts),
                    y: .value("Value", point.value)
                )
                .foregroundStyle(.blue.opacity(0.12))
            }
            .chartXAxis {
                AxisMarks(values: .stride(by: .minute, count: 10)) {
                    AxisGridLine(); AxisTick(); AxisValueLabel(format: .dateTime.hour().minute())
                }
            }
            .chartYAxis { AxisMarks(position: .leading) }
            .frame(height: 220)
        }
        .padding()
        .task {
            await store.loadSnapshotOfflineFallback(metric: metric, workerBase: workerBase)
            store.startStreaming(metric: metric, workerBase: workerBase)
        }
    }
}
```

---

## 4. Auto-Reconnect on SSE Drop

```swift
// ReconnectingStore.swift — wraps TimeseriesStore with automatic reconnection
final class ReconnectingTimeseriesStore: ObservableObject {
    @Published var points: [DataPoint] = []
    private let inner = TimeseriesStore()
    private var metric: String = ""
    private var workerBase: String = ""

    func start(metric: String, workerBase: String) {
        self.metric = metric
        self.workerBase = workerBase
        connect()
    }

    private func connect() {
        inner.startStreaming(metric: metric, workerBase: workerBase)
        // Reconnect after Cloudflare's ~100 s hard limit plus jitter
        DispatchQueue.main.asyncAfter(deadline: .now() + 95 + Double.random(in: 0...5)) { [weak self] in
            self?.connect()
        }
    }
}
```

---

## 5. D1 Metrics Ingestion Worker (Supporting Endpoint)

```typescript
// worker/src/ingest.ts — accepts metric events from server-side producers
export async function ingestMetric(
  env: Env, metric: string, value: number
): Promise<void> {
  const bucketTs = Math.floor(Date.now() / 5_000) * 5_000; // 5 s bucket
  await env.DB.prepare(
    `INSERT INTO metrics (id, metric, bucket_ts, value)
     VALUES (?, ?, ?, ?)
     ON CONFLICT (metric, bucket_ts) DO UPDATE SET value = value + excluded.value`
  ).bind(crypto.randomUUID(), metric, bucketTs, value).run();
}
```

---

## Anti-patterns

- Polling with a `Timer` that re-fetches the full snapshot every 5 s — SSE delivers only new rows; full refetches waste D1 read quota.
- Appending points without pruning — a chart streaming 1 point per second for 1 hour creates 3,600 `DataPoint` allocations; prune to ~300.
- Dispatching UI mutations from `URLSessionDataDelegate` callbacks on the main thread directly — the delegate queue is a background queue; always use `DispatchQueue.main.async`.
- Relying on `Codable` key synthesis for `bucket_ts` → `bucketTs` — Swift does not auto-convert snake_case without a `CodingKeys` enum.

## Gotchas

- `Swift Charts` requires iOS 16+; add a version check and a fallback `List` or placeholder for iOS 15 targets.
- Cloudflare enforces a 100-second CPU time limit per Worker request; SSE streams using `scheduler.wait` must be on a paid plan or backed by Durable Objects Alarms for long-lived sessions.
- `Date(timeIntervalSince1970:)` expects seconds; D1 `bucket_ts` is stored in milliseconds — always divide by `1_000`.
- `@Observable` (Swift 5.9 / iOS 17) is incompatible with `URLSessionDataDelegate` protocol conformance directly; use `NSObject` as the base class and mark `@Observable` explicitly.

## Verification

```bash
# Insert a test metric row
wrangler d1 execute DB --command \
  "INSERT INTO metrics (id, metric, bucket_ts, value) VALUES ('$(uuidgen)', 'orders', $(date +%s)000, 7.5);"

# Confirm snapshot endpoint
curl "https://metrics.example.com/timeseries/snapshot?metric=orders&range=60" | jq .

# Stream a few SSE events
curl -N "https://metrics.example.com/timeseries/stream?metric=orders" | head -20
```

## Related

- `ios-swiftui-basics.md`
- `ios-swift-concurrency-async-await.md`
- `ios-live-activities-workers-real-time-updates.md`
- `mobile-analytics-patterns.md`
- `mobile-websocket-realtime-connections.md`

## Sources

- https://developer.apple.com/documentation/charts
- https://developers.cloudflare.com/d1/
- https://developer.apple.com/documentation/foundation/urlsessiondatadelegate
- https://developer.apple.com/documentation/observation
