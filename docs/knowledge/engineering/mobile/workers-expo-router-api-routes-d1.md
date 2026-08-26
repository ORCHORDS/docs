# Expo Router API Routes Backed by Cloudflare Workers D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want a single TypeScript codebase where your Expo app and its backend API share types, with API routes deployed to Cloudflare Workers and a D1 SQLite database for persistence. The standard Expo Router `app/api/` file-system routing conflicts with Workers' module syntax, so you need a clear bridge pattern.

## Context

- Expo SDK 52 + Expo Router v4 (file-based API routes via `app/api/`)
- Cloudflare Workers (module format) + D1 binding
- Shared `packages/types` workspace for request/response shapes
- Local dev: Wrangler 3 dev server proxied through Expo Metro

---

## Shared TypeScript Types

Create a workspace package so both the Expo client and Workers handler import identical types.

```typescript
// packages/types/src/todo.ts
export interface Todo {
  id: number;
  text: string;
  done: boolean;
  created_at: string;
}

export interface CreateTodoBody {
  text: string;
}

export interface ApiResponse<T> {
  data: T | null;
  error: string | null;
}
```

```json
// packages/types/package.json
{
  "name": "@myapp/types",
  "version": "1.0.0",
  "main": "src/index.ts",
  "exports": { ".": "./src/index.ts" }
}
```

---

## Cloudflare Workers Handler with D1

```typescript
// workers/src/index.ts
import type { Todo, CreateTodoBody, ApiResponse } from '@myapp/types';

export interface Env {
  DB: D1Database;
}

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

function json<T>(data: ApiResponse<T>, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // GET /todos
    if (url.pathname === '/todos' && request.method === 'GET') {
      const { results } = await env.DB.prepare(
        'SELECT * FROM todos ORDER BY created_at DESC LIMIT 100'
      ).all<Todo>();
      return json<Todo[]>({ data: results, error: null });
    }

    // POST /todos
    if (url.pathname === '/todos' && request.method === 'POST') {
      const body = await request.json<CreateTodoBody>();
      if (!body.text?.trim()) {
        return json({ data: null, error: 'text is required' }, 400);
      }
      const result = await env.DB.prepare(
        'INSERT INTO todos (text, done, created_at) VALUES (?, 0, datetime()) RETURNING *'
      )
        .bind(body.text.trim())
        .first<Todo>();
      return json<Todo>({ data: result ?? null, error: null }, 201);
    }

    // PATCH /todos/:id
    const patchMatch = url.pathname.match(/^\/todos\/(\d+)$/);
    if (patchMatch && request.method === 'PATCH') {
      const id = parseInt(patchMatch[1], 10);
      const body = await request.json<Partial<Todo>>();
      const updated = await env.DB.prepare(
        'UPDATE todos SET done = ? WHERE id = ? RETURNING *'
      )
        .bind(body.done ? 1 : 0, id)
        .first<Todo>();
      if (!updated) return json({ data: null, error: 'not found' }, 404);
      return json<Todo>({ data: updated, error: null });
    }

    return json({ data: null, error: 'not found' }, 404);
  },
};
```

---

## D1 Schema & Migrations

```sql
-- workers/migrations/0001_create_todos.sql
CREATE TABLE IF NOT EXISTS todos (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  text       TEXT    NOT NULL,
  done       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_todos_created_at ON todos(created_at DESC);
```

```jsonc
// workers/wrangler.toml
name = "myapp-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding      = "DB"
database_name = "myapp-prod"
database_id  = "<your-d1-id>"
```

---

## Expo Client: fetch() from React Native

```typescript
// app/(tabs)/todos.tsx
import { useEffect, useState } from 'react';
import { FlatList, TextInput, TouchableOpacity, Text, View, StyleSheet } from 'react-native';
import type { Todo, CreateTodoBody, ApiResponse } from '@myapp/types';

const API_BASE =
  process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8787';

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<ApiResponse<T>> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    return { data: null, error: text };
  }
  return res.json<ApiResponse<T>>();
}

export default function TodosScreen() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [text, setText] = useState('');

  useEffect(() => {
    apiFetch<Todo[]>('/todos').then((r) => {
      if (r.data) setTodos(r.data);
    });
  }, []);

  async function addTodo() {
    const body: CreateTodoBody = { text };
    const r = await apiFetch<Todo>('/todos', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    if (r.data) {
      setTodos((prev) => [r.data!, ...prev]);
      setText('');
    }
  }

  async function toggleTodo(todo: Todo) {
    const r = await apiFetch<Todo>(`/todos/${todo.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ done: !todo.done }),
    });
    if (r.data) {
      setTodos((prev) => prev.map((t) => (t.id === r.data!.id ? r.data! : t)));
    }
  }

  return (
    <View style={s.container}>
      <View style={s.row}>
        <TextInput style={s.input} value={text} onChangeText={setText} placeholder="New todo" />
        <TouchableOpacity style={s.btn} onPress={addTodo}>
          <Text style={s.btnText}>Add</Text>
        </TouchableOpacity>
      </View>
      <FlatList
        data={todos}
        keyExtractor={(t) => String(t.id)}
        renderItem={({ item }) => (
          <TouchableOpacity onPress={() => toggleTodo(item)}>
            <Text style={[s.item, item.done && s.done]}>{item.text}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  row: { flexDirection: 'row', marginBottom: 12, gap: 8 },
  input: { flex: 1, borderWidth: 1, borderColor: '#ccc', borderRadius: 6, padding: 8 },
  btn: { backgroundColor: '#0066cc', padding: 8, borderRadius: 6, justifyContent: 'center' },
  btnText: { color: '#fff', fontWeight: '600' },
  item: { paddingVertical: 10, fontSize: 16, borderBottomWidth: 1, borderColor: '#eee' },
  done: { textDecorationLine: 'line-through', color: '#999' },
});
```

---

## Local Dev with Wrangler

```bash
# Terminal 1 — start Workers dev server
cd workers
npx wrangler dev --local --persist

# Terminal 2 — start Expo
cd app
EXPO_PUBLIC_API_URL=http://localhost:8787 npx expo start
```

Set `EXPO_PUBLIC_API_URL` in `.env.local` for team consistency:

```bash
# app/.env.local
EXPO_PUBLIC_API_URL=http://localhost:8787
```

---

## Anti-patterns

- Do NOT use Expo Router `app/api/` server actions as a proxy to Workers — it adds latency and duplicates auth logic.
- Do NOT hardcode `localhost:8787` without an env var; emulators use `10.0.2.2` for Android.
- Do NOT skip CORS preflight handling; React Native's `fetch` sends real cross-origin requests.
- Do NOT use `SELECT *` in production without explicit column lists — schema changes break Codable decoders.

## Gotchas

- `wrangler dev --local` stores D1 state in `.wrangler/state/` — commit `.wrangler/` to `.gitignore`.
- Android emulator cannot reach `localhost`; use `http://10.0.2.2:8787` or a tunnel (cloudflared).
- D1 `RETURNING *` requires SQLite 3.35+ — Cloudflare's runtime supports it; local Wrangler does too from v3.28.
- `process.env.EXPO_PUBLIC_*` is inlined at build time; restart Metro after changing `.env.local`.

---

## Verification

```bash
# Create a todo via curl
curl -s -X POST http://localhost:8787/todos \
  -H 'Content-Type: application/json' \
  -d '{"text":"test item"}' | jq .

# List todos
curl -s http://localhost:8787/todos | jq '.data | length'

# Run D1 migration against local
npx wrangler d1 migrations apply myapp-prod --local

# Run D1 migration against remote
npx wrangler d1 migrations apply myapp-prod --remote
```

---

## Related

- `documentation/docs/policies/mobile/workers-flutter-riverpod-api-client.md`
- `documentation/docs/policies/mobile/workers-ios-swift-async-d1-api.md`
- `documentation/docs/policies/mobile/workers-mobile-graphql-yoga-d1.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/workers/configuration/cors/
- https://docs.expo.dev/router/reference/api-routes/
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
