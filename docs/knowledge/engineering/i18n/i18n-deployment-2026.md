# i18n-deployment-2026

**Issue:** A team localizes a product to 15 languages. Translations live in a TMS (Lokalise, Crowdin, Phrase). Engineers need to get the latest translations into the production app. The team debates CDN delivery, in-app JSON, lazy-load vs full-bundle.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 deployment patterns

1. **Compile-in.** All locales bundled with the app. Simple, large bundle.
2. **Locale-on-demand.** Lazy-load the user's locale on first visit. Cached.
3. **Per-route loading.** Each route lazy-loads its namespace. Best for large apps.
4. **CDN-served JSON.** TMS pushes to CDN; app fetches at runtime. Easy translator updates.
5. **Pull-on-build.** CI fetches latest from TMS, builds with translations. Atomic, no runtime fetch.

## The 5-step decision rule

1. **Static site, 1-3 locales, low translation churn** → compile-in.
2. **Web app, 5-15 locales, frequent updates** → CDN-served JSON.
3. **Mobile app, 10+ locales, slow networks** → bundle the user's locale, download others on demand.
4. **Large web app with 100+ namespace** → per-route loading + namespace lazy-load.
5. **Production-stable translations, fast release** → pull-on-build.

## The 5 best practices

1. **Cache locale JSON aggressively** with content-hash filenames.
2. **Use `Intl.DisplayNames` for the picker** so users see their own language.
3. **Lazy-load namespaces** for routes not yet visited.
4. **Detect locale from `Accept-Language` header** server-side fallback.
5. **Monitor translation coverage** (untranslated key count per locale) in CI.

## The 5 anti-patterns

1. **Bundle all 50 locales into 200KB app.** Most users see one locale.
2. **Fetch translations from TMS at runtime in production.** Outage = untranslated UI.
3. **No caching strategy.** Every page load refetches JSON.
4. **Hardcoded fallback to English.** Users in non-English markets get worse experience.
5. **No "translation missing" indicator.** Silent fallback hides gaps.

## Gotchas

- **CDN cache invalidation** is the bottleneck for CDN-served JSON. Use content-hash filenames, not versioned URLs.
- **Lazy-loading requires Suspense or fallback UI** to avoid layout shift.
- **Accept-Language parsing** is non-trivial; use `Intl.LocaleMatcher` or library.
- **Mobile offline** complicates lazy-load; bundle the active locale.
- **Pseudo-loc testing** must run against the actual catalog, not mock.

## Source URLs (verified 2026-08-10)

- https://www.i18next.com/how-to/add-or-load-languages
- https://formatjs.io/docs/getting-started/message-distribution
- https://lokalise.com/blog/continuous-localization
- https://phrase.com/blog/posts/continuous-localization-workflow/
