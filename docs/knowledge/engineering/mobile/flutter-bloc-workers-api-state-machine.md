# Flutter BLoC Workers API State Machine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Flutter screen fetches data from a Cloudflare Workers endpoint and must handle loading, success, empty, and error states with retry logic. Ad-hoc `setState` calls grow unmaintainable as the screen gains filters, pagination, and background refresh. You need a formal state machine: `flutter_bloc` as the event/state layer, Cloudflare Workers as the remote data source, and a clean boundary between UI and business logic.

## Context

`flutter_bloc` (by Felix Angelov) implements the BLoC (Business Logic Component) pattern via `Cubit` and `Bloc` classes. Each screen owns a `Bloc` that maps `Event → State`. Cloudflare Workers serve JSON from D1 or KV behind an authenticated endpoint. The BLoC fetches from Workers, handles pagination with a cursor, and exposes discrete states the widget tree responds to.

State machine:

```
Initial → Loading → Success(items, cursor, hasMore)
                 → Empty
                 → Failure(message, retryAfter)
Success → LoadingMore → Success (appended items)
```

## Workers API Endpoint

```typescript
// workers/items/index.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const cursor = url.searchParams.get("cursor") ?? null;
    const limit = Math.min(Number(url.searchParams.get("limit") ?? "20"), 100);

    const query = cursor
      ? env.DB.prepare(
          "SELECT id, title, created_at FROM items WHERE id > ? ORDER BY id ASC LIMIT ?"
        ).bind(cursor, limit + 1)
      : env.DB.prepare(
          "SELECT id, title, created_at FROM items ORDER BY id ASC LIMIT ?"
        ).bind(limit + 1);

    const { results } = await query.all<{ id: string; title: string; created_at: string }>();
    const hasMore = results.length > limit;
    const items = hasMore ? results.slice(0, limit) : results;
    const nextCursor = hasMore ? items[items.length - 1].id : null;

    return Response.json({ items, nextCursor, hasMore });
  },
};
```

## Dart Model and Repository

```dart
// lib/data/models/item_model.dart
class Item {
  const Item({required this.id, required this.title, required this.createdAt});

  final String id;
  final String title;
  final DateTime createdAt;

  factory Item.fromJson(Map<String, dynamic> json) => Item(
        id: json['id'] as String,
        title: json['title'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );
}

// lib/data/repositories/items_repository.dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/item_model.dart';

class ItemsPage {
  const ItemsPage({required this.items, required this.nextCursor, required this.hasMore});
  final List<Item> items;
  final String? nextCursor;
  final bool hasMore;
}

class ItemsRepository {
  static const _base = 'https://api.example.com';
  final http.Client _client;

  ItemsRepository({http.Client? client}) : _client = client ?? http.Client();

  Future<ItemsPage> fetchPage({String? cursor, int limit = 20}) async {
    final uri = Uri.parse('$_base/items').replace(queryParameters: {
      if (cursor != null) 'cursor': cursor,
      'limit': '$limit',
    });

    final response = await _client.get(uri, headers: {'Accept': 'application/json'});
    if (response.statusCode != 200) {
      throw Exception('Workers returned ${response.statusCode}');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return ItemsPage(
      items: (body['items'] as List).map((e) => Item.fromJson(e as Map<String, dynamic>)).toList(),
      nextCursor: body['nextCursor'] as String?,
      hasMore: body['hasMore'] as bool,
    );
  }
}
```

## BLoC Events and States

```dart
// lib/blocs/items/items_event.dart
abstract class ItemsEvent {}
class ItemsFetchRequested extends ItemsEvent {}
class ItemsLoadMoreRequested extends ItemsEvent {}
class ItemsRefreshRequested extends ItemsEvent {}

// lib/blocs/items/items_state.dart
abstract class ItemsState {}

class ItemsInitial extends ItemsState {}

class ItemsLoading extends ItemsState {}

class ItemsSuccess extends ItemsState {
  ItemsSuccess({required this.items, required this.nextCursor, required this.hasMore});
  final List<Item> items;
  final String? nextCursor;
  final bool hasMore;
}

class ItemsEmpty extends ItemsState {}

class ItemsLoadingMore extends ItemsSuccess {
  ItemsLoadingMore({required super.items, required super.nextCursor, required super.hasMore});
}

class ItemsFailure extends ItemsState {
  ItemsFailure({required this.message});
  final String message;
}
```

## BLoC Implementation

```dart
// lib/blocs/items/items_bloc.dart
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../data/repositories/items_repository.dart';
import 'items_event.dart';
import 'items_state.dart';

class ItemsBloc extends Bloc<ItemsEvent, ItemsState> {
  ItemsBloc({required ItemsRepository repository})
      : _repository = repository,
        super(ItemsInitial()) {
    on<ItemsFetchRequested>(_onFetch);
    on<ItemsLoadMoreRequested>(_onLoadMore);
    on<ItemsRefreshRequested>(_onRefresh);
  }

  final ItemsRepository _repository;

  Future<void> _onFetch(ItemsFetchRequested event, Emitter<ItemsState> emit) async {
    emit(ItemsLoading());
    try {
      final page = await _repository.fetchPage();
      if (page.items.isEmpty) {
        emit(ItemsEmpty());
      } else {
        emit(ItemsSuccess(items: page.items, nextCursor: page.nextCursor, hasMore: page.hasMore));
      }
    } catch (e) {
      emit(ItemsFailure(message: e.toString()));
    }
  }

  Future<void> _onLoadMore(ItemsLoadMoreRequested event, Emitter<ItemsState> emit) async {
    final current = state;
    if (current is! ItemsSuccess || !current.hasMore) return;

    emit(ItemsLoadingMore(items: current.items, nextCursor: current.nextCursor, hasMore: current.hasMore));
    try {
      final page = await _repository.fetchPage(cursor: current.nextCursor);
      emit(ItemsSuccess(
        items: [...current.items, ...page.items],
        nextCursor: page.nextCursor,
        hasMore: page.hasMore,
      ));
    } catch (e) {
      // Revert to previous success state on load-more failure
      emit(current);
    }
  }

  Future<void> _onRefresh(ItemsRefreshRequested event, Emitter<ItemsState> emit) async {
    // Keep showing content during pull-to-refresh
    final page = await _repository.fetchPage();
    if (page.items.isEmpty) {
      emit(ItemsEmpty());
    } else {
      emit(ItemsSuccess(items: page.items, nextCursor: page.nextCursor, hasMore: page.hasMore));
    }
  }
}
```

## Widget Layer

```dart
// lib/screens/items_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../blocs/items/items_bloc.dart';
import '../blocs/items/items_event.dart';
import '../blocs/items/items_state.dart';

class ItemsScreen extends StatelessWidget {
  const ItemsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (ctx) => ItemsBloc(repository: ctx.read())..add(ItemsFetchRequested()),
      child: Scaffold(
        appBar: AppBar(title: const Text('Items')),
        body: BlocBuilder<ItemsBloc, ItemsState>(
          builder: (context, state) => switch (state) {
            ItemsLoading() => const Center(child: CircularProgressIndicator()),
            ItemsEmpty() => const Center(child: Text('No items found')),
            ItemsFailure(:final message) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(message),
                    ElevatedButton(
                      onPressed: () => context.read<ItemsBloc>().add(ItemsFetchRequested()),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            ItemsSuccess(:final items, :final hasMore) => RefreshIndicator(
                onRefresh: () async =>
                    context.read<ItemsBloc>().add(ItemsRefreshRequested()),
                child: ListView.builder(
                  itemCount: items.length + (hasMore ? 1 : 0),
                  itemBuilder: (ctx, i) {
                    if (i == items.length) {
                      context.read<ItemsBloc>().add(ItemsLoadMoreRequested());
                      return const Center(child: CircularProgressIndicator());
                    }
                    return ListTile(title: Text(items[i].title));
                  },
                ),
              ),
            _ => const SizedBox.shrink(),
          },
        ),
      ),
    );
  }
}
```

## Anti-patterns

- **Using `Cubit` for complex flows**: `Cubit` lacks event tracing; use `Bloc` when you need pagination or multi-event orchestration.
- **Fetching directly from the widget**: always route network calls through the repository injected into the BLoC, never call `http` from `build()`.
- **Emitting `ItemsLoading` on load-more**: this wipes the existing list from the UI. Emit `ItemsLoadingMore` (a `Success` subclass) to keep items visible.
- **Ignoring Emitter completion**: `on<>` handlers with `async` that `await` after `emit()` can cause state emissions after BLoC close. Check `emit.isDone` if you have branching async paths.

## Gotchas

- Workers D1 cursors are opaque IDs, not page numbers. Do not assume sequential integers; store the last row's `id` as the cursor.
- `flutter_bloc` 8.x requires Dart 3 pattern matching (`switch (state) { ItemsSuccess() => … }`). Downgrade to `when` / `is` checks on Dart 2.
- `BlocProvider.of<ItemsBloc>(context)` throws if called outside the subtree. Use `context.read<ItemsBloc>()` inside callbacks, `context.watch<ItemsBloc>()` only inside `build`.
- Dispose the `ItemsBloc` automatically via `BlocProvider`; do not call `.close()` manually in `dispose()` of a `StatefulWidget` that owns a `BlocProvider`.

## Verification

```bash
# Seed D1 with test rows
wrangler d1 execute MY_DB --command \
  "INSERT INTO items (id, title, created_at) VALUES ('1','Alpha','2026-01-01'),('2','Beta','2026-01-02')"

# Confirm Workers endpoint returns expected shape
curl "https://api.example.com/items?limit=1"
# {"items":[{"id":"1","title":"Alpha","created_at":"2026-01-01"}],"nextCursor":"1","hasMore":true}

# In Flutter, run integration test:
# flutter test integration_test/items_bloc_test.dart
```

## Related

- `flutter-riverpod-workers-state-management.md`
- `flutter-workers-d1-cursor-pagination.md`
- `flutter-workers-dart-client.md`
- `mobile-offline-sync-conflict-resolution.md`

## Sources

- https://bloclibrary.dev
- https://developers.cloudflare.com/d1/
- https://pub.dev/packages/flutter_bloc
