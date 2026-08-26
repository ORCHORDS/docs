# Flutter Workers D1 Cursor Pagination

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

`LIMIT/OFFSET` pagination breaks on large D1 tables: `OFFSET 5000` forces D1 to scan and discard 5000 rows on every request, response time grows linearly, and concurrent page loads with inserts cause rows to shift — users see duplicates or skipped items. Cursor-based pagination (`WHERE id > ?`) solves both: it is O(1) on an indexed column and immune to concurrent inserts.

## Context

D1 is SQLite at the edge. The cursor is the last `id` (or `(updated_at, id)` compound) seen by the client. Workers returns a page of rows and an opaque `next_cursor` the client sends on the next request. Flutter manages pagination state with a `PageController`-style notifier backed by Riverpod. The cursor is base64-encoded to hide implementation details from clients.

Pagination flow:
```
Flutter → GET /items?limit=20&cursor=<encoded>
Workers → D1 query WHERE id > <decoded cursor>
Workers → return rows + next_cursor (null if last page)
Flutter → append rows, store next_cursor
```

---

## Workers: Cursor Pagination Endpoint

```typescript
// workers/src/items/list.ts
import { Env } from '../types';

interface Item {
  id: number;
  title: string;
  created_at: string;
}

interface PageResponse {
  items: Item[];
  next_cursor: string | null;
  has_more: boolean;
}

function encodeCursor(id: number): string {
  return btoa(String(id));
}

function decodeCursor(cursor: string): number | null {
  try {
    const raw = atob(cursor);
    const id = parseInt(raw, 10);
    return Number.isFinite(id) ? id : null;
  } catch {
    return null;
  }
}

export async function handleItemsList(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '20', 10), 100);
  const cursorParam = url.searchParams.get('cursor');

  let query: string;
  let params: unknown[];

  if (cursorParam) {
    const lastId = decodeCursor(cursorParam);
    if (lastId === null) {
      return Response.json({ error: 'invalid_cursor' }, { status: 400 });
    }
    // Fetch one extra row to detect whether there are more pages
    query = `SELECT id, title, created_at FROM items WHERE id > ? ORDER BY id ASC LIMIT ?`;
    params = [lastId, limit + 1];
  } else {
    query = `SELECT id, title, created_at FROM items ORDER BY id ASC LIMIT ?`;
    params = [limit + 1];
  }

  const { results } = await env.DB.prepare(query)
    .bind(...params)
    .all<Item>();

  const hasMore = results.length > limit;
  const items = hasMore ? results.slice(0, limit) : results;
  const nextCursor = hasMore ? encodeCursor(items[items.length - 1].id) : null;

  return Response.json({
    items,
    next_cursor: nextCursor,
    has_more: hasMore,
  } satisfies PageResponse);
}
```

## Flutter: Pagination State Notifier (Riverpod)

```dart
// lib/features/items/items_notifier.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class ItemsState {
  final List<Map<String, dynamic>> items;
  final String? nextCursor;
  final bool isLoading;
  final bool hasMore;
  final String? error;

  const ItemsState({
    this.items = const [],
    this.nextCursor,
    this.isLoading = false,
    this.hasMore = true,
    this.error,
  });

  ItemsState copyWith({
    List<Map<String, dynamic>>? items,
    String? nextCursor,
    bool? isLoading,
    bool? hasMore,
    String? error,
  }) =>
      ItemsState(
        items: items ?? this.items,
        nextCursor: nextCursor ?? this.nextCursor,
        isLoading: isLoading ?? this.isLoading,
        hasMore: hasMore ?? this.hasMore,
        error: error,
      );
}

class ItemsNotifier extends AsyncNotifier<ItemsState> {
  static const _baseUrl = 'https://api.example.com';
  static const _pageSize = 20;

  @override
  Future<ItemsState> build() async {
    return _fetchPage(cursor: null, existing: []);
  }

  Future<ItemsState> _fetchPage({
    required String? cursor,
    required List<Map<String, dynamic>> existing,
  }) async {
    final uri = Uri.parse('$_baseUrl/items').replace(queryParameters: {
      'limit': '$_pageSize',
      if (cursor != null) 'cursor': cursor,
    });

    final token = await AuthService.instance.getValidToken();
    final response = await http.get(
      uri,
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode != 200) {
      throw Exception('HTTP ${response.statusCode}');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final newItems = (body['items'] as List).cast<Map<String, dynamic>>();

    return ItemsState(
      items: [...existing, ...newItems],
      nextCursor: body['next_cursor'] as String?,
      hasMore: body['has_more'] as bool,
      isLoading: false,
    );
  }

  Future<void> loadMore() async {
    final current = state.valueOrNull;
    if (current == null || current.isLoading || !current.hasMore) return;

    state = AsyncValue.data(current.copyWith(isLoading: true));

    try {
      final next = await _fetchPage(
        cursor: current.nextCursor,
        existing: current.items,
      );
      state = AsyncValue.data(next);
    } catch (e, st) {
      state = AsyncValue.data(current.copyWith(isLoading: false, error: e.toString()));
    }
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(
      () => _fetchPage(cursor: null, existing: []),
    );
  }
}

final itemsProvider = AsyncNotifierProvider<ItemsNotifier, ItemsState>(
  ItemsNotifier.new,
);
```

## Flutter: Infinite Scroll ListView

```dart
// lib/features/items/items_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'items_notifier.dart';

class ItemsScreen extends ConsumerStatefulWidget {
  const ItemsScreen({super.key});

  @override
  ConsumerState<ItemsScreen> createState() => _ItemsScreenState();
}

class _ItemsScreenState extends ConsumerState<ItemsScreen> {
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  void _onScroll() {
    final threshold = _scrollController.position.maxScrollExtent - 200;
    if (_scrollController.offset >= threshold) {
      ref.read(itemsProvider.notifier).loadMore();
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(itemsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Items')),
      body: state.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (data) => RefreshIndicator(
          onRefresh: () => ref.read(itemsProvider.notifier).refresh(),
          child: ListView.builder(
            controller: _scrollController,
            itemCount: data.items.length + (data.hasMore ? 1 : 0),
            itemBuilder: (context, index) {
              if (index == data.items.length) {
                // Footer: loading indicator or end-of-list label
                return data.isLoading
                    ? const Padding(
                        padding: EdgeInsets.all(16),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    : const SizedBox.shrink();
              }

              final item = data.items[index];
              return ListTile(
                key: ValueKey(item['id']),
                title: Text(item['title'] as String),
                subtitle: Text(item['created_at'] as String),
              );
            },
          ),
        ),
      ),
    );
  }
}
```

## Workers: Compound Cursor for Stable Sort (updated_at + id)

```typescript
// workers/src/items/listByDate.ts
// Use when sorting by updated_at — plain id cursor breaks here because
// newer rows can have lower IDs after deletions + re-inserts.

interface CompoundCursor {
  updated_at: string;
  id: number;
}

function encodeCompoundCursor(c: CompoundCursor): string {
  return btoa(JSON.stringify(c));
}

function decodeCompoundCursor(raw: string): CompoundCursor | null {
  try {
    return JSON.parse(atob(raw)) as CompoundCursor;
  } catch {
    return null;
  }
}

export async function handleItemsByDate(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '20', 10), 100);
  const cursorParam = url.searchParams.get('cursor');

  let query: string;
  let params: unknown[];

  if (cursorParam) {
    const cursor = decodeCompoundCursor(cursorParam);
    if (!cursor) return Response.json({ error: 'invalid_cursor' }, { status: 400 });

    // Stable: rows where (updated_at, id) > (cursor.updated_at, cursor.id)
    query = `
      SELECT id, title, updated_at FROM items
      WHERE (updated_at > ?) OR (updated_at = ? AND id > ?)
      ORDER BY updated_at ASC, id ASC
      LIMIT ?
    `;
    params = [cursor.updated_at, cursor.updated_at, cursor.id, limit + 1];
  } else {
    query = `SELECT id, title, updated_at FROM items ORDER BY updated_at ASC, id ASC LIMIT ?`;
    params = [limit + 1];
  }

  const { results } = await env.DB.prepare(query).bind(...params).all<{
    id: number;
    title: string;
    updated_at: string;
  }>();

  const hasMore = results.length > limit;
  const items = hasMore ? results.slice(0, limit) : results;
  const last = items.at(-1);
  const nextCursor = hasMore && last
    ? encodeCompoundCursor({ updated_at: last.updated_at, id: last.id })
    : null;

  return Response.json({ items, next_cursor: nextCursor, has_more: hasMore });
}
```

---

## Anti-patterns

- **LIMIT/OFFSET on large tables** — scanning and discarding N rows on every request is O(N); cursor pagination is O(log N) on an indexed column.
- **Exposing raw cursor values** — sending `cursor=12345` leaks your auto-increment ID sequence. Base64-encode (or HMAC-sign if enumeration is a security concern).
- **Single-column cursor on a non-unique sort column** — sorting by `updated_at` alone is non-deterministic when multiple rows share the same timestamp. Always break ties with `id`.
- **Not accounting for `has_more` in the UI** — if the Flutter list always shows a loading spinner at the bottom when `isLoading` is false but `hasMore` is true, a double `loadMore()` call fires immediately on first render. Guard with both flags.

---

## Gotchas

- **D1 `LIMIT + 1` trick** — fetching one extra row to detect `has_more` is the standard cursor pattern; it avoids a separate `COUNT(*)` query. Just slice before returning.
- **D1 row limit per query** — D1 caps result sets at 1000 rows per `all()` call. Keep page size ≤ 100 and let the cursor handle the rest.
- **Flutter `ListView.builder` key stability** — always pass `key: ValueKey(item['id'])` so Flutter can reconcile items correctly when the list grows. Without it, widget state (e.g. expansion tiles) jumps.
- **Riverpod `AsyncNotifier.state` vs `update`** — calling `state = AsyncValue.data(...)` while another async update is in flight can race. Use `ref.read(provider.notifier).loadMore()` (guarded by `isLoading`) rather than parallel calls.

---

## Verification

```bash
# Confirm D1 query uses index scan not full scan
wrangler d1 execute <db> --command \
  "EXPLAIN QUERY PLAN SELECT id, title, created_at FROM items WHERE id > 100 ORDER BY id ASC LIMIT 21"
# Expect: SEARCH items USING INDEX

# Test pagination chain
curl "https://api.example.com/items?limit=2"
# Copy next_cursor from response, then:
curl "https://api.example.com/items?limit=2&cursor=<next_cursor>"
```

---

## Related

- `android-workers-paging3-cursor-pagination.md`
- `flutter-workers-dart-client.md`
- `flutter-riverpod-workers-state-management.md`
- `capacitor-d1-sqlite-offline-sync.md`
- `react-native-reanimated-gesture-feed-workers-pagination.md`

---

## Sources

- Cloudflare D1 — https://developers.cloudflare.com/d1/
- SQLite cursor pagination best practices — https://www.sqlite.org/rowvalue.html
- flutter_riverpod AsyncNotifier — https://riverpod.dev/docs/concepts/providers#asyncnotifier
- Cursor-based pagination — https://use-the-index-luke.com/no-offset
