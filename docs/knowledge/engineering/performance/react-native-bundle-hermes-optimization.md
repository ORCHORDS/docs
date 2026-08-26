# React Native Bundle Size Optimization for Hermes

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A React Native app cold-starts in 4.2 seconds on a mid-range Android device.  Profiling shows the JavaScript bundle is 8.4 MB (uncompressed), taking 2.1 seconds to load and parse.  After switching to Hermes (Facebook's optimized JavaScript engine), the startup drops to 2.8 seconds — but is still too slow.  Further investigation reveals the bundle includes multiple copies of utility libraries, un-tree-shaken code paths, and a translation library that includes all 70 locales when only 3 are used.  These are addressable through Hermes-aware bundle optimization, which differs from browser-JS optimization because Hermes pre-compiles to bytecode and has different dead-code elimination characteristics.

## Context

**Hermes** is an ahead-of-time (AOT) JavaScript engine designed specifically for React Native.  Instead of parsing and JIT-compiling JavaScript at runtime, Hermes compiles the JS bundle into **Hermes Bytecode (HBC)** at build time.  The device executes HBC directly, eliminating parse time and reducing JIT warm-up.

Hermes startup characteristics vs JSC (JavaScriptCore):

| Metric | JSC (baseline) | Hermes (HBC) |
|--------|---------------|-------------|
| Parse time (8 MB bundle) | ~1,800 ms | ~0 ms (pre-compiled) |
| Execute-to-first-render | ~2,400 ms | ~800 ms |
| Memory at startup | ~120 MB | ~90 MB |
| HBC file size vs JS | N/A | +10–25% larger |

Key insight: **Hermes shifts the cost from runtime to build time**.  The HBC file is larger than the JS source (due to bytecode metadata), but the device executes it faster.  This changes the optimization strategy:

- **For JSC:** minimize JS bundle size to reduce parse time.
- **For Hermes:** minimize JS bundle size to reduce *HBC file size and I/O time* (disk read + decompression), because parse time is already eliminated.  The bottleneck shifts from parse to I/O.

Enable Hermes in `android/app/build.gradle`:

```groovy
project.ext.react = [
    enableHermes: true,  // Required for Hermes
]
```

And in `ios/Podfile`:
```ruby
use_react_native!(
  :hermes_enabled => true
)
```

## Section 1 — Measuring Bundle Composition with Metro Bundle Analyzer

Before optimizing, measure.  Metro (the React Native bundler) does not ship a visual analyzer by default, but `@expo/metro-inspector` and `react-native-bundle-visualizer` both produce treemaps compatible with the Hermes workflow:

```bash
# Install visualizer
npx react-native-bundle-visualizer
# This runs Metro, produces bundle.json, opens a treemap in the browser
```

For production-accurate analysis including Hermes HBC size:

```bash
# Build a release bundle (Android example)
npx react-native bundle \
  --platform android \
  --dev false \
  --entry-file index.js \
  --bundle-output /tmp/index.android.bundle \
  --assets-dest /tmp/assets

# Check raw JS bundle size
wc -c /tmp/index.android.bundle

# Build HBC (what actually ships) — requires Hermes compiler
./node_modules/react-native/sdks/hermesc/bin/hermesc \
  -emit-binary \
  -output-source-map \
  -out /tmp/index.android.bundle.hbc \
  /tmp/index.android.bundle

wc -c /tmp/index.android.bundle.hbc
```

Typical ratio: if the JS bundle is 8 MB, the HBC is 9–10 MB.  The device reads the HBC from disk (or OTA update cache), so minimizing JS bundle size directly reduces HBC I/O time.

## Section 2 — Tree-Shaking and Import Audit for Hermes

Hermes's dead-code elimination at HBC compile time is **less aggressive than webpack/Metro's** JS-level tree-shaking.  Dead code must be eliminated in the Metro bundler stage, not left to Hermes.

Common bundle bloat patterns and fixes:

**Pattern 1: Full lodash import**

```javascript
// BAD — imports all of lodash (~70 KB)
import _ from 'lodash';
const result = _.groupBy(items, 'category');

// GOOD — import only the function used (~3 KB)
import groupBy from 'lodash/groupBy';
const result = groupBy(items, 'category');
```

Configure Metro to enforce cherry-picking via a custom resolver:

```javascript
// metro.config.js
const { getDefaultConfig } = require('@react-native/metro-config');

const config = getDefaultConfig(__dirname);

config.resolver.resolverMainFields = ['react-native', 'browser', 'main'];

// Block barrel imports from lodash to force per-function imports
config.resolver.blockList = [/node_modules\/lodash\/lodash\.js$/];

module.exports = config;
```

**Pattern 2: moment.js with all locales**

```javascript
// BAD — moment includes all 70+ locale files by default
import moment from 'moment';

// GOOD — use date-fns (tree-shakeable, Hermes-compatible)
import { format, parseISO } from 'date-fns';
// Or if you must use moment, exclude all locales then require only what you need:
import moment from 'moment';
import 'moment/locale/en-gb';
import 'moment/locale/es';
```

Metro config to drop unused moment locales:

```javascript
// metro.config.js
const path = require('path');
const { getDefaultConfig } = require('@react-native/metro-config');

const config = getDefaultConfig(__dirname);

// Custom transformer to strip moment locale files
const originalResolver = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (/moment\/locale\/.+/.test(moduleName)) {
    const allowed = ['moment/locale/en', 'moment/locale/es'];
    if (!allowed.includes(moduleName)) {
      // Return an empty module for non-allowed locales
      return { type: 'empty' };
    }
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
```

**Pattern 3: Duplicate package versions**

```bash
# Find duplicate packages across different semver ranges
npx react-native-bundle-visualizer --show-duplicates

# Or manually with jq
node -e "
  const lock = require('./package-lock.json');
  const pkgs = {};
  for (const [name, meta] of Object.entries(lock.packages || {})) {
    const base = name.replace(/^node_modules\//, '').split('/node_modules/').pop();
    (pkgs[base] = pkgs[base] || []).push(meta.version);
  }
  Object.entries(pkgs).filter(([,v]) => new Set(v).size > 1).forEach(([n,v]) => console.log(n, v));
"
```

Deduplicate by hoisting to a shared version in `package.json`:

```json
{
  "resolutions": {
    "react-is": "18.3.1",
    "tslib": "2.7.0"
  }
}
```

## Section 3 — Code Splitting and RAM Bundles for Hermes

React Native supports **RAM (Random Access Module) bundles**, which load module code on demand rather than parsing the entire bundle at startup.  On Hermes, RAM bundles are the equivalent of browser lazy loading.

Enable RAM bundles:

```bash
npx react-native bundle \
  --platform android \
  --dev false \
  --entry-file index.js \
  --bundle-output index.android.bundle \
  --indexed-ram-bundle   # Produces an indexed binary format for fast module lookup
```

In `android/app/build.gradle`:

```groovy
project.ext.react = [
    enableHermes: true,
    bundleCommand: "ram-bundle",
    extraPackagerArgs: ["--indexed-ram-bundle"]
]
```

For iOS (uses file RAM bundle — one file per module):

```groovy
project.ext.react = [
    enableHermes: true,
    bundleCommand: "ram-bundle"
]
```

Pair with **inline requires** to defer module evaluation to first use:

```javascript
// babel.config.js — enable inline requires
module.exports = {
  presets: ['module:@react-native/babel-preset'],
  plugins: [
    ['@babel/plugin-transform-modules-commonjs', { lazy: true }],
  ],
  env: {
    production: {
      plugins: ['transform-inline-environment-variables'],
    },
  },
};
```

Or enable inline requires via Metro directly:

```javascript
// metro.config.js
config.transformer.getTransformOptions = async () => ({
  transform: {
    experimentalImportSupport: false,
    inlineRequires: true,    // Defer require() calls to first use
  },
});
```

**Inline requires** ensure that `require('heavy-screen')` is not executed at startup — only when the user navigates to that screen.  Combined with RAM bundles, this can reduce startup module evaluation from 300+ modules to 30–50 modules.

## Section 4 — Hermes Profiling and Startup Trace Analysis

Hermes ships with a built-in sampling profiler that produces flamegraph output readable in Chrome DevTools:

```javascript
// In your app's development entry point
import { useEffect } from 'react';

export function useHermesProfiling(enabled = __DEV__) {
  useEffect(() => {
    if (!enabled || !global.HermesInternal) return;

    // Start profiling
    global.HermesInternal.enableSamplingProfiler?.();

    return () => {
      // Stop and save the profile
      global.HermesInternal.disableSamplingProfiler?.();
      // The profile is written to the device; retrieve with:
      // adb shell cat /data/user/0/<package>/files/hermesProfile*.json > profile.json
    };
  }, []);
}
```

```bash
# Retrieve Hermes profile from Android device
adb shell run-as com.yourapp cat /data/data/com.yourapp/cache/hermesProfile.json > /tmp/hermes.json

# Convert to Chrome-readable format
npx hermes-profile-transformer /tmp/hermes.json -o /tmp/chrome-trace.json

# Open chrome://tracing and load chrome-trace.json
```

Key metrics to look for in the Hermes startup trace:

| Metric | Target | Warning |
|--------|--------|---------|
| `JS bundle load (I/O)` | < 200 ms | > 500 ms |
| `HBC module parse` | < 50 ms (Hermes pre-compiles) | > 200 ms (fallback to JS) |
| `require() calls before first render` | < 50 | > 150 |
| `React tree render` | < 300 ms | > 800 ms |

## Anti-patterns

- **Enabling Hermes but not building RAM bundles** — Hermes without RAM bundles still loads the entire HBC file before executing any module.  RAM bundles are the second required optimization step.
- **Importing from barrel files (index.js re-exports)** — `import { Button } from '@ui-kit'` where `ui-kit/index.js` re-exports 200 components causes Metro to bundle all 200 components even if you use only one.  Import directly from `@ui-kit/Button`.
- **Using `require()` inside module scope for side-effectful imports** — `require('polyfill')` at the top of a file is evaluated at startup even with inline requires enabled.  Polyfills must go in the entry file, not in feature modules.
- **Not generating source maps for the HBC file** — without source maps, Hermes crash reports reference HBC bytecode offsets, not source file lines.  Always pass `--source-map` to `hermesc` and upload the source map to your crash reporter.
- **Benchmarking on a dev build** — the dev bundle includes React error messages, hot reload infrastructure, and warning overlays, making it 3–5× larger than a production bundle.  Always benchmark release builds.

## Gotchas

- Hermes does **not** support all ES2022+ features.  Check `hermes/website` for the compatibility table.  Features like `Object.hasOwn()` and `Array.at()` may need Babel polyfills for older Hermes versions bundled with older React Native versions.
- The `global.HermesInternal` object is `undefined` on JSC.  Always guard Hermes-specific calls with `global.HermesInternal?.`.
- RAM bundles are not supported by the Expo Go client.  Use a custom dev client (`expo-dev-client`) to test RAM bundle behavior.
- Hermes HBC files are not cross-compatible between Hermes versions.  If you deliver OTA updates (Expo Updates, CodePush), the HBC must be compiled with the same Hermes version bundled in the installed native binary.  A version mismatch causes a crash at startup.
- `inlineRequires` can cause subtle behavioral differences if your code relies on module-level side effects executing at import time.  Test thoroughly; set `inlineRequires: false` for specific files via Metro's `transform` option if needed.

## Verification

1. Measure cold-start time on a physical mid-range Android device (not an emulator) before and after RAM bundles + inline requires.  Use `adb logcat | grep -E 'ReactNative|Hermes'` to find the `runJSBundle` timing log line.  Target: > 40% reduction from baseline.
2. Validate tree-shaking: run `npx react-native-bundle-visualizer` before and after lodash cherry-picking.  The `lodash` node in the treemap should shrink from ~70 KB to ≤ 5 KB.
3. Verify Hermes is active on device: `console.log(global.HermesInternal?.getRuntimeProperties?.())` should print `{ Build: { ... }, Snapshot: ... }`.  If it logs `undefined`, Hermes is not running.

## Related

- `javascript-bundle-size.md` — general bundle size analysis patterns
- `bundle-size-budgets.md` — setting and enforcing bundle budgets
- `dead-code-elimination.md` — tree-shaking fundamentals
- `javascript-tree-shaking-dead-code-elimination.md` — Metro-specific tree-shaking
- `code-splitting-strategies.md` — code splitting patterns applicable to RN

## Sources

- Hermes documentation: https://hermesengine.dev/
- React Native Hermes guide: https://reactnative.dev/docs/hermes
- RAM bundles overview: https://reactnative.dev/docs/ram-bundles-inline-requires
- Metro bundler: https://metrobundler.dev/
- Hermes profile transformer: https://www.npmjs.com/package/hermes-profile-transformer
