# React Native New Architecture Workers Typed Bindings (Codegen → TypeScript)

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your React Native app has migrated to the New Architecture (Fabric renderer + TurboModules +
Codegen) and your Cloudflare Workers API has grown to dozens of endpoints. Developers are
spending significant time keeping native module specs, Workers response types, and React
component prop types in sync — three separate type systems drifting apart over time, causing
runtime type errors that Codegen and TypeScript each catch only on their own side. You want a
single source of truth so that a change to a Workers endpoint type automatically propagates to
the native Codegen spec and to the TypeScript client types in the app, without manual editing.

---

## Context

**React Native New Architecture** uses a Codegen pipeline: you write TypeScript (or Flow)
interface specs for TurboModules and Fabric components, and the C++ bridge code, Java bindings,
and Objective-C++ headers are generated at build time. The spec language is deliberately
constrained — no union types, no generics, primitive types and readonly arrays only — but it is
TypeScript at the source level.

**Cloudflare Workers** can expose a TypeScript-typed API via hand-written types or, in 2026,
via OpenAPI 3.1 schemas generated from your Worker handlers. The bridge between these two
worlds is:

1. **zod** schemas on the Workers side, used for runtime validation and as the type source.
2. **zod-to-openapi** or **zod-to-json-schema** to emit schemas.
3. A codegen script that reads the JSON schema and emits:
   - TypeScript client types for use in React Native JS/TS code.
   - Codegen-compatible TurboModule spec stubs for native modules that need to call Workers
     endpoints synchronously over JSI (rare but useful for auth tokens, config, etc.).

---

## Workers Side: Zod-Typed Routes

```typescript
// workers/src/schemas.ts
import { z } from "zod";

export const UserProfileSchema = z.object({
  id: z.string().uuid(),
  displayName: z.string().max(100),
  avatarUrl: z.string().url().nullable(),
  plan: z.enum(["free", "pro", "enterprise"]),
  createdAt: z.string().datetime(),
});

export const TrackSchema = z.object({
  id: z.string(),
  title: z.string(),
  durationMs: z.number().int().nonnegative(),
  streamUrl: z.string().url(),
  coverArtKey: z.string().nullable(),
});

export const PlaylistSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  tracks: z.array(TrackSchema),
  totalDurationMs: z.number().int(),
});

export const ApiErrorSchema = z.object({
  error: z.string(),
  code: z.string(),
  requestId: z.string().optional(),
});

// Export inferred types for use inside Workers
export type UserProfile = z.infer<typeof UserProfileSchema>;
export type Track = z.infer<typeof TrackSchema>;
export type Playlist = z.infer<typeof PlaylistSchema>;
export type ApiError = z.infer<typeof ApiErrorSchema>;
```

```typescript
// workers/src/routes/profile.ts
import { UserProfileSchema } from "../schemas";
import type { Env } from "../types";

export async function handleGetProfile(request: Request, env: Env): Promise<Response> {
  const userId = new URL(request.url).searchParams.get("userId");
  if (!userId) return Response.json({ error: "Missing userId", code: "BAD_REQUEST" }, { status: 400 });

  const raw = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(userId).first();
  if (!raw) return Response.json({ error: "Not found", code: "NOT_FOUND" }, { status: 404 });

  const parsed = UserProfileSchema.safeParse(raw);
  if (!parsed.success) {
    console.error("Schema mismatch:", parsed.error.flatten());
    return Response.json({ error: "Internal error", code: "SCHEMA_MISMATCH" }, { status: 500 });
  }

  return Response.json(parsed.data);
}
```

---

## Schema Export Script (Workers → JSON Schema)

```typescript
// scripts/export-schemas.ts  (runs in Node, not in Workers)
import { zodToJsonSchema } from "zod-to-json-schema";
import { writeFileSync, mkdirSync } from "fs";
import {
  UserProfileSchema,
  TrackSchema,
  PlaylistSchema,
  ApiErrorSchema,
} from "../workers/src/schemas";

const schemas = {
  UserProfile: UserProfileSchema,
  Track: TrackSchema,
  Playlist: PlaylistSchema,
  ApiError: ApiErrorSchema,
};

const out: Record<string, unknown> = {};
for (const [name, schema] of Object.entries(schemas)) {
  out[name] = zodToJsonSchema(schema, { name, $refStrategy: "none" });
}

mkdirSync("generated", { recursive: true });
writeFileSync("generated/api-schemas.json", JSON.stringify(out, null, 2));
console.log("Exported", Object.keys(schemas).length, "schemas to generated/api-schemas.json");
```

Add to `package.json`:
```json
{
  "scripts": {
    "codegen:schemas": "ts-node scripts/export-schemas.ts",
    "codegen:rn": "npm run codegen:schemas && ts-node scripts/generate-rn-types.ts"
  }
}
```

---

## React Native Type Generation Script

```typescript
// scripts/generate-rn-types.ts
import { readFileSync, writeFileSync } from "fs";
import { compile } from "json-schema-to-typescript";

const schemasRaw = readFileSync("generated/api-schemas.json", "utf-8");
const schemas = JSON.parse(schemasRaw) as Record<string, unknown>;

async function main() {
  const lines: string[] = [
    "// AUTO-GENERATED — do not edit manually.",
    "// Source: workers/src/schemas.ts via scripts/generate-rn-types.ts",
    "// Run: npm run codegen:rn",
    "",
  ];

  for (const [name, schema] of Object.entries(schemas)) {
    const ts = await compile(schema as object, name, {
      bannerComment: "",
      additionalProperties: false,
    });
    lines.push(ts);
  }

  const output = lines.join("\n");
  writeFileSync("src/types/api.generated.ts", output);
  console.log("Generated src/types/api.generated.ts");
}

main().catch(console.error);
```

---

## TurboModule Spec for Native Auth Token Fetching

When a native module (e.g., a background upload module) needs to call Workers to refresh a
JWT without going through the JS thread, generate a Codegen-compatible spec:

```typescript
// src/native/NativeWorkersBridge.ts  (Codegen TurboModule spec)
import type { TurboModule } from 'react-native';
import { TurboModuleRegistry } from 'react-native';

// Codegen constraint: only primitive types, string, boolean, number, Object, Array allowed.
// No union types, no generics at the spec level.
export interface Spec extends TurboModule {
  // Fetch a fresh JWT from the Workers auth endpoint — called from native background tasks.
  refreshAuthToken(refreshToken: string): Promise<string>;

  // Batch-resolve track stream URLs from Workers (avoids JS thread round-trip in media player).
  resolveStreamUrls(trackIds: ReadonlyArray<string>): Promise<ReadonlyArray<string>>;

  // Ping Workers health endpoint from native network monitor.
  pingWorkers(endpoint: string): Promise<boolean>;
}

export default TurboModuleRegistry.getEnforcing<Spec>('WorkersBridge');
```

The C++ implementation calls the Workers endpoint via `libcurl` / `NSURLSession` directly,
bypassing the JS thread entirely — important for media session handlers on Android Auto and
background URLSessions on iOS.

---

## Using Generated Types in the App

```typescript
// src/hooks/useProfile.ts
import { useState, useEffect } from 'react';
import type { UserProfile } from '../types/api.generated';  // auto-generated from Workers schema

const WORKERS_BASE = 'https://api.example.com';

export function useProfile(userId: string) {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const resp = await fetch(`${WORKERS_BASE}/profile?userId=${encodeURIComponent(userId)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        // Type is directly from Workers zod schema — no manual interface needed.
        const data: UserProfile = await resp.json();
        if (active) setProfile(data);
      } catch (e) {
        if (active) setError(String(e));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [userId]);

  return { profile, loading, error };
}
```

---

## CI Integration

```yaml
# .github/workflows/codegen.yml
name: Workers Codegen
on:
  push:
    paths:
      - 'workers/src/schemas.ts'

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npm run codegen:rn
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: regenerate RN types from Workers schemas"
          file_pattern: "src/types/api.generated.ts generated/"
```

---

## Anti-patterns

- **Writing TurboModule specs by hand to match Workers types.** Any manual synchronisation
  will drift. The codegen pipeline must be the authoritative bridge — schemas change in one
  place only.
- **Using `Object` as the return type in TurboModule specs.** Codegen will accept it but you
  lose all type safety at the JSI boundary. Use typed interfaces even if Codegen flattens
  them into `jsi::Object` under the hood; TypeScript still enforces the shape in JS code.
- **Running the codegen script only locally.** Generated files that are committed manually
  will fall out of date. Automate in CI on every schema change.
- **Sharing zod schemas between Workers and the mobile bundle.** Zod adds ~14 KB gzipped to
  the JS bundle. Use zod in Workers for runtime validation; generate plain TypeScript interfaces
  for the mobile app where bundle size matters.
- **Importing from Workers source files directly into the RN app.** The Workers runtime APIs
  (`cloudflare:workers`, `@cloudflare/workers-types`) will not resolve in Metro and crash
  the bundler. Keep schemas in a separate shared package or copy via codegen.

---

## Gotchas

- Codegen runs as part of `pod install` (iOS) and the Gradle sync (Android). If generated
  types change, `pod install` must re-run before the native build picks up new JSI bindings.
- `json-schema-to-typescript` maps `z.string().datetime()` → `string` (no `Date` type) because
  JSON has no native date type. Explicitly document date fields and add a runtime parser.
- Nullable fields in Zod (`z.nullable()`) become `T | null` in TypeScript but require special
  handling in Codegen specs — use `?` optional rather than null union where the spec is strict.
- The `TurboModuleRegistry.getEnforcing` call throws at startup if the native module is not
  linked. Gate with `TurboModuleRegistry.get` (returns null) during transitional builds where
  not all platforms have the native side implemented yet.

---

## Verification

```bash
# Regenerate and diff
npm run codegen:rn
git diff src/types/api.generated.ts

# Type-check the app
npx tsc --noEmit

# Verify Codegen spec compiles on iOS
cd ios && pod install 2>&1 | grep -i "WorkersBridge"

# Verify on Android
cd android && ./gradlew generateCodegenArtifactsFromSchema 2>&1 | tail -20
```

---

## Related

- `react-native-new-architecture-fabric-jsi.md` — Fabric and JSI fundamentals
- `react-native-new-architecture.md` — migration guide
- `react-native-hermes-engine.md` — Hermes JS engine characteristics
- `react-native-workers-hmac-signed-requests.md` — request signing for Workers calls

---

## Sources

- https://reactnative.dev/docs/the-new-architecture/what-is-the-new-architecture
- https://reactnative.dev/docs/turbo-native-modules-introduction
- https://github.com/StefanTerdell/zod-to-json-schema
- https://github.com/bcherny/json-schema-to-typescript
- https://developers.cloudflare.com/workers/languages/typescript/
