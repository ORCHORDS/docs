# Bundle Size Budgets

## What are Bundle Size Budgets?

Bundle size budgets are performance thresholds that limit the maximum size of JavaScript bundles in web applications. They prevent bundle bloat by enforcing size limits during development and CI/CD pipelines, ensuring applications remain fast and responsive.

## Performance Budgets

Performance budgets define acceptable limits for various bundle sizes. Set realistic targets based on your application's complexity and target devices:

```json
{
  "budgets": [
    {
      "type": "initial",
      "maximumWarning": "240 KB",
      "maximumError": "300 KB"
    },
    {
      "type": "parsed",
      "maximumWarning": "1.5 MB",
      "maximumError": "2 MB"
    }
  ]
}
```

## Size-Limit Tool

Size-limit is a popular tool for monitoring bundle sizes:

```bash
npm install --save-dev size-limit
```

Configure in `package.json`:
```json
{
  "size-limit": [
    {
      "path": "dist/**/*.js",
      "limit": "240 KB"
    }
  ]
}
```

Run with: `npx size-limit`

## BundleSize CI Integration

Integrate bundle size monitoring into your CI pipeline:

```yaml
# .github/workflows/bundle-size.yml
name: Bundle Size
on: [push, pull_request]
jobs:
  bundle-size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: npm ci
      - run: npm run build
      - run: npx bundlesize
```

## Initial JS Budget

Set specific limits for initial JavaScript load:

```javascript
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
        }
      }
    }
  },
  performance: {
    maxEntrypointSize: 240000, // 240 KB
    maxAssetSize: 250000, // 250 KB
  }
};
```

## Route-Level Splitting

Implement code splitting by route to reduce initial bundle size:

```javascript
// routes.js
const Home = () => import('./views/Home.vue');
const About = () => import('./views/About.vue');

const routes = [
  {
    path: '/',
    component: Home
  },
  {
    path: '/about',
    component: About
  }
];
```

## Size Analysis Tools

Use tools to analyze bundle composition:

```bash
