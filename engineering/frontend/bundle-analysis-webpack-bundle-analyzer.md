# bundle-analysis-webpack-bundle-analyzer

**Issue:** Unknown what is inside the production bundle; large dependencies go unnoticed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The app bundle is 2 MB but no one knows why; moment.js locale files are included unnecessarily.

## Pattern / Solution
```bash
# Webpack
npm install --save-dev webpack-bundle-analyzer
npx webpack --profile --json > stats.json
npx webpack-bundle-analyzer stats.json

# Vite
npm install --save-dev rollup-plugin-visualizer
```

```ts
// vite.config.ts
import { visualizer } from 'rollup-plugin-visualizer';
plugins: [visualizer({ open: true, gzipSize: true })];

// Next.js
// @next/bundle-analyzer
const withBundleAnalyzer = require('@next/bundle-analyzer')({ enabled: true });
module.exports = withBundleAnalyzer({});
```

## Gotchas
- Analyse gzip size, not raw size — that is what users download
- Look for duplicate packages (multiple React versions, lodash + lodash-es)
- moment.js includes all 160 KB of locales by default; use date-fns or dayjs instead

## Related
- `tree-shaking-patterns.md`
- `webpack-code-splitting.md`
