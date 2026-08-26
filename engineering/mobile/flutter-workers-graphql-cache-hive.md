# Flutter Workers GraphQL Cache Hive

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
The example project Flutter client fetches wam feeds, trending tags, and anonymous user profiles via a
GraphQL API backed by a Cloudflare Worker and D1. On flaky mobile connections, repeated identical
queries waste bandwidth and cause visible loading states on every navigation push. A persistent
Hive-based response cache keyed on the normalised query + variables hash eliminates redundant
round-trips and keeps the feed usable while offline.

## Context
The Cloudflare Worker exposes a GraphQL-over-HTTP endpoint (`POST /graphql`) with `ETag` and
`Cache-Control` response headers. The Flutter app uses `gql` + a custom `Link` that checks a
Hive box before executing the network fetch, writes successful responses back to Hive with a
per-query TTL, and falls back to the cached version when the Worker returns a non-2xx or when the
device is offline. Hive is chosen over `Isar` here because of its minimal overhead for pure
key-value JSON blobs and its synchronous read path inside a Flutter isolate.

## Architecture — Hive Box Schema
Each cached entry is stored in a Hive box named `gql_cache`. The key is a SHA-256 hex of
`operationName + JSON.stringify(variables)`. The value is a `GqlCacheEntry` TypeAdapter that
records the raw JSON body, the ETag, and the expiry timestamp.

```dart
// lib/cache/gql_cache_entry.dart
import 'package:hive_flutter/hive_flutter.dart';

part 'gql_cache_entry.g.dart';

@HiveType(typeId: 10)
class GqlCacheEntry extends HiveObject {
  @HiveField(0)
  final String body; // raw JSON string from Worker

  @HiveField(1)
  final String etag;

  @HiveField(2)
  final int expiresAt; // unix ms

  GqlCacheEntry({
    required this.body,
    required this.etag,
    required this.expiresAt,
  });

  bool get isExpired => DateTime.now().millisecondsSinceEpoch > expiresAt;
}
```

```dart
// lib/cache/gql_cache.dart
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'gql_cache_entry.dart';

class GqlCache {
  static const _boxName = 'gql_cache';
  late Box<GqlCacheEntry> _box;

  Future<void> init() async {
    await Hive.initFlutter();
    Hive.registerAdapter(GqlCacheEntryAdapter());
    _box = await Hive.openBox<GqlCacheEntry>(_boxName);
  }

  String _cacheKey(String operationName, Map<String, dynamic> variables) {
    final raw = '$operationName${jsonEncode(variables)}';
    return sha256.convert(utf8.encode(raw)).toString();
  }

  GqlCacheEntry? get(String operationName, Map<String, dynamic> variables) {
    final entry = _box.get(_cacheKey(operationName, variables));
    if (entry == null || entry.isExpired) return null;
    return entry;
  }

  Future<void> put(
    String operationName,
    Map<String, dynamic> variables,
    String body,
    String etag,
    Duration ttl,
  ) async {
    final key = _cacheKey(operationName, variables);
    await _box.put(
      key,
      GqlCacheEntry(
        body: body,
        etag: etag,
        expiresAt: DateTime.now().add(ttl).millisecondsSinceEpoch,
      ),
    );
  }

  Future<void> invalidate(String operationName, Map<String, dynamic> variables) async {
    await _box.delete(_cacheKey(operationName, variables));
  }

  Future<void> purgeExpired() async {
    final expired = _box.keys.where((k) => _box.get(k)?.isExpired == true).toList();
    await _box.deleteAll(expired);
  }
}
```

## Workers Side — GraphQL Endpoint with ETag
The Worker executes the GraphQL query against D1, computes a hash of the response body, and sends
it as an `ETag`. It also reads `If-None-Match` to return `304 Not Modified` for unchanged feeds,
saving downstream bandwidth.

```typescript
// worker/src/graphql.ts
import { Env } from './types';
import { buildSchema, graphql } from 'graphql';
import { schema } from './schema'; // your GraphQL schema definition
import { createRootValue } from './resolvers';

export async function handleGraphQL(request: Request, env: Env): Promise<Response> {
  const { query, operationName, variables } = (await request.json()) as {
    query: string;
    operationName?: string;
    variables?: Record<string, unknown>;
  };

  const result = await graphql({
    schema,
    source: query,
    rootValue: createRootValue(env),
    variableValues: variables,
    operationName,
  });

  const body = JSON.stringify(result);

  // ETag: first 16 hex chars of SHA-256 of the response body
  const hashBuffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
  const etag = `"${Array.from(new Uint8Array(hashBuffer))
    .slice(0, 8)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')}"`;

  const clientEtag = request.headers.get('If-None-Match');
  if (clientEtag === etag) {
    return new Response(null, { status: 304, headers: { ETag: etag } });
  }

  // Queries are cacheable; mutations must not be cached
  const isMutation = query.trimStart().startsWith('mutation');
  const cacheControl = isMutation
    ? 'no-store'
    : 'public, max-age=30, stale-while-revalidate=60';

  return new Response(body, {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': cacheControl,
      ETag: etag,
    },
  });
}
```

## Mobile Side — Custom GraphQL Link with Hive Cache
A `CachingHttpLink` wraps the standard `HttpLink`. On every query it checks Hive first; on cache
miss it fetches the Worker, updates Hive, and streams the result downstream. On mutation it
bypasses the cache and optionally invalidates related cached queries.

```dart
// lib/graphql/caching_http_link.dart
import 'dart:convert';
import 'package:gql_exec/gql_exec.dart';
import 'package:gql_link/gql_link.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import '../cache/gql_cache.dart';

class CachingHttpLink extends Link {
  final String url;
  final GqlCache cache;
  final Duration queryTtl;

  CachingHttpLink({
    required this.url,
    required this.cache,
    this.queryTtl = const Duration(minutes: 2),
  });

  @override
  Stream<Response> request(Request request, [NextLink? forward]) async* {
    final opName = request.operation.operationName ?? 'anonymous';
    final vars = request.variables;
    final isMutation = request.operation.document.definitions
        .any((d) => d.toString().contains('OperationType.mutation'));

    if (!isMutation) {
      final cached = cache.get(opName, vars);
      if (cached != null) {
        yield Response(data: jsonDecode(cached.body)['data'] as Map<String, dynamic>?);
        return;
      }
    }

    final connectivity = await Connectivity().checkConnectivity();
    if (connectivity == ConnectivityResult.none) {
      yield const Response(errors: [GraphQLError(message: 'No network connection')]);
      return;
    }

    final body = jsonEncode({
      'query': request.operation.document.toString(),
      'operationName': opName,
      'variables': vars,
    });

    final http = await Uri.parse(url).let((uri) async {
      return await Future(() => uri); // avoid dart2js analysis warning
    });

    final response = await (await _post(url, body));
    final responseBody = await response.body;

    if (response.statusCode == 200 && !isMutation) {
      final etag = response.headers['etag'] ?? '';
      await cache.put(opName, vars, responseBody, etag, queryTtl);
    }

    final json = jsonDecode(responseBody) as Map<String, dynamic>;
    yield Response(
      data: json['data'] as Map<String, dynamic>?,
      errors: (json['errors'] as List?)
          ?.map((e) => GraphQLError(message: e['message'] as String))
          .toList(),
    );
  }
}

// Minimal HTTP wrapper (use dio or http package in real code)
Future<_HttpResponse> _post(String url, String body) async {
  // Implementation using package:http
  throw UnimplementedError('wire up package:http here');
}

class _HttpResponse {
  final int statusCode;
  final Map<String, String> headers;
  final String body;
  const _HttpResponse({required this.statusCode, required this.headers, required this.body});
}

extension _Let<T> on T {
  R let<R>(R Function(T) block) => block(this);
}
```

## Cache Purge on Cold Start
On app start, stale Hive entries should be pruned to prevent the box from growing without bound.

```dart
// lib/app_startup.dart
import 'cache/gql_cache.dart';

final gqlCache = GqlCache();

Future<void> appStartup() async {
  await gqlCache.init();
  await gqlCache.purgeExpired(); // runs async, does not block UI
}
```

## Anti-patterns
- Caching mutations — mutations change server state; caching their response will serve stale data
  on subsequent queries if the mutation result is mistakenly stored.
- Using `SharedPreferences` for GraphQL blobs — `SharedPreferences` serialises to XML on Android
  and is not designed for large JSON payloads; Hive is faster and binary-safe.
- A fixed global TTL for all operations — feed queries go stale in seconds; user profile queries
  can be cached for minutes; differentiate TTL by operation name.
- Not validating the Hive TypeAdapter version after schema changes — bump `typeId` or add a
  migration step whenever `GqlCacheEntry` fields change to avoid decode panics.

## Gotchas
- `hive_flutter` requires calling `Hive.initFlutter()` before any box is opened; do this before
  `runApp`.
- The `crypto` package must be added to `pubspec.yaml` — it is not included with the Flutter SDK.
- GraphQL `operationName` is optional in the spec; anonymous queries must fall back to a stable
  hash of the query string to generate a cache key.
- The Worker `304 Not Modified` response has no body — do not attempt to `response.json()` on it
  in Dart; check `statusCode` first and read from the Hive entry instead.
- Hive is not thread-safe across isolates without the `HiveInterface` isolate workaround; keep all
  cache reads/writes on the main isolate or use a dedicated background isolate with a message
  channel.

## Verification
1. Open the Flutter app and navigate to the feed — confirm a GraphQL response is stored in Hive
   using `hive_inspector` or by printing `_box.length` in debug mode.
2. Enable airplane mode and navigate to a previously visited profile — data should render from
   Hive with no network error.
3. In the Worker logs (`wrangler tail`), confirm that repeated identical queries within the TTL
   window receive a `304` from the ETag check.
4. Trigger `purgeExpired()` manually and confirm `_box.length` decreases for entries past TTL.

## Related
- `/documentation/categories/mobile/flutter-riverpod-workers-state-management.md`
- `/documentation/categories/mobile/flutter-workers-dart-client.md`
- `/documentation/categories/mobile/mobile-offline-sync-conflict-resolution.md`
- `/documentation/categories/mobile/react-native-workers-graphql-codegen.md`

## Sources
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
- https://docs.hivedb.dev/
- https://pub.dev/packages/gql_link
- https://pub.dev/packages/connectivity_plus
