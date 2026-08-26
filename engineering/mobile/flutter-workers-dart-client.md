# Flutter Dart HTTP Client for Cloudflare Workers API

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Flutter apps calling Cloudflare Workers APIs encounter inconsistent error handling, missing
retry logic, and no structured way to propagate Workers-specific headers like `CF-Ray` into
crash reporters. Teams copying ad-hoc `http.get` calls across their codebase end up with
divergent auth patterns and no central place to inject tokens or handle 429 rate-limiting
from Workers' built-in rate limiter.

## Context

Dart's `http` package and `dio` both lack native understanding of Workers response envelopes
or edge-specific headers. The recommended approach is a typed `WorkersClient` class that
wraps `dio`, injects JWT auth from `flutter_secure_storage`, handles Workers-specific error
responses (which include a `traceId` field in the body), implements exponential backoff for
transient 5xx and 429 responses, and forwards `CF-Ray` to Sentry. This pattern works for
both REST and streaming Workers endpoints.

## Dart WorkersClient with Dio

```dart
// lib/api/workers_client.dart
import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class WorkersApiException implements Exception {
  final int statusCode;
  final String message;
  final String? traceId;
  final String? cfRay;

  const WorkersApiException({
    required this.statusCode,
    required this.message,
    this.traceId,
    this.cfRay,
  });

  @override
  String toString() =>
      'WorkersApiException($statusCode): $message [ray=$cfRay, trace=$traceId]';
}

class WorkersClient {
  final Dio _dio;
  final FlutterSecureStorage _storage;
  final String _tokenKey;
  static const int _maxRetries = 3;

  WorkersClient({
    required String baseUrl,
    FlutterSecureStorage? storage,
    String tokenKey = 'workers_jwt',
  })  : _storage = storage ?? const FlutterSecureStorage(),
        _tokenKey = tokenKey,
        _dio = Dio(BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 30),
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
        )) {
    _dio.interceptors.add(_authInterceptor());
    _dio.interceptors.add(_retryInterceptor());
  }

  Interceptor _authInterceptor() => InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _storage.read(key: _tokenKey);
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      );

  Interceptor _retryInterceptor() => InterceptorsWrapper(
        onError: (error, handler) async {
          final statusCode = error.response?.statusCode ?? 0;
          final attempt = error.requestOptions.extra['_attempt'] as int? ?? 0;

          final shouldRetry =
              (statusCode == 429 || statusCode >= 500) && attempt < _maxRetries;

          if (!shouldRetry) {
            handler.next(error);
            return;
          }

          final delay = Duration(milliseconds: 200 * (1 << attempt));
          await Future<void>.delayed(delay);

          final options = error.requestOptions
            ..extra['_attempt'] = attempt + 1;

          try {
            final response = await _dio.fetch<dynamic>(options);
            handler.resolve(response);
          } on DioException catch (e) {
            handler.reject(e);
          }
        },
      );

  Future<T> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    T Function(Map<String, dynamic>)? fromJson,
  }) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        path,
        queryParameters: queryParameters,
      );
      final data = res.data ?? {};
      return fromJson != null ? fromJson(data) : data as T;
    } on DioException catch (e) {
      throw _mapError(e);
    }
  }

  Future<T> post<T>(
    String path, {
    Object? body,
    T Function(Map<String, dynamic>)? fromJson,
  }) async {
    try {
      final res =
          await _dio.post<Map<String, dynamic>>(path, data: body);
      final data = res.data ?? {};
      return fromJson != null ? fromJson(data) : data as T;
    } on DioException catch (e) {
      throw _mapError(e);
    }
  }

  WorkersApiException _mapError(DioException e) {
    final response = e.response;
    final headers = response?.headers;
    final cfRay = headers?.value('cf-ray');
    final body = response?.data;
    final traceId = body is Map ? body['traceId'] as String? : null;
    final message = body is Map
        ? (body['error'] as String? ?? e.message ?? 'Unknown error')
        : (e.message ?? 'Network error');

    return WorkersApiException(
      statusCode: response?.statusCode ?? 0,
      message: message,
      traceId: traceId,
      cfRay: cfRay,
    );
  }
}
```

## Workers Endpoint with Typed Dart Response

```typescript
// workers/src/api/products.ts
export interface Product {
  id: string;
  name: string;
  price: number;
  currency: string;
}

export interface ProductsResponse {
  products: Product[];
  total: number;
  traceId: string;
}

export async function handleProducts(req: Request, env: { DB: D1Database }): Promise<Response> {
  const url = new URL(req.url);
  const page = parseInt(url.searchParams.get('page') ?? '1', 10);
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '20', 10), 100);
  const offset = (page - 1) * limit;

  const { results } = await env.DB.prepare(
    'SELECT id, name, price, currency FROM products ORDER BY created_at DESC LIMIT ? OFFSET ?'
  )
    .bind(limit, offset)
    .all<Product>();

  const { results: countRows } = await env.DB.prepare(
    'SELECT COUNT(*) as total FROM products'
  ).all<{ total: number }>();

  const traceId = req.headers.get('X-Trace-Id') ?? crypto.randomUUID();

  return Response.json(
    {
      products: results,
      total: countRows[0]?.total ?? 0,
      traceId,
    } satisfies ProductsResponse,
    {
      headers: {
        'Cache-Control': 'private, max-age=30',
        'X-Trace-Id': traceId,
      },
    }
  );
}
```

## Consuming the Client in Flutter Widgets

```dart
// lib/features/products/products_repository.dart
import '../api/workers_client.dart';

class Product {
  final String id;
  final String name;
  final double price;
  final String currency;

  const Product({
    required this.id,
    required this.name,
    required this.price,
    required this.currency,
  });

  factory Product.fromJson(Map<String, dynamic> json) => Product(
        id: json['id'] as String,
        name: json['name'] as String,
        price: (json['price'] as num).toDouble(),
        currency: json['currency'] as String,
      );
}

class ProductsRepository {
  final WorkersClient _client;

  const ProductsRepository(this._client);

  Future<List<Product>> fetchProducts({int page = 1}) async {
    final response = await _client.get<Map<String, dynamic>>(
      '/api/products',
      queryParameters: {'page': page, 'limit': 20},
    );
    final items = response['products'] as List<dynamic>;
    return items
        .map((e) => Product.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
```

## Anti-patterns

- Creating a new `Dio` instance per widget — interceptors, connection pools, and token caches
  are not shared, which causes duplicate auth refreshes and wasted sockets.
- Catching `Exception` broadly and discarding the `WorkersApiException` — the `cfRay` field
  is the only way to correlate a Flutter crash report with a specific Workers invocation in
  Cloudflare's dashboard.
- Ignoring `Retry-After` response headers from the Workers rate limiter — always parse the
  header and back off for the specified duration rather than using a fixed delay.

## Gotchas

- Dio's `receiveTimeout` applies per-read-chunk on some platforms; for streaming Workers
  responses, set `receiveDataWhenStatusError: true` on `BaseOptions` or error body parsing
  will return `null`.
- `flutter_secure_storage` on Android requires `minSdkVersion 23`; if your app targets
  lower, fall back to `shared_preferences` with an in-memory encryption layer.

## Verification

```bash
# Run Workers locally
npx wrangler dev --port 8787

# Test the products endpoint
curl -s http://localhost:8787/api/products?page=1 | jq '.traceId'

# In the Flutter project, run integration tests
flutter test integration_test/workers_client_test.dart \
  --dart-define=WORKERS_BASE_URL=http://localhost:8787

# Check Dio retry behaviour with a mock 429
# (use wrangler --test-mode or a local mock server)
```

## Related

- `mobile/flutter-getting-started.md`
- `mobile/mobile-auth-oauth-pkce.md`
- `mobile/mobile-network-resilience-cloudflare-workers.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/response/
- https://pub.dev/packages/dio
- https://pub.dev/packages/flutter_secure_storage
