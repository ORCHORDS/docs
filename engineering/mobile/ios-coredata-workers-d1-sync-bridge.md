# iOS CoreData Workers D1 Sync Bridge

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

App stores structured data in CoreData for offline use and must synchronise it with a
Cloudflare D1 (SQLite-compatible) database via a Workers REST API. On first launch the device
pulls a full snapshot; subsequent sessions send only delta changes using a watermark timestamp.
Conflicts between local edits and remote writes must resolve deterministically without manual
merge UI.

## Context

CoreData's `NSManagedObjectContext` tracks local changes via `NSManagedObjectContextObjectsDidChangeNotification`
and `performBackgroundTask`. The Workers side uses D1's `updated_at` column as a vector clock.
A lightweight sync coordinator task runs on `BGAppRefreshTask` and posts change-sets to
`POST /api/sync` which upserts rows and returns server changes the client has not yet seen.

---

## 1. D1 Schema and Workers Sync Endpoint

```typescript
// worker/src/sync.ts
export interface SyncPayload {
  clientChanges: Record<string, unknown>[];
  watermark: string; // ISO timestamp of last successful sync
  deviceId: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST" || new URL(req.url).pathname !== "/api/sync") {
      return new Response("Not found", { status: 404 });
    }
    const { clientChanges, watermark, deviceId } =
      await req.json<SyncPayload>();

    // Upsert client changes into D1
    const stmt = env.DB.prepare(
      `INSERT INTO notes (id, title, body, updated_at, device_id)
       VALUES (?1, ?2, ?3, ?4, ?5)
       ON CONFLICT(id) DO UPDATE SET
         title = excluded.title,
         body = excluded.body,
         updated_at = excluded.updated_at,
         device_id = excluded.device_id
       WHERE excluded.updated_at > notes.updated_at`
    );
    const batch = clientChanges.map((c: any) =>
      stmt.bind(c.id, c.title, c.body, c.updated_at, deviceId)
    );
    await env.DB.batch(batch);

    // Return server changes since client's watermark
    const { results } = await env.DB.prepare(
      `SELECT id, title, body, updated_at FROM notes
       WHERE updated_at > ?1 AND device_id != ?2
       ORDER BY updated_at ASC LIMIT 500`
    ).bind(watermark, deviceId).all();

    return Response.json({
      serverChanges: results,
      newWatermark: new Date().toISOString(),
    });
  },
};
```

---

## 2. CoreData Model and Change Tracking

```swift
// CoreDataStack.swift
import CoreData

class CoreDataStack {
    static let shared = CoreDataStack()
    lazy var container: NSPersistentContainer = {
        let c = NSPersistentContainer(name: "AppModel")
        c.loadPersistentStores { _, error in
            if let error { fatalError("CoreData load failed: \(error)") }
        }
        c.viewContext.automaticallyMergesChangesFromParent = true
        c.viewContext.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
        return c
    }()

    /// Collect unsynchronised objects modified after `watermark`.
    func pendingChanges(after watermark: Date) throws -> [[String: Any]] {
        let ctx = container.newBackgroundContext()
        return try ctx.performAndWait {
            let req = NSFetchRequest<NSManagedObject>(entityName: "Note")
            req.predicate = NSPredicate(format: "syncedAt < updatedAt OR syncedAt == nil")
            let objects = try ctx.fetch(req)
            return objects.map { obj in
                [
                    "id": obj.value(forKey: "id") as? String ?? UUID().uuidString,
                    "title": obj.value(forKey: "title") as? String ?? "",
                    "body": obj.value(forKey: "body") as? String ?? "",
                    "updated_at": ISO8601DateFormatter().string(
                        from: obj.value(forKey: "updatedAt") as? Date ?? Date()
                    ),
                ]
            }
        }
    }
}
```

---

## 3. Sync Coordinator

```swift
// SyncCoordinator.swift
import Foundation

actor SyncCoordinator {
    private let stack = CoreDataStack.shared
    private let workersURL: URL
    private let deviceId: String

    init(workersURL: URL, deviceId: String) {
        self.workersURL = workersURL
        self.deviceId = deviceId
    }

    func sync() async throws {
        let watermarkKey = "sync_watermark"
        let watermarkStr = UserDefaults.standard.string(forKey: watermarkKey)
            ?? "1970-01-01T00:00:00Z"
        let watermarkDate = ISO8601DateFormatter().date(from: watermarkStr) ?? .distantPast

        let clientChanges = try stack.pendingChanges(after: watermarkDate)

        var req = URLRequest(url: workersURL.appendingPathComponent("/api/sync"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "clientChanges": clientChanges,
            "watermark": watermarkStr,
            "deviceId": deviceId,
        ])

        let (data, _) = try await URLSession.shared.data(for: req)
        let response = try JSONDecoder().decode(SyncResponse.self, from: data)
        try await applyServerChanges(response.serverChanges)
        UserDefaults.standard.set(response.newWatermark, forKey: watermarkKey)
    }

    private func applyServerChanges(_ changes: [NoteDTO]) async throws {
        let ctx = stack.container.newBackgroundContext()
        ctx.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
        try await ctx.perform {
            for dto in changes {
                let req = NSFetchRequest<NSManagedObject>(entityName: "Note")
                req.predicate = NSPredicate(format: "id == %@", dto.id)
                let existing = try ctx.fetch(req).first
                    ?? NSEntityDescription.insertNewObject(forEntityName: "Note", into: ctx)
                existing.setValue(dto.id, forKey: "id")
                existing.setValue(dto.title, forKey: "title")
                existing.setValue(dto.body, forKey: "body")
                existing.setValue(ISO8601DateFormatter().date(from: dto.updatedAt), forKey: "updatedAt")
                existing.setValue(Date(), forKey: "syncedAt")
            }
            try ctx.save()
        }
    }
}

struct SyncResponse: Decodable {
    let serverChanges: [NoteDTO]
    let newWatermark: String
}

struct NoteDTO: Decodable {
    let id: String
    let title: String
    let body: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, title, body
        case updatedAt = "updated_at"
    }
}
```

---

## 4. Background App Refresh Registration

```swift
// AppDelegate.swift
import BackgroundTasks

extension AppDelegate {
    static let syncTaskId = "com.example.app.sync"

    func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.syncTaskId,
            using: nil
        ) { task in
            self.handleSyncTask(task as! BGAppRefreshTask)
        }
    }

    func scheduleSyncTask() {
        let request = BGAppRefreshTaskRequest(identifier: Self.syncTaskId)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private func handleSyncTask(_ task: BGAppRefreshTask) {
        scheduleSyncTask() // schedule next run
        let coordinator = SyncCoordinator(
            workersURL: URL(string: ProcessInfo.processInfo.environment["WORKERS_URL"]!)!,
            deviceId: UIDevice.current.identifierForVendor!.uuidString
        )
        let syncTask = Task {
            try await coordinator.sync()
            task.setTaskCompleted(success: true)
        }
        task.expirationHandler = { syncTask.cancel() }
    }
}
```

---

## 5. Conflict Resolution Strategy in Workers

```typescript
// worker/src/conflict.ts
// Last-Write-Wins by updated_at with device tie-breaking
export function resolveConflict(
  local: { updated_at: string; device_id: string },
  remote: { updated_at: string; device_id: string }
): "local" | "remote" {
  const localMs = new Date(local.updated_at).getTime();
  const remoteMs = new Date(remote.updated_at).getTime();
  if (localMs !== remoteMs) return localMs > remoteMs ? "local" : "remote";
  // Deterministic tie-break: lexicographic device ID
  return local.device_id > remote.device_id ? "local" : "remote";
}
```

---

## Anti-patterns

- **Syncing on main thread** — CoreData fetches and network calls must run on a background
  context; blocking `viewContext` causes UI jank and potential watchdog kills.
- **Full-table sync on every open** — always use a watermark; re-downloading 10k rows wastes
  bandwidth and hits D1 row-read limits.
- **Trusting client clocks for conflict resolution** — supplement `updated_at` with a server-
  assigned sequence number or Durable Object monotonic counter when device clocks may skew.
- **Single merge policy on `viewContext`** — use `NSMergeByPropertyObjectTrumpMergePolicy` on
  background contexts only; leave `viewContext` as `NSMergeByPropertyStoreTrumpMergePolicy` so
  server data wins on the display layer.

## Gotchas

- **D1 `updated_at` precision** — D1 stores TEXT ISO strings; compare them with `>` not `>=`
  to avoid re-syncing the same row on every pass.
- **BGAppRefreshTask throttling** — iOS may delay or skip background refreshes aggressively;
  always trigger a sync on `sceneWillEnterForeground` as a fallback.
- **CoreData object IDs after insert** — freshly inserted objects have a temporary `objectID`
  until `save()` is called; obtain the permanent ID only after the save.
- **Workers D1 batch size limit** — `DB.batch()` accepts up to 1000 statements; chunk client
  changes into pages of 500 to stay well within limits.

## Verification

```bash
# Confirm D1 upsert logic
curl -X POST https://api.example.com/api/sync \
  -H 'Content-Type: application/json' \
  -d '{"clientChanges":[{"id":"abc","title":"T","body":"B","updated_at":"2026-08-23T10:00:00Z"}],"watermark":"1970-01-01T00:00:00Z","deviceId":"dev1"}'

# Check D1 row was written
wrangler d1 execute DB --command "SELECT * FROM notes WHERE id='abc'"

# Simulate two-device conflict
# Device 1 writes newer timestamp, device 2 writes older — verify device 1's row wins
```

## Related

- `ios-core-data-patterns.md`
- `ios-background-fetch.md`
- `mobile-offline-sync-conflict-resolution.md`
- `android-workmanager-workers-sync.md`

## Sources

- https://developers.cloudflare.com/d1/platform/sql-api/
- https://developer.apple.com/documentation/backgroundtasks/bgapprefreshtask
- https://developer.apple.com/documentation/coredata/nsmergebyproperty
- https://developers.cloudflare.com/d1/platform/limits/
