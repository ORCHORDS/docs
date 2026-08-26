# React Native Hermes Bytecode Workers API Compatibility

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A React Native app compiled with Hermes bytecode (`.hbc`) throws `TypeError: fetch is not a function`
or silently fails when calling Cloudflare Workers endpoints at runtime, even though the same code
works fine in the Metro debug build. Developers also observe that `TextEncoder`, `TextDecoder`,
`AbortController`, and `crypto.subtle` behave inconsistently between Hermes debug and release builds.

## Context

Hermes pre-compiles JavaScript to bytecode during the Expo/RN build, stripping unused globals and
freezing the prototype chain at bundle time. Globals that Cloudflare Workers rely on —
`fetch`, `Headers`, `Request`, `Response`, `ReadableStream`, `crypto` — must be present in the
Hermes runtime **before** bytecode evaluation, or the bundle sees them as `undefined`.

React Native 0.73+ ships Hermes 0.12 with a broader Web API surface, but gaps remain. The
`node-fetch` and `cross-fetch` polyfills both break under bytecode because they mutate
`globalThis` at runtime, which Hermes restricts after bytecode finalisation.

Environment:
- React Native 0.73–0.76
- Hermes 0.12–0.13
- Cloudflare Workers (fetch API, Workers AI, D1 REST, R2 presigned)
- TypeScript 5.x

## Identifying the Gap

Run the Hermes introspection snippet in a release build to see which globals are missing:

```typescript
// src/debug/hermesGlobalCheck.ts
const REQUIRED_GLOBALS: string[] = [
  'fetch',
  'Headers',
  'Request',
  'Response',
  'AbortController',
  'AbortSignal',
  'ReadableStream',
  'TextEncoder',
  'TextDecoder',
  'crypto',
  'FormData',
  'URL',
  'URLSearchParams',
];

export function auditHermesGlobals(): Record<string, boolean> {
  const result: Record<string, boolean> = {};
  for (const name of REQUIRED_GLOBALS) {
    result[name] = typeof (globalThis as Record<string, unknown>)[name] !== 'undefined';
  }
  return result;
}

// Call early in App.tsx before any Workers fetch:
// console.log(JSON.stringify(auditHermesGlobals(), null, 2));
```

## Polyfill Strategy for Hermes Bytecode

The key constraint: polyfills must be **native modules** registered before bytecode runs, not
JS-only patches. Use the `react-native-url-polyfill` and `react-native-fetch-api` packages which
register via native JSI, surviving Hermes bytecode:

```typescript
// index.js (entry point — before any other import)
import 'react-native-url-polyfill/auto';          // URL, URLSearchParams
import 'react-native-fetch-api';                   // fetch, Headers, Request, Response
import { setupWorkersCompat } from './src/workersCompat';

setupWorkersCompat();

import { AppRegistry } from 'react-native';
import App from './App';
import { name as appName } from './app.json';

AppRegistry.registerComponent(appName, () => App);
```

```typescript
// src/workersCompat.ts
import { NativeModules } from 'react-native';

export function setupWorkersCompat(): void {
  // AbortController shim for Hermes < 0.12
  if (typeof AbortController === 'undefined') {
    const { AbortControllerNative } = NativeModules;
    if (AbortControllerNative) {
      globalThis.AbortController = AbortControllerNative;
    } else {
      // Minimal JS fallback — fine for fetch timeouts, not for streams
      class AbortControllerShim {
        signal = { aborted: false, addEventListener: () => {}, removeEventListener: () => {} };
        abort() { this.signal.aborted = true; }
      }
      // @ts-expect-error — polyfill assignment
      globalThis.AbortController = AbortControllerShim;
    }
  }

  // crypto.getRandomValues — needed for Workers HMAC signing on-device
  if (typeof crypto === 'undefined' || !crypto.getRandomValues) {
    const { ExpoRandom } = NativeModules; // expo-random or equivalent
    if (ExpoRandom) {
      // @ts-expect-error
      globalThis.crypto = {
        getRandomValues: <T extends ArrayBufferView>(array: T): T => {
          const bytes = ExpoRandom.getRandomBytesSync(array.byteLength);
          const u8 = new Uint8Array(array.buffer);
          for (let i = 0; i < bytes.length; i++) u8[i] = bytes[i];
          return array;
        },
      };
    }
  }
}
```

## Workers API Client with Hermes-Safe Patterns

```typescript
// src/api/workersClient.ts
const WORKER_BASE = 'https://api.example.workers.dev';

interface WorkerRequestOptions {
  path: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  token?: string;
}

export async function callWorker<T>(opts: WorkerRequestOptions): Promise<T> {
  const { path, method = 'GET', body, signal, token } = opts;

  // Build headers without spreading — Hermes bytecode can mishandle spread on Headers objects
  const headers = new Headers();
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const requestInit: RequestInit = { method, headers };
  if (signal) requestInit.signal = signal;
  if (body !== undefined) requestInit.body = JSON.stringify(body);

  const response = await fetch(`${WORKER_BASE}${path}`, requestInit);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Workers API ${method} ${path} → ${response.status}: ${errorText}`);
  }

  // Avoid response.json() — its error message is stripped in Hermes release builds
  const text = await response.text();
  return JSON.parse(text) as T;
}
```

## Hermes Bytecode Build Configuration

Add the Hermes-specific Metro config to ensure polyfills are bundled before bytecode emission:

```javascript
// metro.config.js
const { getDefaultConfig, mergeConfig } = require('@react-native/metro-config');

const config = {
  transformer: {
    getTransformOptions: async () => ({
      transform: {
        experimentalImportSupport: false,
        inlineRequires: true, // critical: resolves polyfill ordering in Hermes
      },
    }),
  },
  resolver: {
    // Ensure Web API polyfills resolve to Hermes-compatible versions
    extraNodeModules: {
      'node-fetch': require.resolve('react-native-fetch-api'),
    },
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
```

In `android/app/build.gradle` and `ios/Podfile`, confirm Hermes is enabled and bytecode targets
match:

```gradle
// android/app/build.gradle
android {
  defaultConfig {
    // ...
  }
}
project.ext.react = [
  enableHermes: true,
  hermesCommand: "../../node_modules/react-native/sdks/hermesc/%OS-BIN%/hermesc",
  hermesFlags: ["-O", "-output-source-map"], // -O enables bytecode optimisation
]
```

## Anti-patterns

- **`node-fetch` or `cross-fetch` as direct imports** — both patch `global.fetch` at JS runtime,
  which fires after Hermes bytecode locks globals. Use JSI-registered polyfills only.
- **`response.json()` in release builds** — Hermes strips V8 JSON error context; always parse via
  `response.text()` then `JSON.parse()` for debuggable errors.
- **Spread operator on `Headers`** — `{ ...existingHeaders }` converts Headers to a plain object
  and drops methods. Use `new Headers(existingHeaders)` or `headers.set()` chains.
- **`crypto.subtle` for signing on-device** — `SubtleCrypto` is absent in Hermes < 0.13. Perform
  HMAC signing in the Worker, or use a JSI-native crypto module.
- **Dynamic `import()` of polyfills** — dynamic imports are deferred to after bytecode execution.
  All polyfills must be static imports in `index.js`.

## Gotchas

- Hermes bytecode versions are **tightly coupled** to the RN version. Updating RN without
  rebuilding all `.hbc` files leads to silent runtime mismatches.
- `inlineRequires: true` in Metro can reorder polyfill imports. Always verify ordering by
  inspecting the Metro bundle output (`npx react-native bundle --dev false --out bundle.js`).
- iOS Simulator uses JavaScriptCore (JSC), not Hermes, so globals missing in Hermes are available
  in Simulator. Always test on a physical device with a release build.
- The `AbortSignal.timeout()` static method is absent in Hermes 0.12; implement a manual wrapper.

## Verification

```typescript
// src/__tests__/hermesCompat.test.ts
describe('Hermes Workers API compatibility', () => {
  it('fetch is defined', () => {
    expect(typeof fetch).toBe('function');
  });

  it('Headers constructor works', () => {
    const h = new Headers({ 'x-test': 'value' });
    expect(h.get('x-test')).toBe('value');
  });

  it('AbortController is defined', () => {
    const ctrl = new AbortController();
    expect(ctrl.signal.aborted).toBe(false);
  });

  it('callWorker returns typed data', async () => {
    const data = await callWorker<{ ok: boolean }>({ path: '/health' });
    expect(data.ok).toBe(true);
  });
});
```

Run on device:
```bash
npx react-native run-android --variant=release
npx react-native run-ios --configuration Release
```

## Related

- `react-native-hermes-engine.md`
- `react-native-hermes-performance-profiling.md`
- `react-native-workers-hmac-signed-requests.md`
- `react-native-new-architecture-fabric-jsi.md`
- `mobile-network-resilience-cloudflare-workers.md`

## Sources

- https://reactnative.dev/docs/hermes
- https://hermesengine.dev/docs/building-and-running
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://github.com/nicolo-ribaudo/fetch-ponyfill-performance
- https://metrobundler.dev/docs/configuration
