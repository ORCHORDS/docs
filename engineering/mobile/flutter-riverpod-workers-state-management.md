# Flutter Riverpod Workers State Management

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

Flutter app using Riverpod providers fetches data from Cloudflare Workers. Providers either
re-fetch on every navigation, stale data is served after background mutations, or error states
are lost during router transitions. Teams want a single source of truth that mirrors server
state held in Workers KV / D1 with minimal boilerplate.

## Context

Riverpod 2.x (code-generation variant) pairs well with a Cloudflare Workers REST backend:
`AsyncNotifierProvider` tracks inflight states, `ref.invalidate` acts as a targeted cache-bust,
and `keepAlive` preserves data across route rebuilds. The Workers side must return structured
JSON with consistent error envelopes so Dart sealed classes can pattern-match cleanly.

---

## 1. Workers JSON Contract

```typescript
// worker/src/api.ts
export interface ApiResponse<T> {
  data: T | null;
  error: string | null;
  ts: number; // epoch ms for stale detection
}

function ok<T>(data: T): ApiResponse<T> {
  return { data, error: null, ts: Date.now() };
}
function fail(msg: string): ApiResponse<null> {
  return { data: null, error: msg, ts: Date.now() };
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/api/items") {
      const { results } = await env.DB.prepare(
        "SELECT id, name, updated_at FROM items ORDER BY updated_at DESC LIMIT 50"
      ).all();
      return Response.json(ok(results));
    }
    return Response.json(fail("not found"), { status: 404 });
  },
};
```

---

## 2. Dart HTTP Client with Typed Response

```dart
// lib/data/workers_client.dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class WorkersClient {
  final String _base;
  final http.Client _http;

  const WorkersClient({required String base, required http.Client http})
      : _base = base,
        _http = http;

  Future<T> get<T>(
    String path,
    T Function(dynamic json) fromJson,
  ) async {
    final res = await _http.get(Uri.parse('$_base$path'));
    if (res.statusCode != 200) {
      final body = jsonDecode(res.body) as Map<String, dynamic>;
      throw ApiException(body['error'] as String? ?? 'Unknown error');
    }
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    return fromJson(body['data']);
  }
}

class ApiException implements Exception {
  final String message;
  const ApiException(this.message);
}
```

---

## 3. Riverpod AsyncNotifier Provider

```dart
// lib/providers/items_provider.dart
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../data/workers_client.dart';
import '../models/item.dart';

part 'items_provider.g.dart';

@riverpod
WorkersClient workersClient(WorkersClientRef ref) {
  return WorkersClient(
    base: const String.fromEnvironment('WORKERS_BASE_URL'),
    http: http.Client(),
  );
}

@riverpod
class ItemsNotifier extends _$ItemsNotifier {
  @override
  Future<List<Item>> build() async {
    ref.keepAlive(); // survive route pop/push
    return _fetch();
  }

  Future<List<Item>> _fetch() async {
    final client = ref.read(workersClientProvider);
    return client.get<List<Item>>(
      '/api/items',
      (json) => (json as List).map((e) => Item.fromJson(e as Map<String, dynamic>)).toList(),
    );
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_fetch);
  }

  Future<void> create(String name) async {
    final client = ref.read(workersClientProvider);
    await client.post('/api/items', {'name': name});
    ref.invalidateSelf(); // re-run build()
  }
}
```

---

## 4. Widget Consumption

```dart
// lib/screens/items_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/items_provider.dart';

class ItemsScreen extends ConsumerWidget {
  const ItemsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final itemsAsync = ref.watch(itemsNotifierProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Items'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.read(itemsNotifierProvider.notifier).refresh(),
          ),
        ],
      ),
      body: itemsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (items) => ListView.builder(
          itemCount: items.length,
          itemBuilder: (_, i) => ListTile(title: Text(items[i].name)),
        ),
      ),
    );
  }
}
```

---

## 5. Workers Mutation Endpoint with KV Invalidation

```typescript
// worker/src/mutations.ts
async function handleCreateItem(req: Request, env: Env): Promise<Response> {
  const body = await req.json<{ name: string }>();
  if (!body.name?.trim()) {
    return Response.json({ data: null, error: "name required" }, { status: 400 });
  }
  const id = crypto.randomUUID();
  await env.DB.prepare("INSERT INTO items (id, name, updated_at) VALUES (?, ?, ?)")
    .bind(id, body.name.trim(), new Date().toISOString())
    .run();
  // Purge list cache tag so next GET returns fresh data
  await env.CACHE_KV.delete("items:list");
  return Response.json({ data: { id }, error: null, ts: Date.now() }, { status: 201 });
}
```

---

## 6. Stale-While-Revalidate Pattern in Provider

```dart
// lib/providers/items_swr_provider.dart
@riverpod
Future<List<Item>> itemsSwr(ItemsSwrRef ref) async {
  final client = ref.read(workersClientProvider);
  // Serve cached data immediately, then refresh in background
  final cached = ref.state; // previous value if any
  final fresh = client.get<List<Item>>('/api/items', Item.fromJsonList);
  // keepAlive so the provider isn't disposed during await
  ref.keepAlive();
  return fresh; // Riverpod shows previous data while loading via .valueOrNull
}
```

---

## Anti-patterns

- **Global `ref.refresh` on every build** — call `refresh()` only on explicit user action or
  meaningful lifecycle event; excessive re-fetches waste egress and hit Workers CPU limits.
- **Throwing raw `http.Response` objects** — always unwrap to a typed `ApiException`; the
  Riverpod error state serialises the `.toString()` which becomes unreadable otherwise.
- **`autoDispose` on shared providers** — list providers should use `keepAlive` so multiple
  routes share the same fetch; use `autoDispose` only for per-screen detail providers.
- **Mutating local state before server confirms** — optimistic updates require rollback logic;
  keep it simple by calling `ref.invalidateSelf()` after the Workers write completes.

## Gotchas

- **`ref.read` inside `build()`** — use `ref.watch` for dependencies that should trigger rebuild;
  `ref.read` is for one-shot reads inside event handlers only.
- **`keepAlive` prevents GC** — pair it with `ref.onDispose` to cancel in-flight requests when
  the provider actually needs to be torn down on logout.
- **Workers response time variance** — cold-start latency (10–50 ms) can make `AsyncLoading`
  flash briefly; add a 200 ms delay before showing the loading spinner in the UI.
- **`const String.fromEnvironment` is compile-time** — the Workers base URL must be baked at
  build time via `--dart-define`; it cannot be changed at runtime without a new build.

## Verification

```bash
# Run provider tests with mocked HTTP
flutter test test/providers/items_provider_test.dart

# Check codegen ran cleanly
dart run build_runner build --delete-conflicting-outputs

# Confirm Workers endpoint returns correct envelope shape
curl -s https://api.example.com/api/items | jq '.data | length, .[0].id'

# Verify no extra fetches on navigation (watch logs)
flutter run --verbose 2>&1 | grep "WorkersClient.get"
```

## Related

- `flutter-workers-dart-client.md`
- `flutter-workers-error-reporting-analytics-engine.md`
- `mobile-offline-sync-conflict-resolution.md`
- `mobile-network-resilience-cloudflare-workers.md`

## Sources

- https://riverpod.dev/docs/concepts/async_initialization
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://pub.dev/packages/riverpod_annotation
- https://developers.cloudflare.com/d1/
