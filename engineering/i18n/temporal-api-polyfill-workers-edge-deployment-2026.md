# Temporal API Polyfill Edge Deployment for Date/Time i18n in Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Workers route formats event start times for users across 40+ locales, converting stored UTC
timestamps to local calendar-aware representations with Intl.DateTimeFormat. The legacy `Date`
object's lack of a timezone-safe arithmetic API forces hand-rolled DST offsetting that breaks on
DST transition edges. Switching to TC39 Temporal resolves the semantics—but the V8 version
running in the Workers runtime ships Temporal behind a flag, and bundling `@js-temporal/polyfill`
naively bloats the Worker well past the 3 MB compressed limit.

## Context

TC39 Temporal reached Stage 4 in late 2025. Chromium shipped it unflagged in v134; V8 embedded in
`workerd` (the open-source Workers runtime) followed in a subsequent release, but exact version
parity with production is not guaranteed. The polyfill package (`@js-temporal/polyfill`, ~500 KB
minified before compression) is not tree-shakeable in the conventional sense: CLDR timezone and
calendar data is linked by side-effect inside the build. A naïve import causes `wrangler deploy`
to warn on bundle size and may push past the 1 MB *uncompressed* script limit for free-tier
Workers, or the 3 MB limit on paid plans.

The correct strategy is **conditional polyfilling**: detect native Temporal availability at
startup, import the polyfill only when absent, and—critically—test both code paths in CI because
the production runtime may advance faster than local `wrangler dev`.

## Detecting Native Temporal in Workers

```ts
// src/temporal-compat.ts
type TemporalLike = typeof import('@js-temporal/polyfill').Temporal;

let _Temporal: TemporalLike;

export async function getTemporalNS(): Promise<TemporalLike> {
  if (_Temporal) return _Temporal;

  // globalThis.Temporal exists when V8 ships it natively
  if (typeof (globalThis as any).Temporal !== 'undefined') {
    _Temporal = (globalThis as any).Temporal as TemporalLike;
    return _Temporal;
  }

  // Dynamic import keeps the polyfill out of the main bundle chunk
  // when the Workers bundler (esbuild) performs code splitting.
  const { Temporal } = await import('@js-temporal/polyfill');
  _Temporal = Temporal;
  return _Temporal;
}
```

The dynamic `import()` works in Workers with `wrangler` ≥ 3.40 and the `nodejs_compat` flag **off**
(standard ESM splitting). Without code splitting the async path still works but the polyfill ends
up in the main chunk—profile with `wrangler deploy --dry-run --outdir dist` and inspect chunk
sizes.

## Bundle Size Strategy

### Approach 1 – wrangler build conditions

`wrangler.toml` lets you define a `[build]` block that sets `NODE_ENV`. Pair that with a custom
esbuild plugin to conditionally exclude the polyfill at build time when you know the production
runtime supports native Temporal:

```toml
# wrangler.toml
[build]
command = "npm run build:workers"

[vars]
TEMPORAL_NATIVE = "true"   # flip to "false" to force polyfill
```

```ts
// esbuild.config.ts
import { build } from 'esbuild';

const temporalNative = process.env.TEMPORAL_NATIVE === 'true';

await build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  format: 'esm',
  outfile: 'dist/worker.js',
  define: {
    '__TEMPORAL_NATIVE__': String(temporalNative),
  },
});
```

```ts
// src/temporal-compat.ts (build-time variant)
declare const __TEMPORAL_NATIVE__: boolean;

export async function getTemporalNS() {
  if (__TEMPORAL_NATIVE__) {
    return (globalThis as any).Temporal;
  }
  const { Temporal } = await import('@js-temporal/polyfill');
  return Temporal;
}
```

esbuild dead-code-eliminates the unused branch, cutting the compressed bundle from ~540 KB to
~8 KB for the Temporal import alone when `TEMPORAL_NATIVE=true`.

### Approach 2 – partial polyfill (timezone only)

If you need only `ZonedDateTime` → `Intl.DateTimeFormat` conversion and not the full Temporal
namespace, import only the timezone-safe slice:

```ts
import { Temporal } from '@js-temporal/polyfill/impl';
// 'impl' subpath skips the CLDR calendar data loader; saves ~180 KB minified
```

This trade-off: non-Gregorian calendar support (Islamic, Hebrew, Buddhist, Persian) is lost—use
`Intl.DateTimeFormat` with `calendar` option for those instead.

## Date/Time i18n Pattern with Temporal in Workers

```ts
import type { ExportedHandler, Request } from '@cloudflare/workers-types';
import { getTemporalNS } from './temporal-compat';

export default {
  async fetch(request: Request): Promise<Response> {
    const Temporal = await getTemporalNS();

    // Extract locale from Accept-Language; fall back to 'en-US'
    const acceptLang = request.headers.get('Accept-Language') ?? 'en-US';
    const locale = new Intl.Locale(acceptLang.split(',')[0].trim()).toString();

    // CF header supplies IANA tz; fall back to UTC
    const timeZone =
      (request as any).cf?.timezone ?? 'UTC';

    // Stored UTC epoch (ms) from D1/KV
    const epochMs = 1_756_000_000_000;

    const instant = Temporal.Instant.fromEpochMilliseconds(epochMs);
    const zdt = instant.toZonedDateTimeISO(timeZone);

    // Temporal.ZonedDateTime → Intl.DateTimeFormat parts
    const fmt = new Intl.DateTimeFormat(locale, {
      dateStyle: 'long',
      timeStyle: 'short',
      timeZone,
    });

    const display = fmt.format(new Date(zdt.epochMilliseconds));

    return Response.json({ locale, timeZone, display });
  },
} satisfies ExportedHandler;
```

Key point: `Temporal.ZonedDateTime` does arithmetic correctly across DST gaps (e.g., adding 1 day
to `2026-03-28T01:30:00+00:00[Europe/London]` yields the next calendar day, not 23 h later). The
final `Intl.DateTimeFormat` call handles locale-specific month name, numeral system, and time
period rendering.

## DST-Safe Duration Arithmetic

```ts
// Add 7 days to a ZonedDateTime without DST-skewing
const event = Temporal.ZonedDateTime.from({
  year: 2026, month: 3, day: 26,
  hour: 10, minute: 0,
  timeZone: 'Europe/Paris',
});

const nextWeek = event.add({ days: 7 });
// → 2026-04-02T10:00:00+02:00[Europe/Paris]
// DST transition on 2026-03-29 is absorbed; wall-clock time preserved

// Contrast with naive Date arithmetic that would give 09:00 or 11:00
const naive = new Date(event.epochMilliseconds + 7 * 86_400_000);
// naive.toLocaleTimeString('fr-FR', { timeZone: 'Europe/Paris' }) → '09:00'  ← wrong
```

## Non-Gregorian Calendar Support

```ts
const Temporal = await getTemporalNS();

// Persian calendar for fa-IR users
const persianDate = Temporal.Now.plainDateISO()
  .withCalendar('persian');

const fmt = new Intl.DateTimeFormat('fa-IR', {
  calendar: 'persian',
  year: 'numeric', month: 'long', day: 'numeric',
  numberingSystem: 'arabext',
});

// fmt.format() needs a Gregorian Date; convert via epoch
const gregorianEpochMs = persianDate
  .toPlainDateTime({ hour: 0, minute: 0, second: 0 })
  .toZonedDateTime('Asia/Tehran')
  .epochMilliseconds;

const display = fmt.format(new Date(gregorianEpochMs));
// → '۱ شهریور ۱۴۰۵'
```

When the polyfill is used, `withCalendar('persian')` relies on the CLDR calendar tables included
in `@js-temporal/polyfill`. When native Temporal is present, the engine provides its own CLDR
data—no shipping cost.

## Anti-patterns

- **Importing `@js-temporal/polyfill` unconditionally at module top level.** This forces the
  entire polyfill into the main script even when native Temporal is available and inflates cold
  start time. Always gate behind a runtime detection or a build-time flag.
- **Using `Date.now()` for arithmetic then formatting with Temporal.** `Date.now()` returns an
  epoch millisecond which is fine as an input to `Temporal.Instant.fromEpochMilliseconds`, but
  mixing `Date` arithmetic with `Temporal` formatting means DST bugs re-enter via the `Date` path.
- **Assuming `request.cf.timezone` is always present.** CF appends it for eyeball requests but
  not for Cron Triggers, Queues, or `service.fetch()` internal calls. Always have a fallback.
- **Pinning polyfill to a minor without a lock file.** CLDR data changes between polyfill minors
  and can shift plural/calendar outputs silently. Pin exact versions in `package-lock.json` and
  treat upgrades like a locale data migration.

## Gotchas

- `workerd` ships a specific V8 revision; check `wrangler --version` release notes against the
  Temporal stage in that V8. As of mid-2026, production Workers V8 supports
  `Temporal.Instant`, `Temporal.ZonedDateTime`, and `Temporal.Now` natively, but
  `Temporal.PlainYearMonth` is not yet covered in older `workerd` revisions still deployed to
  some edge PoPs.
- The polyfill's `Temporal.Now.zonedDateTimeISO()` reads the host process TZ env var when running
  under Node.js locally but reads `Intl.DateTimeFormat().resolvedOptions().timeZone` in `workerd`.
  These can diverge if your CI runner has a non-UTC TZ.
- `@js-temporal/polyfill` does not polyfill `Intl.DurationFormat` (a separate TC39 proposal).
  Duration display still requires `Intl.DurationFormat` or a manual formatter.
- Code splitting via dynamic `import()` in Workers requires `bundle = true` and esbuild's
  `splitting: true`. Check `wrangler.toml` for `[build] command` or that you are not running with
  `--no-bundle`.

## Verification

```bash
# 1. Build and inspect chunk sizes
wrangler deploy --dry-run --outdir dist
ls -lh dist/

# 2. Confirm polyfill chunk only appears when TEMPORAL_NATIVE=false
TEMPORAL_NATIVE=false npm run build:workers
grep -l 'js-temporal' dist/*.js | wc -l   # should be 1 (the split chunk)

TEMPORAL_NATIVE=true npm run build:workers
grep -l 'js-temporal' dist/*.js | wc -l   # should be 0

# 3. Integration test both paths
npx vitest run src/__tests__/temporal-compat.test.ts
```

```ts
// src/__tests__/temporal-compat.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('getTemporalNS', () => {
  beforeEach(() => {
    // Simulate no native Temporal
    delete (globalThis as any).Temporal;
  });

  it('falls back to polyfill when native Temporal absent', async () => {
    const { getTemporalNS } = await import('../temporal-compat');
    const T = await getTemporalNS();
    expect(typeof T.Instant).toBe('function');
  });

  it('uses native Temporal when present', async () => {
    const fakeTemporal = { Instant: class {} };
    (globalThis as any).Temporal = fakeTemporal;
    const { getTemporalNS } = await import('../temporal-compat');
    const T = await getTemporalNS();
    expect(T).toBe(fakeTemporal);
  });
});
```

## Related

- `date-time-timezone-workers-edge-formatting.md`
- `datetime-formatting-temporal-api-intl.md`
- `timezone-iana-temporal-2026.md`
- `intl-locale-calendar-preference-and-explicit-choice.md`
- `dst-safe-scheduling-ui-2026.md`

## Sources

- TC39 Temporal proposal: https://tc39.es/proposal-temporal/
- `@js-temporal/polyfill` npm: https://www.npmjs.com/package/@js-temporal/polyfill
- Cloudflare Workers bundle size limits: https://developers.cloudflare.com/workers/platform/limits/
- workerd V8 version tracking: https://github.com/cloudflare/workerd/blob/main/WORKSPACE
- Temporal cookbook: https://tc39.es/proposal-temporal/docs/cookbook.html
