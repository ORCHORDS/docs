# Flutter App Consuming a Typed REST API Backed by Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Flutter app needs a reliable REST API with typed request/response shapes, JWT authentication, and graceful error handling for poor mobile connectivity. A Cloudflare Worker with Zod validation in front of a D1 database provides a strongly-typed, globally-distributed backend without managing servers.

---

## Context
Cloudflare Workers serve as the HTTP layer: they parse and validate request bodies with Zod, query D1 via prepared statements, and return typed JSON. The Dart `http` package sends requests with an `Authorization: Bearer <token>` header. Flutter's `FutureBuilder` propagates typed error objects for 4xx/5xx responses, and `shared_preferences` caches the last successful response so the UI renders stale data while offline rather than showing a blank screen. Zod runs in the Worker via `zod` from npm — Workers support npm packages natively.

---

## Setup / Config

```toml
# wrangler.toml
name = "flutter-api"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "orchords-prod"
database_id = "<your-d1-database-id>"

[vars]
JWT_AUDIENCE = "https://api.example.com"
```

```bash
# Install dependencies (Workers project)
npm install zod
npm install -D wrangler typescript

# Create D1 schema
npx wrangler d1 execute orchords-prod --command "
  CREATE TABLE IF NOT EXISTS chords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    frets TEXT NOT NULL,
    tuning TEXT NOT NULL DEFAULT 'EADGBE',
    created_at INTEGER NOT NULL
  );
"
```

---

## Implementation — Workers REST API

```typescript
// src/index.ts
import { z } from 'zod';

export interface Env {
  DB: D1Database;
  JWT_AUDIENCE: string;
}

// ── Schemas ────────────────────────────────────────────────────────────
const ChordSchema = z.object({
  name: z.string().min(1).max(32),
  frets: z.string().regex(/^[x0-9-]{6,24}$/),
  tuning: z.string().length(6).optional().default('EADGBE'),
});

type ChordInput = z.infer<typeof ChordSchema>;

// ── Helpers ────────────────────────────────────────────────────────────
function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function verifyBearer(request: Request, audience: string): Promise<boolean> {
  const auth = request.headers.get('Authorization') ?? '';
  if (!auth.startsWith('Bearer ')) return false;
  // In production verify JWT signature against your JWKS endpoint;
  // simplified here to illustrate the header pattern.
  const token = auth.slice(7);
  return token.length > 0; // replace with real JWT verification
}

// ── Route handlers ─────────────────────────────────────────────────────
async function listChords(env: Env, url: URL): Promise<Response> {
  const limit = Math.min(Number(url.searchParams.get('limit') ?? '20'), 100);
  const offset = Number(url.searchParams.get('offset') ?? '0');

  const { results } = await env.DB.prepare(
    'SELECT id, name, frets, tuning, created_at FROM chords ORDER BY id DESC LIMIT ? OFFSET ?'
  )
    .bind(limit, offset)
    .all();

  return json({ data: results, limit, offset });
}

async function createChord(env: Env, request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'Invalid JSON body' }, 400);
  }

  const parsed = ChordSchema.safeParse(body);
  if (!parsed.success) {
    return json({ error: 'Validation failed', details: parsed.error.issues }, 422);
  }

  const { name, frets, tuning } = parsed.data as ChordInput;
  const { meta } = await env.DB.prepare(
    'INSERT INTO chords (name, frets, tuning, created_at) VALUES (?, ?, ?, ?)'
  )
    .bind(name, frets, tuning, Date.now())
    .run();

  return json({ id: meta.last_row_id, name, frets, tuning }, 201);
}

async function getChord(env: Env, id: number): Promise<Response> {
  const row = await env.DB.prepare(
    'SELECT id, name, frets, tuning, created_at FROM chords WHERE id = ?'
  )
    .bind(id)
    .first();

  if (!row) return json({ error: 'Chord not found' }, 404);
  return json(row);
}

// ── Router ─────────────────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    const authed = await verifyBearer(request, env.JWT_AUDIENCE);
    if (!authed) return json({ error: 'Unauthorized' }, 401);

    if (url.pathname === '/chords' && request.method === 'GET') {
      return listChords(env, url);
    }
    if (url.pathname === '/chords' && request.method === 'POST') {
      return createChord(env, request);
    }
    const idMatch = url.pathname.match(/^\/chords\/(\d+)$/);
    if (idMatch && request.method === 'GET') {
      return getChord(env, Number(idMatch[1]));
    }

    return json({ error: 'Not found' }, 404);
  },
};
```

---

## Integration — Flutter Client

```dart
// lib/api/chord_api.dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

const _base = 'https://flutter-api.<subdomain>.workers.dev';
const _cacheKey = 'cached_chords';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  const ApiException(this.statusCode, this.message);
  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ChordApi {
  final String token;
  ChordApi(this.token);

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };

  Future<List<Map<String, dynamic>>> fetchChords({int limit = 20, int offset = 0}) async {
    final prefs = await SharedPreferences.getInstance();
    try {
      final uri = Uri.parse('$_base/chords?limit=$limit&offset=$offset');
      final response = await http.get(uri, headers: _headers)
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 401) throw const ApiException(401, 'Unauthorized');
      if (response.statusCode >= 400) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        throw ApiException(response.statusCode, body['error'] as String? ?? 'Unknown error');
      }

      final data = (jsonDecode(response.body) as Map<String, dynamic>)['data'] as List;
      final chords = data.cast<Map<String, dynamic>>();

      // Update cache on success
      await prefs.setString(_cacheKey, jsonEncode(chords));
      return chords;
    } catch (e) {
      // Return stale cache on network failure
      final cached = prefs.getString(_cacheKey);
      if (cached != null) {
        return (jsonDecode(cached) as List).cast<Map<String, dynamic>>();
      }
      rethrow;
    }
  }

  Future<Map<String, dynamic>> createChord({
    required String name,
    required String frets,
    String tuning = 'EADGBE',
  }) async {
    final uri = Uri.parse('$_base/chords');
    final response = await http
        .post(uri, headers: _headers, body: jsonEncode({'name': name, 'frets': frets, 'tuning': tuning}))
        .timeout(const Duration(seconds: 10));

    if (response.statusCode == 422) {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      throw ApiException(422, body['error'] as String? ?? 'Validation failed');
    }
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, 'Unexpected error');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }
}
```

```dart
// lib/screens/chord_list_screen.dart (FutureBuilder snippet)
FutureBuilder<List<Map<String, dynamic>>>(
  future: ChordApi(token).fetchChords(),
  builder: (context, snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) {
      return const Center(child: CircularProgressIndicator());
    }
    if (snapshot.hasError) {
      final err = snapshot.error;
      final message = err is ApiException ? err.message : 'Network error';
      return Center(child: Text('Error: $message'));
    }
    final chords = snapshot.data!;
    return ListView.builder(
      itemCount: chords.length,
      itemBuilder: (_, i) => ListTile(title: Text(chords[i]['name'] as String)),
    );
  },
)
```

---

## Anti-patterns
- **Returning raw D1 errors to the client** — always map D1 exceptions to generic 500 messages; never leak SQL details.
- **Parsing response body before checking status code** — a 401/500 may return HTML; always check `statusCode` first.
- **Storing the JWT in `shared_preferences` without encryption** — use `flutter_secure_storage` for tokens on mobile.
- **Awaiting D1 writes without error handling** — D1 `.run()` rejects the promise on constraint violations; wrap in try/catch.

---

## Gotchas
- D1's `meta.last_row_id` returns `0` if the INSERT touches a table with no AUTOINCREMENT column; always define `INTEGER PRIMARY KEY AUTOINCREMENT`.
- `http` package `timeout` does not cancel the underlying socket on iOS; pair with a `CancelToken` pattern for robust cancellation.
- `shared_preferences` is asynchronous; do not read it synchronously in `build()` — always inside a `FutureBuilder` or `initState`.
- Workers `compatibility_date` controls which npm APIs are available; pin it and test upgrades explicitly.

---

## Verification

```bash
# Deploy Worker
npx wrangler deploy

# Create a chord
curl -X POST https://flutter-api.<subdomain>.workers.dev/chords \
  -H 'Authorization: Bearer test-token' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Am","frets":"x02210"}'
# Expected: {"id":1,"name":"Am","frets":"x02210","tuning":"EADGBE"}

# List chords
curl -H 'Authorization: Bearer test-token' \
  https://flutter-api.<subdomain>.workers.dev/chords

# Trigger validation error
curl -X POST https://flutter-api.<subdomain>.workers.dev/chords \
  -H 'Authorization: Bearer test-token' \
  -H 'Content-Type: application/json' \
  -d '{"name":"","frets":"bad"}'
# Expected: 422 with Zod issues array
```

---

## Related
- `workers-mobile-certificate-pinning-bypass-detect.md`
- `workers-mobile-api-versioning-accept-header.md`

---

## Sources
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Zod documentation — https://zod.dev
- Flutter http package — https://pub.dev/packages/http
- shared_preferences — https://pub.dev/packages/shared_preferences
