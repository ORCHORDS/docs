# i18n Bundle Size and Tree-Shaking (2026)

## Symptom

Your SPA ships fine in English (200KB JS). You add 10 locales and the
bundle balloons to 2MB. Lighthouse screams. Mobile users on 3G wait 8
seconds for first paint. The cause: every locale's message catalog and
its CLDR locale data is statically imported into the main chunk.

## Why i18n blows up bundle size

- **Message catalogs.** 1000 keys x 10 locales = 10,000 strings. Even at
  50 bytes each that is 500KB of JSON shipped whether the user needs it or not.
- **CLDR locale data.** `@formatjs/intl-*` polyfills, `Intl.PluralRules`
  data, full locale calendars/numbering systems. Per locale, often 30-100KB.
- **ICU runtime.** `intl-messageformat` parser is ~20KB; one copy per
  entry chunk if not deduped.
- **Full libraries imported.** `import * from 'date-fns/locale'` pulls
  every locale. Same for `moment/locale/*` (still haunted by legacy code).

## Strategies (in order of impact)

### 1. Code-split locales by route or by user locale
Only load the user's active locale. Use dynamic import:

```js
const messages = await import(`./locales/${locale}.json`);
```

Webpack and Vite will emit one chunk per locale. The user downloads
exactly one locale file.

### 2. Lazy-load CLDR data
```js
import(`@formatjs/intl-numberformat/locale-data/${locale}`);
```
Never `import '@formatjs/intl-numberformat/locale-data'` (all locales).

### 3. Tree-shake the i18n library
- `react-i18next`: import only `useTranslation`, not the whole package.
- `formatjs`: use `react-intl`'s named imports; avoid `*`.
- `lodash`-style barrel imports kill tree-shaking.

### 4. Drop unused plural categories
English needs only `one`/`other`. If you ship English-only first, strip
the `few`/`many`/`zero` fields from the en catalog. CLDR plural rules
data for `en` is ~200 bytes; for `ar` it is ~2KB.

### 5. Compile ICU at build time
Use `@formatjs/cli` to pre-compile messages into AST JSON. The runtime
skips parsing -- saves ~15KB and CPU on first paint.

### 6. Compress and Brotli
JSON compresses extremely well. Ensure your CDN serves `.json` locale
chunks with `Content-Encoding: br` (Brotli). 500KB JSON -> ~60KB over wire.

### 7. Preload the user's locale
`<link rel="modulepreload" >` in the document head,
gated by the cookie-detected locale (see locale-persistence file).

## Gotchas

- **Dynamic import paths must be statically analyzable.** Webpack/Vite
  need a template literal with a variable: `./locales/${locale}.json`.
  Don't build the path with string concatenation that hides the folder --
  the bundler will not split it.
- **Server-side rendering changes the math.** On SSR you need ALL locales
  reachable from the server bundle, but you should still stream only the
  user's locale in the initial HTML. Hydrate with the same locale.
- **`moment.js` is the worst offender.** It cannot tree-shake. Migrate to
  `date-fns`, `dayjs`, or the native `Intl` APIs (`Temporal` in 2026).
- **CLDR data via polyfill is loaded at runtime, not bundle time.**
  `Intl.PluralRules` polyfill `tryAddLocaleData` fetches on demand. Make
  sure your CDN caches it or it round-trips every session.
- **JSON dead-code elimination is limited.** Bundlers cannot remove unused
  JSON keys the way they remove unused JS exports. Run a custom script to
  strip keys not referenced in code (`i18next-parser` in reverse).
- **Namespace splitting helps huge apps.** `react-i18next` namespaces
  (`common`, `dashboard`, `settings`) let you load only the relevant
  namespace for a route. Don't ship the entire catalog to the login page.
- **Translation string length affects layout shift (CLS).** German strings
  are ~30% longer than English. If you lazy-load, English renders first
  and German pushes the layout on arrival. Reserve space or show a skeleton.
- **Audit with `webpack-bundle-analyzer` / `vite-bundle-visualizer`.**
  Look for a giant `locales` chunk. Anything >200KB per locale is a smell.
- **Brotli over gzip matters more for JSON than for JS.** JSON's repetition
  compresses ~15-20% better with Brotli. Verify your host supports it.
- **Avoid `require.context('./locales', true, /\.json$/)`.** It pulls
  every file eagerly. Use explicit dynamic imports per locale instead.

## Checklist

1. One dynamic import per locale; never static-import all.
2. CLDR data loaded per-locale, not as a single global.
3. Pre-compile ICU messages at build time.
4. Strip unused plural categories and orphan keys.
5. Brotli compression on JSON chunks.
6. Visualize the bundle; investigate any locale chunk >200KB.
