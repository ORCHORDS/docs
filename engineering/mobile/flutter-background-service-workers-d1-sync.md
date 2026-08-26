# Flutter Background Service with Cloudflare Workers + D1 Sync

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Flutter app must sync local state to Cloudflare D1 (via a Workers API) while the app is
in the background or even terminated — for example, to flush pending form submissions, sync
sensor readings, or keep a local cache warm. The standard `dart:isolate` does not survive
process death on mobile, and periodic triggers differ significantly between iOS and Android.

## Context

Flutter's background execution model:
- **Android**: `WorkManager` (via `flutter_background_service` or `workmanager`) runs Dart
  code in a separate isolate with the Flutter engine re-initialised.
- **iOS**: Background fetch (`BGAppRefreshTask`) and background processing
  (`BGProcessingTask`) grant short windows (30 s and up to several minutes).

The `flutter_background_service` package provides a unified Dart API that bridges both
platforms. The background isolate gets its own `FlutterEngine` and cannot share memory with
the UI isolate — all shared state must go through a persistence layer (e.g. `sqflite`, Hive,
or `shared_preferences`).

Stack: Dart, Flutter 3.22+, `flutter_background_service ^5.0`, `http ^1.2`, `sqflite ^2.3`,
Cloudflare Workers + D1.

## Background Service Initialisation

```dart
// lib/background/background_service.dart
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_background_service_android/flutter_background_service_android.dart';

Future<void> initBackgroundService() async {
  final service = FlutterBackgroundService();

  await service.configure(
    androidConfiguration: AndroidConfiguration(
      onStart: onStart,
      isForegroundMode: false,         // uses WorkManager, not a foreground service
      autoStart: true,
      autoStartOnBoot: true,
      initialNotificationTitle: 'Syncing…',
      initialNotificationContent: '',
    ),
    iosConfiguration: IosConfiguration(
      autoStart: true,
      onForeground: onStart,           // called during foreground sessions
      onBackground: onIosBackground,   // called during BGAppRefreshTask
    ),
  );
}

@pragma('vm:entry-point')
Future<bool> onIosBackground(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();
  DartPluginRegistrant.ensureInitialized();
  await runSync();
  return true;
}

@pragma('vm:entry-point')
void onStart(ServiceInstance service) async {
  DartPluginRegistrant.ensureInitialized();

  if (service is AndroidServiceInstance) {
    service.on('setAsForeground').listen((_) => service.setAsForegroundService());
    service.on('setAsBackground').listen((_) => service.setAsBackgroundService());
  }

  // Periodic tick inside the background isolate
  Timer.periodic(const Duration(minutes: 15), (_) async {
    await runSync();
  });
}
```

## Local Pending Queue (sqflite)

```dart
// lib/data/pending_sync_dao.dart
import 'package:sqflite/sqflite.dart';

class PendingSyncDao {
  final Database _db;
  PendingSyncDao(this._db);

  static const _table = 'pending_sync';

  Future<void> enqueue(Map<String, dynamic> payload) async {
    await _db.insert(_table, {
      'payload': jsonEncode(payload),
      'created_at': DateTime.now().toIso8601String(),
      'attempts': 0,
    });
  }

  Future<List<Map<String, dynamic>>> fetchPending({int limit = 50}) async {
    final rows = await _db.query(
      _table,
      where: 'attempts < 5',
      orderBy: 'created_at ASC',
      limit: limit,
    );
    return rows;
  }

  Future<void> markSynced(int id) async {
    await _db.delete(_table, where: 'id = ?', whereArgs: [id]);
  }

  Future<void> incrementAttempts(int id) async {
    await _db.rawUpdate(
      'UPDATE $_table SET attempts = attempts + 1 WHERE id = ?',
      [id],
    );
  }
}
```

## Sync Runner

```dart
// lib/background/run_sync.dart
Future<void> runSync() async {
  final db  = await openDatabase('app.db', version: 1);
  final dao = PendingSyncDao(db);

  final pending = await dao.fetchPending();
  if (pending.isEmpty) return;

  final client = http.Client();
  try {
    for (final row in pending) {
      final id      = row['id'] as int;
      final payload = row['payload'] as String;

      final response = await client
          .post(
            Uri.parse('https://api.example.com/sync'),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ${await _readToken()}',
            },
            body: payload,
          )
          .timeout(const Duration(seconds: 15));

      if (response.statusCode == 200 || response.statusCode == 201) {
        await dao.markSynced(id);
      } else if (response.statusCode >= 400 && response.statusCode < 500) {
        // Permanent client error – do not retry
        await dao.markSynced(id);
        debugPrint('Sync item $id rejected: ${response.statusCode}');
      } else {
        await dao.incrementAttempts(id);
      }
    }
  } finally {
    client.close();
    await db.close();
  }
}

Future<String> _readToken() async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getString('access_token') ?? '';
}
```

## Cloudflare Workers Ingest Endpoint

```typescript
// worker.ts
interface SyncPayload {
  entityType: string
  entityId: string
  data: Record<string, unknown>
  clientTimestamp: number
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 })
    }

    const auth = request.headers.get('Authorization') ?? ''
    const token = auth.replace('Bearer ', '')
    const userId = await verifyToken(token, env.JWT_SECRET)
    if (!userId) return new Response('Unauthorized', { status: 401 })

    const body = await request.json<SyncPayload>()

    const stmt = env.DB.prepare(
      `INSERT INTO entity_events (user_id, entity_type, entity_id, data, client_ts, server_ts)
       VALUES (?, ?, ?, ?, ?, ?)`
    )

    await stmt.bind(
      userId,
      body.entityType,
      body.entityId,
      JSON.stringify(body.data),
      body.clientTimestamp,
      Date.now(),
    ).run()

    // Fan-out to a Queue for downstream processing
    await env.SYNC_QUEUE.send({ userId, ...body })

    return new Response(JSON.stringify({ status: 'ok' }), {
      headers: { 'Content-Type': 'application/json' },
    })
  },
}

async function verifyToken(token: string, secret: string): Promise<string | null> {
  try {
    // Minimal HMAC-SHA256 JWT verification
    const [header, payload, sig] = token.split('.')
    const key = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' }, false, ['verify'],
    )
    const valid = await crypto.subtle.verify(
      'HMAC', key,
      base64url(sig), new TextEncoder().encode(`${header}.${payload}`),
    )
    if (!valid) return null
    const claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    return claims.sub as string
  } catch {
    return null
  }
}

function base64url(s: string): Uint8Array {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(b64), c => c.charCodeAt(0))
}
```

## Registering the Service in App Startup

```dart
// lib/main.dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initBackgroundService();
  runApp(const MyApp());
}
```

## Anti-patterns

- **Spawning isolates directly with `Isolate.spawn`** — isolates created this way do not
  survive process death. Use `flutter_background_service` or `workmanager` so the platform
  re-launches Dart when the OS allows.
- **Holding open HTTP connections across background wake-ups** — create and close the
  `http.Client()` within each sync run. A kept-alive connection is unusable after the OS
  suspends the process.
- **Syncing on every app resume** — gate the sync trigger on a staleness check
  (`lastSyncAt + threshold < now`) to avoid redundant network calls.
- **Writing to sqflite from both the UI isolate and the background isolate simultaneously**
  — use WAL journal mode (`pragma journal_mode = WAL`) and keep the database open for the
  shortest possible window in the background isolate.

## Gotchas

- iOS `BGAppRefreshTask` budget is controlled by the OS based on usage patterns. A freshly
  installed app may not receive any background wakeups for several days. Do not rely on
  background sync for time-critical data on iOS.
- `flutter_background_service` v5 removed the `autoStart` shortcut on Android 14+ due to
  restrictions on starting background services from the background. Use `WorkManager`
  constraints (`requiresNetworkConnectivity: true`) and `autoStartOnBoot` only.
- `@pragma('vm:entry-point')` is mandatory on any function that the native layer calls
  directly. Without it, the Dart tree-shaker removes the function in release builds.
- The background isolate cannot call `platform channels` unless `DartPluginRegistrant
  .ensureInitialized()` is invoked first.

## Verification

```bash
# Android – trigger a WorkManager background task immediately
adb shell am broadcast \
  -a com.example.app.TRIGGER_SYNC \
  -n com.example.app/.SyncBroadcastReceiver

# Check WorkManager queue
adb shell dumpsys jobscheduler | grep -A 5 "flutter_background"

# iOS – simulate background fetch in Xcode
# Debug > Simulate Background Fetch

# Flutter logs from background isolate
flutter logs --device-id <device-id> 2>&1 | grep "BgService"
```

## Related

- `mobile-offline-first-sync-cloudflare-queues.md`
- `mobile-offline-sync-conflict-resolution.md`
- `flutter-workers-dart-client.md`
- `flutter-riverpod-workers-state-management.md`

## Sources

- flutter_background_service package — pub.dev/packages/flutter_background_service
- iOS Background Execution — developer.apple.com/documentation/backgroundtasks
- Cloudflare Queues — developers.cloudflare.com/queues
- sqflite WAL mode — pub.dev/packages/sqflite#-write-ahead-logging
