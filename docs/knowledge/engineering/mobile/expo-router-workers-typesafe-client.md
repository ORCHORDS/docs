# Expo Router Workers API Type-Safe Client

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Teams using Expo Router (file-based routing) need a type-safe way to call Cloudflare Workers APIs from their mobile app without duplicating type definitions between the Workers backend and the React Native client.

## Context
Expo Router's `+api` routes provide server-side endpoints but only work for Expo web or EAS hosting—not for Workers. When your API layer lives in Cloudflare Workers, sharing types between the Workers TypeScript project and the Expo app requires a deliberate setup: a shared types package, a generated fetch client, and CI validation that the contract stays in sync. Without this, runtime mismatches between the Worker response shape and the client expectation are discovered only after deployment.

## Shared Types Package

Create a `packages/api-types` workspace that both the Workers and the Expo app import:

```
apps/
  mobile/       # Expo app
  worker/       # Cloudflare Workers project
packages/
  api-types/    # shared TypeScript types
    src/
      index.ts
    package.json
    tsconfig.json
```

```typescript
// packages/api-types/src/index.ts
export interface UserProfile {
  id: string;
  displayName: string;
  avatarUrl: string | null;
  createdAt: string; // ISO-8601
}

export interface ListUsersResponse {
  users: UserProfile[];
  cursor: string | null;
  total: number;
}

export interface ApiError {
  code: string;
  message: string;
  requestId: string;
}

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: ApiError };
```

```json
// packages/api-types/package.json
{
  "name": "@myapp/api-types",
  "version": "0.0.1",
  "main": "src/index.ts",
  "types": "src/index.ts"
}
```

## Workers Implementation

The Worker imports from the shared types package and returns responses that conform to them:

```typescript
// apps/worker/src/index.ts
import { UserProfile, ListUsersResponse, ApiError } from "@myapp/api-types";

export interface Env {
  DB: D1Database;
}

function jsonResponse<T>(data: T, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

function errorResponse(code: string, message: string, status: number): Response {
  const err: ApiError = {
    code,
    message,
    requestId: crypto.randomUUID(),
  };
  return jsonResponse(err, status);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/users" && request.method === "GET") {
      const cursor = url.searchParams.get("cursor");
      const limit = parseInt(url.searchParams.get("limit") ?? "20", 10);

      let query = "SELECT id, display_name, avatar_url, created_at FROM users";
      const params: unknown[] = [];

      if (cursor) {
        query += " WHERE created_at < ?1 ORDER BY created_at DESC LIMIT ?2";
        params.push(cursor, limit + 1);
      } else {
        query += " ORDER BY created_at DESC LIMIT ?1";
        params.push(limit + 1);
      }

      const result = await env.DB.prepare(query).bind(...params).all<{
        id: string;
        display_name: string;
        avatar_url: string | null;
        created_at: string;
      }>();

      const rows = result.results ?? [];
      const hasMore = rows.length > limit;
      const page = hasMore ? rows.slice(0, limit) : rows;

      const body: ListUsersResponse = {
        users: page.map((r): UserProfile => ({
          id: r.id,
          displayName: r.display_name,
          avatarUrl: r.avatar_url,
          createdAt: r.created_at,
        })),
        cursor: hasMore ? page[page.length - 1].createdAt : null,
        total: rows.length,
      };

      return jsonResponse(body);
    }

    if (url.pathname.startsWith("/users/") && request.method === "GET") {
      const userId = url.pathname.replace("/users/", "");
      const row = await env.DB.prepare(
        "SELECT id, display_name, avatar_url, created_at FROM users WHERE id = ?1"
      )
        .bind(userId)
        .first<{ id: string; display_name: string; avatar_url: string | null; created_at: string }>();

      if (!row) return errorResponse("NOT_FOUND", "User not found", 404);

      const user: UserProfile = {
        id: row.id,
        displayName: row.display_name,
        avatarUrl: row.avatar_url,
        createdAt: row.created_at,
      };
      return jsonResponse(user);
    }

    return errorResponse("NOT_FOUND", "Route not found", 404);
  },
};
```

## Expo App Type-Safe Client

```typescript
// apps/mobile/src/lib/workersClient.ts
import {
  ApiResult,
  ApiError,
  ListUsersResponse,
  UserProfile,
} from "@myapp/api-types";

const WORKERS_BASE_URL = process.env.EXPO_PUBLIC_WORKERS_URL!;

async function call<T>(
  path: string,
  init?: RequestInit
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${WORKERS_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (networkErr) {
    return {
      ok: false,
      error: {
        code: "NETWORK_ERROR",
        message: (networkErr as Error).message,
        requestId: "",
      },
    };
  }

  const json = await response.json();

  if (!response.ok) {
    return { ok: false, error: json as ApiError };
  }
  return { ok: true, data: json as T };
}

export const workersClient = {
  listUsers(params?: { cursor?: string; limit?: number }) {
    const qs = new URLSearchParams();
    if (params?.cursor) qs.set("cursor", params.cursor);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs}` : "";
    return call<ListUsersResponse>(`/users${suffix}`);
  },

  getUser(userId: string) {
    return call<UserProfile>(`/users/${encodeURIComponent(userId)}`);
  },
};
```

```typescript
// apps/mobile/src/hooks/useUsers.ts
import { useState, useEffect, useCallback } from "react";
import { workersClient } from "../lib/workersClient";
import type { UserProfile } from "@myapp/api-types";

export function useUsers() {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextCursor?: string) => {
    setLoading(true);
    setError(null);
    const result = await workersClient.listUsers({
      cursor: nextCursor,
      limit: 20,
    });
    setLoading(false);

    if (!result.ok) {
      setError(result.error.message);
      return;
    }

    setUsers((prev) =>
      nextCursor ? [...prev, ...result.data.users] : result.data.users
    );
    setCursor(result.data.cursor);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { users, cursor, loading, error, loadMore: () => load(cursor ?? undefined) };
}
```

## Expo Router Screen Integration

```typescript
// apps/mobile/app/(tabs)/users.tsx
import React from "react";
import {
  FlatList,
  Text,
  View,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
} from "react-native";
import { useUsers } from "../../src/hooks/useUsers";
import type { UserProfile } from "@myapp/api-types";

function UserRow({ user }: { user: UserProfile }) {
  return (
    <View style={styles.row}>
      <Text style={styles.name}>{user.displayName}</Text>
      <Text style={styles.date}>
        {new Date(user.createdAt).toLocaleDateString()}
      </Text>
    </View>
  );
}

export default function UsersScreen() {
  const { users, loading, error, loadMore, cursor } = useUsers();

  if (loading && users.length === 0) {
    return <ActivityIndicator style={styles.center} />;
  }

  if (error) {
    return <Text style={styles.error}>Error: {error}</Text>;
  }

  return (
    <FlatList
      data={users}
      keyExtractor={(u) => u.id}
      renderItem={({ item }) => <UserRow user={item} />}
      onEndReached={cursor ? loadMore : undefined}
      onEndReachedThreshold={0.4}
      ListFooterComponent={
        loading ? <ActivityIndicator style={styles.center} /> : null
      }
    />
  );
}

const styles = StyleSheet.create({
  row: { padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#ccc" },
  name: { fontSize: 16, fontWeight: "600" },
  date: { fontSize: 12, color: "#888", marginTop: 2 },
  center: { margin: 24 },
  error: { margin: 24, color: "red" },
});
```

## Anti-patterns
- Importing types directly from the Workers project (creates circular monorepo dependencies and breaks mobile-only builds)
- Using `any` casts when consuming Worker responses—defeats the purpose of shared types
- Putting `EXPO_PUBLIC_WORKERS_URL` directly in source code instead of `.env.local`
- Duplicating the type definitions in both projects and hoping they stay in sync manually
- Skipping the `ApiResult` discriminated union and relying only on `try/catch` for error handling

## Gotchas
- `process.env.EXPO_PUBLIC_*` variables are inlined at Metro bundle time; changes require a new build or a dev server restart, not a Workers redeploy
- The shared package must be listed in the `workspaces` field of the root `package.json` and in the Expo project's `metro.config.js` `watchFolders` for Metro to resolve it correctly
- D1 `cursor`-based pagination uses `created_at` as the cursor value here; ensure the column is indexed and values are unique enough (add `id` as a secondary sort key for true stability)
- `JSON.stringify` on D1 `INTEGER` columns returns a JavaScript `number`; ensure your shared type reflects this to avoid silent coercions
- Expo Go does not support custom native modules—test with a development build when adding any native dependency alongside the Workers client

## Verification
1. Run `tsc --noEmit` in both `apps/worker` and `apps/mobile`—both should pass with zero errors.
2. Add a CI step: `cd packages/api-types && tsc --noEmit` to validate the shared package independently.
3. Use `wrangler dev --local` and point `EXPO_PUBLIC_WORKERS_URL=http://localhost:8787` in `.env.local`.
4. Call `workersClient.listUsers()` from the Expo app and assert the response shape in a Jest test using `zod` or `expect` matchers derived from the shared types.
5. Intentionally break a field name in the Worker response and confirm TypeScript compilation fails before the change ships.

## Related
- `expo-r2-ota-workers.md`
- `expo-eas-build-cloudflare-workers-secrets.md`
- `react-native-workers-hmac-signed-requests.md`
- `mobile-api-design-patterns.md`

## Sources
- https://docs.expo.dev/router/introduction/
- https://developers.cloudflare.com/d1/
- https://www.typescriptlang.org/docs/handbook/2/narrowing.html#discriminated-unions
