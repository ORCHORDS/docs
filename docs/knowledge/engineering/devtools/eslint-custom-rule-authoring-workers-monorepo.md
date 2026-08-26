# Writing Custom ESLint Rules for a Cloudflare Workers Monorepo

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers monorepo accumulates `console.log` calls that bypass the structured logging pipeline, and developers forget to `await` `ctx.waitUntil()` — causing silent promise abandonment at the edge. Off-the-shelf ESLint plugins do not encode these project-specific invariants.

## Context

ESLint's flat config (introduced in v9, the default in eslint ≥ 9.x) lets you register a local object as a plugin without publishing it to npm. `@typescript-eslint/utils` provides type-safe AST helpers and `RuleCreator` so you get autocomplete on node properties and a standard `meta` shape that ESLint's rule tester understands.

We author two rules:
1. `no-console-log` — bans `console.log` in favour of `logger.info / logger.warn / logger.error`.
2. `require-await-ctx-wait-until` — enforces `await ctx.waitUntil(…)` so the runtime does not silently drop the promise.

## Rule Implementations

```typescript
// tools/eslint-rules/index.ts
import { ESLintUtils } from '@typescript-eslint/utils';

const createRule = ESLintUtils.RuleCreator(
  (name) => `https://example.com/kb/devtools/eslint-custom-rules#${name}`
);

// ── Rule 1: no-console-log ────────────────────────────────────────────────
export const noConsoleLog = createRule({
  name: 'no-console-log',
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Disallow console.log in Workers; use the structured logger instead.',
    },
    messages: {
      noConsoleLog:
        'Use logger.info/warn/error instead of console.log. ' +
        'console.log is unstructured and hard to query in Tail Workers.',
    },
    schema: [], // no options
  },
  defaultOptions: [],
  create(context) {
    return {
      CallExpression(node) {
        const { callee } = node;
        if (
          callee.type === 'MemberExpression' &&
          callee.object.type === 'Identifier' &&
          callee.object.name === 'console' &&
          callee.property.type === 'Identifier' &&
          callee.property.name === 'log'
        ) {
          context.report({ node, messageId: 'noConsoleLog' });
        }
      },
    };
  },
});

// ── Rule 2: require-await-ctx-wait-until ─────────────────────────────────
export const requireAwaitCtxWaitUntil = createRule({
  name: 'require-await-ctx-wait-until',
  meta: {
    type: 'problem',
    docs: {
      description:
        'Require await before ctx.waitUntil() so the promise is not dropped.',
    },
    messages: {
      missingAwait:
        'ctx.waitUntil() must be awaited. ' +
        'Without await the Workers runtime may terminate before the promise settles.',
    },
    schema: [],
  },
  defaultOptions: [],
  create(context) {
    return {
      CallExpression(node) {
        const { callee, parent } = node;
        const isWaitUntil =
          callee.type === 'MemberExpression' &&
          callee.property.type === 'Identifier' &&
          callee.property.name === 'waitUntil' &&
          callee.object.type === 'Identifier' &&
          callee.object.name === 'ctx';

        if (isWaitUntil && parent?.type !== 'AwaitExpression') {
          context.report({ node, messageId: 'missingAwait' });
        }
      },
    };
  },
});

// ── Plugin barrel ─────────────────────────────────────────────────────────
export const localPlugin = {
  rules: {
    'no-console-log': noConsoleLog,
    'require-await-ctx-wait-until': requireAwaitCtxWaitUntil,
  },
};
```

## Wiring Into `eslint.config.mjs`

```javascript
// eslint.config.mjs (repo root — flat config)
import tseslint from 'typescript-eslint';
import { localPlugin } from './tools/eslint-rules/index.ts';

export default tseslint.config(
  {
    plugins: {
      local: localPlugin,  // namespace for all local rules
    },
    rules: {
      'local/no-console-log': 'error',
      'local/require-await-ctx-wait-until': 'error',
    },
    // Apply only to Worker source, not to scripts or config files
    files: ['packages/*/src/**/*.ts', 'workers/*/src/**/*.ts'],
  },
  // Disable the rule in test files where console.log is acceptable
  {
    files: ['**/*.test.ts', '**/*.spec.ts'],
    rules: { 'local/no-console-log': 'off' },
  }
);
```

## Testing with `RuleTester`

```typescript
// tools/eslint-rules/__tests__/rules.test.ts
import { RuleTester } from '@typescript-eslint/rule-tester';
import { noConsoleLog, requireAwaitCtxWaitUntil } from '../index';

const tester = new RuleTester({
  languageOptions: { parser: require('@typescript-eslint/parser') },
});

tester.run('no-console-log', noConsoleLog, {
  valid: [
    { code: 'logger.info("hello")' },
    { code: 'console.error("this is fine")' },
  ],
  invalid: [
    {
      code: 'console.log("bad")',
      errors: [{ messageId: 'noConsoleLog' }],
    },
  ],
});

tester.run('require-await-ctx-wait-until', requireAwaitCtxWaitUntil, {
  valid: [
    { code: 'await ctx.waitUntil(fetch(url))' },
  ],
  invalid: [
    {
      code: 'ctx.waitUntil(fetch(url))',
      errors: [{ messageId: 'missingAwait' }],
    },
  ],
});
```

## `meta.type` Values and When to Use Them

| `meta.type` | Meaning | Example |
|---|---|---|
| `"problem"` | Code is likely wrong / will cause a bug | Missing `await` |
| `"suggestion"` | Better practice exists but code works | Replace `console.log` |
| `"layout"` | Whitespace / formatting only | Indentation |

Choose `"problem"` for rules that correlate with runtime failures (like the `waitUntil` rule) so they surface at error severity by default.

## Anti-patterns

- **Writing rules against the AST node type alone** — always check parent context to avoid false positives (e.g., a method named `waitUntil` on a non-`ctx` object).
- **Not using `RuleCreator`** — raw rule objects lose the `docs.url` link, making it hard for developers to find the rationale.
- **Publishing the local plugin to npm** — local plugins live in `tools/` and are imported directly; publishing forces version management for internal rules.
- **Using `context.getSourceCode()` (deprecated)** — use `context.sourceCode` in ESLint ≥ 8.40.

## Gotchas

- `@typescript-eslint/utils` re-exports `@typescript-eslint/parser` types; you still need `@typescript-eslint/parser` in `devDependencies` for the `languageOptions.parser` reference in `RuleTester`.
- In a pnpm monorepo with `shamefully-hoist=false`, `tools/eslint-rules` must be a proper workspace package (`"name": "@example-org/example-repo"`) so ESLint can resolve the import.
- The `parent` property on AST nodes is set by ESLint's traversal and is not present in the raw parser output — never rely on it before the `CallExpression` visitor fires.

## Verification

```bash
# Run ESLint across all Worker packages
pnpm eslint packages/*/src --max-warnings 0

# Run only the local rule tests
pnpm vitest run tools/eslint-rules/__tests__

# Print the rule list to confirm registration
npx eslint --print-config packages/api-worker/src/index.ts \
  | jq '.rules | with_entries(select(.key | startswith("local/")))'
```

## Related

- `vitest-coverage-thresholds-ci-enforcement-workers.md`
- `typescript-declaration-merging-workers-env-types.md`
- [ESLint custom rules guide](https://eslint.org/docs/developer-guide/working-with-rules)

## Sources

- `@typescript-eslint/utils` RuleCreator — https://typescript-eslint.io/packages/utils/#rulecreator
- ESLint flat config — https://eslint.org/docs/latest/use/configure/configuration-files-new
- ESLint AST node reference — https://eslint.org/docs/latest/extend/custom-rules
