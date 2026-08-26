# ESLint Rules for Cloudflare Workers Compatibility

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Workers run on the V8 isolate runtime, not Node.js, so APIs like `setTimeout` at module scope, `process.env`, and many browser globals either behave differently or are absent entirely. Without lint rules enforcing Workers-compatible patterns, forbidden APIs slip through code review and only surface as runtime errors after deploy.

---

## Context

The Workers runtime implements a subset of the Web Platform APIs and exposes its own globals (`caches`, `crypto`, `fetch`, `Request`, `Response`, etc.). It does not expose `process`, `Buffer` (unless polyfilled), or Node.js built-ins unless the `nodejs_compat` compatibility flag is enabled. `setTimeout` and `setInterval` exist inside a request handler but calling them at module scope (top-level) is a footgun because isolates are not guaranteed to be long-lived. ESLint's flat config system (eslint ≥ 9) makes it straightforward to compose plugin rules with custom local rules for Workers-specific concerns.

---

## Config / Setup

```jsonc
// package.json — relevant dev deps
{
  "devDependencies": {
    "eslint"                                   : "^9.9.0",
    "@typescript-eslint/eslint-plugin"         : "^8.2.0",
    "@typescript-eslint/parser"                : "^8.2.0",
    "eslint-plugin-no-unsupported-browser-features": "^5.0.1"
  },
  "scripts": {
    "lint"     : "eslint src/",
    "lint:fix" : "eslint src/ --fix"
  }
}
```

```toml
# wrangler.toml — compatibility flags referenced by the custom rule
compatibility_date  = "2024-09-23"
compatibility_flags = []
# Add "nodejs_compat" here if you intentionally use Node.js APIs
```

---

## Implementation — ESLint Flat Config

```typescript
// eslint.config.ts
import tsPlugin  from '@typescript-eslint/eslint-plugin';
import tsParser  from '@typescript-eslint/parser';
import noUnsupportedBrowserFeatures from 'eslint-plugin-no-unsupported-browser-features';
import workersRules from './eslint-rules/workers.js';

export default [
  {
    files   : ['src/**/*.ts'],
    plugins : {
      '@typescript-eslint'           : tsPlugin,
      'no-unsupported-browser-features': noUnsupportedBrowserFeatures,
      'workers'                      : workersRules,
    },
    languageOptions: {
      parser        : tsParser,
      parserOptions : {
        project        : './tsconfig.json',
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // --- TypeScript safety -------------------------------------------
      '@typescript-eslint/no-floating-promises'           : 'error',
      '@typescript-eslint/no-misused-promises'            : 'error',
      '@typescript-eslint/await-thenable'                 : 'error',
      '@typescript-eslint/require-await'                  : 'warn',
      '@typescript-eslint/no-explicit-any'                : 'warn',

      // --- Workers-specific custom rules --------------------------------
      'workers/no-module-scope-timers'                    : 'error',
      'workers/no-process-env'                            : 'error',
      'workers/no-node-builtins'                          : 'warn',

      // --- Browser-features plugin (targets Workers globals subset) -----
      // Targets a "chrome" version that approximates the Workers V8 version.
      // Workers supports a wide Web API surface; this catches the worst offenders.
      'no-unsupported-browser-features/no-unsupported-browser-features': [
        'warn',
        {
          severity : 'warn',
          browsers : ['last 2 Chrome versions'],
          ignore   : [
            // Workers polyfills these:
            'fetch',
            'WebSocket',
            'URL',
          ],
        },
      ],
    },
  },
];
```

```javascript
// eslint-rules/workers.js  — custom local ESLint plugin
// Compatible with ESLint flat config (v9)

/** @type {import('eslint').Rule.RuleModule} */
const noModuleScopeTimers = {
  meta: {
    type    : 'problem',
    docs    : {
      description: 'Disallow setTimeout/setInterval at module (top-level) scope in Workers',
      recommended: true,
    },
    schema  : [],
    messages: {
      noModuleScopeTimer:
        '{{ fn }} at module scope is unsafe in Cloudflare Workers — ' +
        'isolates may be evicted before the callback fires. Move inside a request handler.',
    },
  },
  create(context) {
    function isModuleScope(node) {
      let parent = node.parent;
      while (parent) {
        if (
          parent.type === 'FunctionDeclaration' ||
          parent.type === 'FunctionExpression'  ||
          parent.type === 'ArrowFunctionExpression'
        ) return false;
        parent = parent.parent;
      }
      return true;
    }

    return {
      CallExpression(node) {
        const callee = node.callee;
        const name =
          callee.type === 'Identifier' ? callee.name :
          callee.type === 'MemberExpression' && callee.property.type === 'Identifier'
            ? callee.property.name : null;

        if ((name === 'setTimeout' || name === 'setInterval') && isModuleScope(node)) {
          context.report({
            node,
            messageId: 'noModuleScopeTimer',
            data     : { fn: name },
          });
        }
      },
    };
  },
};

/** @type {import('eslint').Rule.RuleModule} */
const noProcessEnv = {
  meta: {
    type    : 'problem',
    docs    : { description: 'Disallow process.env in Workers — use Wrangler bindings/vars instead' },
    schema  : [],
    messages: { noProcessEnv: 'process.env is not available in the Workers runtime. Use env bindings.' },
  },
  create(context) {
    return {
      MemberExpression(node) {
        if (
          node.object.type === 'MemberExpression' &&
          node.object.object.type === 'Identifier' && node.object.object.name === 'process' &&
          node.object.property.type === 'Identifier' && node.object.property.name === 'env'
        ) {
          context.report({ node, messageId: 'noProcessEnv' });
        }
        if (
          node.object.type === 'Identifier' && node.object.name === 'process' &&
          node.property.type === 'Identifier' && node.property.name === 'env'
        ) {
          context.report({ node, messageId: 'noProcessEnv' });
        }
      },
    };
  },
};

/** @type {import('eslint').Rule.RuleModule} */
const noNodeBuiltins = {
  meta: {
    type    : 'suggestion',
    docs    : { description: 'Warn on Node.js built-in imports without nodejs_compat flag' },
    schema  : [],
    messages: {
      noNodeBuiltin:
        "'{{ mod }}' is a Node.js built-in. Add compatibility_flag = 'nodejs_compat' " +
        'or replace with a Web-platform alternative.',
    },
  },
  create(context) {
    const NODE_BUILTINS = new Set([
      'fs', 'path', 'os', 'child_process', 'net', 'tls', 'dns',
      'http', 'https', 'stream', 'buffer', 'zlib', 'events', 'util',
    ]);
    return {
      ImportDeclaration(node) {
        const src = node.source.value.replace(/^node:/, '');
        if (NODE_BUILTINS.has(src)) {
          context.report({ node, messageId: 'noNodeBuiltin', data: { mod: node.source.value } });
        }
      },
    };
  },
};

export default {
  rules: {
    'no-module-scope-timers': noModuleScopeTimers,
    'no-process-env'        : noProcessEnv,
    'no-node-builtins'      : noNodeBuiltins,
  },
};
```

---

## CI Integration

```yaml
# .github/workflows/lint.yml
name: Lint
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: ESLint (Workers compatibility)
        run: npm run lint -- --format=compact
        # Exit code 1 on any error rule violation; warnings are informational.

      - name: Annotate PR with lint findings
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const { execSync } = require('child_process');
            const output = execSync('npm run lint -- --format=json 2>&1 || true').toString();
            const results = JSON.parse(output);
            for (const file of results) {
              for (const msg of file.messages) {
                await github.rest.pulls.createReviewComment({
                  ...context.repo,
                  pull_number: context.issue.number,
                  commit_id  : context.payload.pull_request.head.sha,
                  path       : file.filePath.replace(process.cwd() + '/', ''),
                  line       : msg.line,
                  body       : `**ESLint [${msg.ruleId}]**: ${msg.message}`,
                });
              }
            }
```

---

## Anti-patterns

- **Writing custom rules as CommonJS in an ESM project** — ESLint 9 flat config expects ESM rule files; use `.js` with `"type": "module"` in `package.json` or name files `.mjs`.
- **Targeting `browsers: ['last 1 Chrome versions']` too aggressively** — Workers V8 version lags slightly behind Chrome stable; too strict a browser target produces false positives for APIs Workers does support.
- **Suppressing with `// eslint-disable`** — disabling `workers/no-module-scope-timers` inline papers over a real runtime risk; fix the code instead.
- **Not enabling `parserOptions.project`** — type-aware rules (`no-floating-promises`, `await-thenable`) require the TypeScript project reference; without it they silently do nothing.

---

## Gotchas

- ESLint flat config loads `eslint.config.ts` only when using the `--flag unstable_ts_config` flag in eslint < 9.9; use `eslint.config.js` compiled from TS, or pin to eslint ≥ 9.9 which supports `.ts` configs natively.
- The `no-unsupported-browser-features` plugin maps APIs to MDN compatibility data, which does not perfectly model the Workers runtime; treat its output as advisory.
- `@typescript-eslint/require-await` flags async functions with no `await` — useful for catching forgotten `await` in handlers but noisy in factory functions; adjust to `warn` or add targeted ignores.
- Custom local plugins must be imported (not just referenced by string) in flat config — the string-name lookup used in legacy `.eslintrc` does not work.

---

## Verification

```bash
# 1. Lint the source
npm run lint

# 2. Test the custom rules in isolation
node --input-type=module <<'EOF'
import { RuleTester } from 'eslint';
import plugin from './eslint-rules/workers.js';
const tester = new RuleTester({ languageOptions: { ecmaVersion: 2022 } });
tester.run('no-module-scope-timers', plugin.rules['no-module-scope-timers'], {
  valid  : ["export default { fetch() { setTimeout(() => {}, 0); } }"],
  invalid: [{ code: "setTimeout(() => {}, 1000);", errors: [{ messageId: 'noModuleScopeTimer' }] }],
});
console.log('Rule tests passed');
EOF

# 3. Confirm no floating-promise violations in handlers
npm run lint -- --rule '@typescript-eslint/no-floating-promises: error' src/
```

---

## Related

- `workers-multi-worker-local-dev-service-bindings.md`
- `workers-bundle-analysis-metafile-esbuild.md`

---

## Sources

- ESLint flat config migration guide — https://eslint.org/docs/latest/use/configure/migration-guide
- @typescript-eslint rules — https://typescript-eslint.io/rules/
- eslint-plugin-no-unsupported-browser-features — https://www.npmjs.com/package/eslint-plugin-no-unsupported-browser-features
- Cloudflare Workers runtime APIs — https://developers.cloudflare.com/workers/runtime-apis/
