# webpack-code-splitting

**Issue:** Single large bundle causes slow initial load times
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The main.js bundle is 4 MB and blocks first paint on slow connections.

## Pattern / Solution
```js
// webpack.config.js
module.exports = {
  optimization: {
    splitChunks: {
      chunks: 'all',
      cacheGroups: {
        vendor: {
          test: /[\\/]node_modules[\\/]/,
          name: 'vendors',
          chunks: 'all',
        },
        charts: {
          test: /[\\/]node_modules\\/[\\/]/,
          name: 'charts',
          chunks: 'async',
        },
      },
    },
  },
};

// Dynamic import in code
const Chart = React.lazy(() => import('./Chart'));
```

## Gotchas
- Granular chunks can increase HTTP/1.1 connection overhead; HTTP/2 mitigates this
- Named chunks are easier to cache; content hash naming for long-term caching
- Circular imports prevent splitting; use webpack-bundle-analyzer to diagnose

## Related
- `code-splitting-dynamic-import.md`
- `bundle-analysis-webpack-bundle-analyzer.md`
