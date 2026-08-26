# sentry-sourcemaps-upload

**Issue:** Uploading source maps to Sentry for readable stack traces in production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Sentry stack traces show minified/bundled code instead of original TypeScript source lines.

## Pattern / Solution
```bash
# Install Sentry CLI
npm install -g @sentry/cli

# Upload during CI/CD
sentry-cli releases --org my-org new $VERSION
sentry-cli releases --org my-org --project my-project files $VERSION upload-sourcemaps ./dist --rewrite
sentry-cli releases --org my-org finalize $VERSION
```

Webpack plugin (recommended):
```javascript
// webpack.config.js
const SentryWebpackPlugin = require("@sentry/webpack-plugin");

module.exports = {
  devtool: "hidden-source-map",
  plugins: [
    new SentryWebpackPlugin({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      release: process.env.VERSION,
      include: "./dist",
      ignore: ["node_modules"],
      cleanArtifacts: true,
    }),
  ],
};
```

Vite plugin: `@sentry/vite-plugin`

## Gotchas
- Use `hidden-source-map` (not `source-map`) to avoid exposing maps publicly
- `release` in `Sentry.init()` must match the release created via CLI
- Source maps must be uploaded before the release goes live

## Related
- `sentry-error-tracking.md`
- `sentry-releases.md`
- `deployment-event-tracking.md`
