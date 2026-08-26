# Custom ESLint Rule: Prevent `await` Inside Loops in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Workers have a strict CPU-time budget. Awaiting inside a `for` loop serialises subrequests that could be parallelised with `Promise.all`, often multiplying latency by the iteration count. A linter rule that flags this pattern at PR time prevents the anti-pattern from reaching production and teaches new contributors the correct idiom without code review friction.

---

## Context

ESLint's custom rule API exposes an AST visitor: you register handlers for node types and ESLint calls them as it walks the tree. An `AwaitExpression` nested inside a `ForStatement`, `WhileStatement`, or `ForOfStatement` is the pattern to detect. The rule should emit a suggestion (not an autofix, since the rewrite requires understanding the data dependencies) pointing to the `Promise.all` idiom. Vitest can drive rule tests using `RuleTester` from `eslint` — you get the same test ergonomics as the rest of your Workers test suite.

---

## Section 1 — Rule file and ESLint configuration

```jsonc
// .eslintrc.json
{
  "root": true,
  "parser": "@typescript-eslint/parser",
  "parserOptions": {
    "ecmaVersion": 2022,
    "sourceType": "module"
  },
  "plugins": ["@typescript-eslint", "local-rules"],
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended"
  ],
  "rules": {
    "local-rules/no-await-in-loop": "error"
  }
}
```

```json
// package.json (relevant devDependencies)
{
  "devDependencies": {
    "eslint": "^9.9.0",
    "@typescript-eslint/parser": "^8.3.0",
    "@typescript-eslint/eslint-plugin": "^8.3.0",
    "eslint-plugin-local-rules": "^2.0.1",
    "vitest": "^2.1.0"
  }
}
```

---

## Section 2 — Rule implementation

```typescript
// eslint-rules/no-await-in-loop.ts
import type { Rule } from 'eslint';

const LOOP_TYPES = new Set([
  'ForStatement',
  'ForInStatement',
  'ForOfStatement',
  'WhileStatement',
  'DoWhileStatement',
]);

/**
 * Walk up the ancestor chain to determine whether `node` is inside a loop
 * but NOT separated by a function boundary (arrow, function expression, etc.).
 */
function isInsideLoop(node: Rule.Node): boolean {
  let current: Rule.Node | null = node.parent ?? null;
  while (current) {
    if (LOOP_TYPES.has(current.type)) return true;
    // A function boundary means the await is in a nested async callback —
    // not a serial-subrequest issue at the current scope.
    if (
      current.type === 'FunctionDeclaration' ||
      current.type === 'FunctionExpression' ||
      current.type === 'ArrowFunctionExpression'
    ) {
      return false;
    }
    current = current.parent ?? null;
  }
  return false;
}

const rule: Rule.RuleModule = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Disallow await expressions inside loops — use Promise.all to parallelise subrequests.',
      category: 'Performance',
      recommended: true,
      url: 'https://developers.cloudflare.com/workers/learning/fetch-event-lifecycle/',
    },
    hasSuggestions: true,
    schema: [],
    messages: {
      noAwaitInLoop:
        'Avoid awaiting inside a loop. Collect promises and use Promise.all() to run subrequests in parallel.',
      suggestPromiseAll:
        'Refactor to collect values in an array and await Promise.all(array).',
    },
  },

  create(context) {
    return {
      AwaitExpression(node) {
        if (isInsideLoop(node as unknown as Rule.Node)) {
          context.report({
            node,
            messageId: 'noAwaitInLoop',
            suggest: [
              {
                messageId: 'suggestPromiseAll',
                fix(fixer) {
                  // Suggest only — a full fix requires data-flow analysis.
                  // We wrap the argument in Promise.all([...]) as a hint.
                  const awaitArg = context.getSourceCode().getText(
                    // @ts-expect-error — node.argument is AwaitExpression.argument
                    node.argument
                  );
                  return fixer.replaceText(
                    node,
                    `(await Promise.all([${awaitArg}]))[0]`
                  );
                },
              },
            ],
          });
        }
      },
    };
  },
};

export default rule;
```

```typescript
// eslint-rules/index.ts — plugin entry point consumed by eslint-plugin-local-rules
import noAwaitInLoop from './no-await-in-loop';

export const rules = {
  'no-await-in-loop': noAwaitInLoop,
};
```

---

## Section 3 — Vitest rule tests

```typescript
// eslint-rules/no-await-in-loop.test.ts
import { RuleTester } from 'eslint';
import { describe, it } from 'vitest';
import rule from './no-await-in-loop';

const tester = new RuleTester({
  parserOptions: { ecmaVersion: 2022, sourceType: 'module' },
});

describe('no-await-in-loop', () => {
  it('passes valid cases and flags invalid cases', () => {
    tester.run('no-await-in-loop', rule, {
      valid: [
        // Promise.all — correct pattern
        {
          code: `
            async function fetchAll(ids: string[]) {
              const results = await Promise.all(ids.map(id => fetch(id)));
              return results;
            }
          `,
        },
        // Await inside nested async function inside loop — different scope
        {
          code: `
            async function processItems(items: string[]) {
              for (const item of items) {
                const handler = async () => { await fetch(item); };
                handler();
              }
            }
          `,
        },
        // Await outside any loop
        {
          code: `
            async function fetchOne(url: string) {
              return await fetch(url);
            }
          `,
        },
      ],

      invalid: [
        // for...of loop
        {
          code: `
            async function fetchAll(urls: string[]) {
              const results = [];
              for (const url of urls) {
                results.push(await fetch(url));
              }
            }
          `,
          errors: [{ messageId: 'noAwaitInLoop' }],
        },
        // while loop
        {
          code: `
            async function poll() {
              let done = false;
              while (!done) {
                const res = await fetch('/status');
                done = res.ok;
              }
            }
          `,
          errors: [{ messageId: 'noAwaitInLoop' }],
        },
        // Classic for loop
        {
          code: `
            async function fetchSequential(ids: number[]) {
              for (let i = 0; i < ids.length; i++) {
                await fetch('/item/' + ids[i]);
              }
            }
          `,
          errors: [{ messageId: 'noAwaitInLoop' }],
        },
      ],
    });
  });
});
```

```bash
# Run just the rule tests
npx vitest run eslint-rules/

# Run ESLint over the worker source with the custom rule active
npx eslint src/ --ext .ts
```

---

## Anti-patterns

- **Using ESLint's built-in `no-await-in-loop`** — it fires on every await-in-loop including intentional retry logic; the custom rule lets you carve out exceptions (e.g., polling loops that must be serial).
- **Applying autofix blindly** — `Promise.all` requires that the iterations are independent; if iteration N depends on the result of iteration N-1 (e.g., cursor pagination), the serial pattern is correct and the rule should be suppressed with `// eslint-disable-next-line`.
- **Not running ESLint in CI** — the rule only helps if it runs automatically; add `npx eslint src/` to your PR check workflow.

---

## Gotchas

- `RuleTester` from `eslint` v9 uses flat config by default; if your project is still on `.eslintrc`, import `RuleTester` from `eslint/use-at-your-own-risk` or pin to eslint v8 for `RuleTester`.
- The `hasSuggestions: true` meta flag is required in ESLint v8.40+; without it, the suggestion is silently dropped.
- `eslint-plugin-local-rules` must be listed in `plugins` in `.eslintrc` **and** the rule referenced as `"local-rules/no-await-in-loop"`; the plugin name prefix is mandatory.
- If you use Flat Config (`eslint.config.js`), import your rules object directly and register under `plugins: { 'local-rules': { rules } }`.

---

## Verification

```bash
# Install dependencies
npm install --save-dev eslint eslint-plugin-local-rules @typescript-eslint/parser

# Lint source
npx eslint src/ --ext .ts --rule '{"local-rules/no-await-in-loop": "error"}'

# Run rule unit tests
npx vitest run eslint-rules/no-await-in-loop.test.ts

# Show all findings with context
npx eslint src/ --ext .ts --format codeframe
```

---

## Related

- `workers-vitest-type-coverage-report.md`
- `workers-typescript-path-aliases-wrangler.md`

---

## Sources

- ESLint custom rules guide — https://eslint.org/docs/latest/extend/custom-rules
- ESLint RuleTester — https://eslint.org/docs/latest/integrate/nodejs-api#ruletester
- Cloudflare Workers subrequest limits — https://developers.cloudflare.com/workers/platform/limits/#subrequests
- eslint-plugin-local-rules — https://www.npmjs.com/package/eslint-plugin-local-rules
