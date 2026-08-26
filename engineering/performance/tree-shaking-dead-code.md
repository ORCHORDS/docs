# Tree Shaking and Dead Code Elimination

## What is Tree Shaking?

Tree shaking is a dead code elimination technique that removes unused JavaScript code from final bundles. It works by statically analyzing ES module imports and exports to identify which code is actually used.

```javascript
// math.js
export const add = (a, b) => a + b;
export const subtract = (a, b) => a - b;
export const multiply = (a, b) => a * b;

// main.js
import { add } from './math.js';
console.log(add(2, 3));
```

In this example, `subtract` and `multiply` functions are eliminated during tree shaking since they're not imported.

## ES Modules and Tree Shaking

ES modules enable tree shaking through static analysis. Unlike CommonJS, ES modules declare imports/exports at the top level, making them predictable for bundlers.

```javascript
// Good - Static imports work with tree shaking
import { debounce } from 'lodash-es';
import { format } from 'date-fns';

// Bad - Dynamic imports break tree shaking
const module = await import('lodash-es');
```

## Side Effects and Pure Annotations

Side effects prevent tree shaking. Code with side effects (like console.log, global mutations) must be preserved.

```javascript
// This file has side effects
console.log('Hello world'); // Side effect
export const value = 42;

// Pure annotations help bundlers understand code behavior
/*#__PURE__*/ Math.random(); // Mark as pure function
```

## Production Mode and Webpack

Webpack's production mode automatically enables tree shaking through `mode: 'production'`:

```javascript
// webpack.config.js
module.exports = {
  mode: 'production',
  optimization: {
    usedExports: true,
    sideEffects: false
  }
};
```

## Vite's optimizeDeps

Vite uses `optimizeDeps` to pre-bundle dependencies and enable tree shaking:

```javascript
// vite.config.js
export default {
  optimizeDeps: {
    include: ['lodash-es'],
    exclude: ['react']
  }
}
```

## Verifying Tree Shaking Output

Check bundle size and content using tools like webpack-bundle-analyzer:

```bash
# Install analyzer
npm install --save-dev webpack-bundle-analyzer

# Analyze bundle
npx webpack-bundle-analyzer dist/bundle.js
```

```javascript
// Example of verifying unused code removal
// Before tree shaking: 10KB bundle
// After tree shaking: 2KB bundle (80% reduction)
```

## Common Pitfalls

### 1. Side Effects in Dependencies
```javascript
// Problem: Importing modules with side effects
import 'some-module'; // May have unwanted side effects

// Solution: Configure sideEffects in package.json
{
  "sideEffects": false
