# Flutter GraphQL Client Consuming a Hono Workers GraphQL Endpoint

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Flutter app needs a typed GraphQL client that talks to a Hono-on-Workers GraphQL server, with auth header injection, error handling, and a shared schema generated from the Worker's type definitions.

## Context
Hono's `@hono/graphql-server` middleware runs a full GraphQL schema on Cloudflare Workers using `graphql-js`. Flutter's `graphql_flutter` package provides a `GraphQLClient` with in-memory or Hive cache, auth link injection, and built-in error states. Together they give a full typed client-server GraphQL stack with zero server infrastructure beyond a Worker.

## Hono Workers GraphQL Server

```typescript
// worker/src/index.ts
import { Hono } from 'hono';
import { graphqlServer } from '@hono/graphql-server';
import { buildSchema } from 'graphql';
import { Env } from './types';

const schema = buildSchema(`
  type Product {
    id: ID!
    name: String!
    price: Float!
    stock: Int!
  }

  type Order {
    id: ID!
    productId: ID!
    quantity: Int!
    createdAt: String!
  }

  type Query {
    product(id: ID!): Product
    products(limit: Int, cursor: String): [Product!]!
    myOrders: [Order!]!
  }

  type Mutation {
    createOrder(productId: ID!, quantity: Int!): Order!
  }
`);

const app = new Hono<{ Bindings: Env }>();

// Auth middleware: attach userId to context
app.use('/graphql', async (c, next) => {
  const auth = c.req.header('Authorization') ?? '';
  const token = auth.replace('Bearer ', '');
  if (token) {
    const payload = await verifyJwt(token, c.env.JWT_SECRET);
    if (payload) c.set('userId', payload.sub);
  }
  return next();
});

app.use(
  '/graphql',
  graphqlServer({
    schema,
    rootResolver: (c) => ({
      product: async ({ id }: { id: string }) => {
        const env = (c as { env: Env }).env;
        const row = await env.DB.prepare(
          'SELECT id, name, price, stock FROM products WHERE id = ?'
        )
          .bind(id)
          .first<{ id: string; name: string; price: number; stock: number }>();
        return row ?? null;
      },

      products: async ({ limit = 20, cursor }: { limit?: number; cursor?: string }) => {
        const env = (c as { env: Env }).env;
        const { results } = await env.DB.prepare(
          `SELECT id, name, price, stock FROM products
           WHERE id > ? ORDER BY id ASC LIMIT ?`
        )
          .bind(cursor ?? '', limit)
          .all();
        return results;
      },

      myOrders: async () => {
        const env = (c as { env: Env }).env;
        const userId: string = (c as unknown as { get: (k: string) => string }).get('userId');
        if (!userId) throw new Error('Unauthenticated');
        const { results } = await env.DB.prepare(
          `SELECT id, product_id AS productId, quantity, created_at AS createdAt
           FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 50`
        )
          .bind(userId)
          .all();
        return results;
      },

      createOrder: async ({ productId, quantity }: { productId: string; quantity: number }) => {
        const env = (c as { env: Env }).env;
        const userId: string = (c as unknown as { get: (k: string) => string }).get('userId');
        if (!userId) throw new Error('Unauthenticated');
        const id = crypto.randomUUID();
        await env.DB.prepare(
          `INSERT INTO orders (id, user_id, product_id, quantity, created_at)
           VALUES (?, ?, ?, ?, ?)`
        )
          .bind(id, userId, productId, quantity, new Date().toISOString())
          .run();
        return { id, productId, quantity, createdAt: new Date().toISOString() };
      },
    }),
  })
);

export default app;

async function verifyJwt(token: string, secret: string): Promise<{ sub: string } | null> {
  try {
    const key = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']
    );
    const [h, p, s] = token.split('.');
    const sig = Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
    const valid = await crypto.subtle.verify('HMAC', key, sig, new TextEncoder().encode(`${h}.${p}`));
    return valid ? JSON.parse(atob(p)) as { sub: string } : null;
  } catch { return null; }
}
```

## Flutter GraphQL Client Setup

```yaml
# pubspec.yaml
dependencies:
  graphql_flutter: ^5.2.0
  flutter_secure_storage: ^9.2.2
```

```dart
// lib/graphql/client.dart
import 'package:graphql_flutter/graphql_flutter.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _workersGraphqlUrl = 'https://api.example.com/graphql';

Future<GraphQLClient> buildGraphQLClient() async {
  await initHiveForFlutter(); // optional Hive persistent cache

  final storage = const FlutterSecureStorage();

  final authLink = AuthLink(
    getToken: () async {
      final token = await storage.read(key: 'auth_token');
      return token != null ? 'Bearer $token' : null;
    },
  );

  final httpLink = HttpLink(_workersGraphqlUrl);

  final errorLink = ErrorLink(
    onGraphQLError: (request, forward, response) {
      final errors = response.errors;
      if (errors != null && errors.any((e) => e.message == 'Unauthenticated')) {
        // Navigate to login — handled by your auth bloc
        authEventBus.fire(AuthExpiredEvent());
      }
      return null;
    },
  );

  final link = authLink.concat(errorLink).concat(httpLink);

  return GraphQLClient(
    link: link,
    cache: GraphQLCache(store: HiveStore()),
    defaultPolicies: DefaultPolicies(
      query: Policies(fetch: FetchPolicy.cacheAndNetwork),
      mutate: Policies(fetch: FetchPolicy.networkOnly),
    ),
  );
}
```

## Querying Products in Flutter

```dart
// lib/graphql/queries.dart
import 'package:graphql_flutter/graphql_flutter.dart';

const productsQuery = r'''
  query Products($limit: Int, $cursor: String) {
    products(limit: $limit, cursor: $cursor) {
      id
      name
      price
      stock
    }
  }
''';

const createOrderMutation = r'''
  mutation CreateOrder($productId: ID!, $quantity: Int!) {
    createOrder(productId: $productId, quantity: $quantity) {
      id
      productId
      quantity
      createdAt
    }
  }
''';
```

```dart
// lib/screens/products_screen.dart
import 'package:flutter/material.dart';
import 'package:graphql_flutter/graphql_flutter.dart';
import '../graphql/queries.dart';

class ProductsScreen extends StatelessWidget {
  const ProductsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Query(
      options: QueryOptions(
        document: gql(productsQuery),
        variables: const {'limit': 20},
      ),
      builder: (result, {fetchMore, refetch}) {
        if (result.isLoading && result.data == null) {
          return const Center(child: CircularProgressIndicator());
        }
        if (result.hasException) {
          return Center(child: Text(result.exception.toString()));
        }

        final products = (result.data?['products'] as List<dynamic>? ?? [])
            .cast<Map<String, dynamic>>();

        return ListView.builder(
          itemCount: products.length,
          itemBuilder: (ctx, i) {
            final p = products[i];
            return ListTile(
              title: Text(p['name'] as String),
              subtitle: Text('\$${p['price']} · ${p['stock']} in stock'),
              trailing: _OrderButton(productId: p['id'] as String),
            );
          },
        );
      },
    );
  }
}

class _OrderButton extends StatelessWidget {
  final String productId;
  const _OrderButton({required this.productId});

  @override
  Widget build(BuildContext context) {
    return Mutation(
      options: MutationOptions(document: gql(createOrderMutation)),
      builder: (runMutation, result) {
        return ElevatedButton(
          onPressed: result?.isLoading == true
              ? null
              : () => runMutation({'productId': productId, 'quantity': 1}),
          child: result?.isLoading == true
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Order'),
        );
      },
    );
  }
}
```

## Anti-patterns
- Parsing `result.data` without null-checking — Workers may return partial data alongside errors
- Using `FetchPolicy.networkOnly` for queries — defeats the cache and increases latency on slow connections
- Embedding the JWT directly in the GraphQL query as a variable — use the `AuthLink` header instead
- Throwing untyped errors from Workers resolvers — GraphQL errors surface as `GraphQLError` objects, not HTTP 4xx
- Keeping a single `GraphQLClient` instance across sign-out — the Hive cache and auth token must be purged on logout

## Gotchas
- `@hono/graphql-server` does not support subscriptions over WebSocket; use Durable Objects for that
- Workers script size limit is 10 MB compressed; `graphql-js` adds ~900 KB — tree-shake unused utilities
- Flutter's `graphql_flutter` uses `gql()` for query parsing at runtime; prefer `DocumentNode` constants to avoid re-parsing on every rebuild
- The Hive cache on Flutter stores data on-device in plain text; do not cache sensitive fields like payment details
- `AuthLink` is called on every request including cache reads — keep `getToken` fast (SecureStorage reads are synchronous on most platforms)

## Verification

```bash
# Test the Workers GraphQL endpoint with curl
curl -X POST https://api.example.com/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"query":"{ products(limit:3) { id name price } }"}'

# Introspect schema
curl -X POST https://api.example.com/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ __schema { types { name } } }"}'

# Deploy
wrangler deploy
```

## Related
- `flutter-workers-graphql-cache-hive.md` — advanced Hive cache invalidation patterns
- `flutter-workers-dart-client.md` — REST client alternative with Dio
- `flutter-riverpod-workers-state-management.dart` — Riverpod providers wrapping GraphQL queries
- `react-native-workers-graphql-codegen.md` — code generation for typed React Native GraphQL hooks
- `mobile-api-design-patterns.md` — REST vs GraphQL trade-offs for mobile

## Sources
- https://github.com/honojs/middleware/tree/main/packages/graphql-server
- https://pub.dev/packages/graphql_flutter
- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/api/worker-api/
- https://graphql.org/learn/
