# ESLint Workers no-floating-promises Rule

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker silently drops errors: a `ctx.waitUntil(someAsyncFn())` call
works fine, but an unawaited promise inside a route handler causes the Worker to
return a response before the async work finishes — and the error is swallowed. You
want ESLint to catch every floating promise at CI time so no one ships unhandled
async calls in production Workers.

---

## Context

The `@typescript-eslint/no-floating-promises` rule flags any Promise expression whose
result is neither `await`-ed, returned, nor explicitly handled with `.catch()`. In
Cloudflare Workers this is especially dangerous because:

1. The runtime terminates execution after `Response` is returned — unawaited work
   after the return is silently dropped.
2. `ctx.waitUntil()` extends the Worker's lifetime for background work, but only if
   the Promise is actually passed to it; an unawaited call beside it is ignored.
3. D1/KV/R2 methods are all async; a missing `await` produces stale data without a
   visible error.

The rule requires TypeScript type information (`parserOptions.project`), which is
standard in a `@cloudflare/workers-types`-typed project.

---

## Installation

```bash
pnpm add -D eslint @typescript-eslint/eslint-plugin @typescript-eslint/parser
```

---

## eslint.config.ts (flat config, ESLint 9)

```typescript
import tseslint from 'typescript-eslint'
import type { Linter } from 'eslint'

const config: Linter.Config[] = [
  // TypeScript parser with project-aware type checking
  ...tseslint.configs.recommendedTypeChecked,

  {
    languageOptions: {
      parserOptions: {
        project: true,           // auto-discovers tsconfig.json in the directory
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Core rule: no floating promises
      '@typescript-eslint/no-floating-promises': [
        'error',
        {
          ignoreVoid: true,      // allow `void somePromise()` as an explicit escape hatch
          ignoreIIFE: false,     // flag `(async () => { ... })()` unless awaited
        },
      ],

      // Companion rule: catches `.then()` chains without `.catch()`
      '@typescript-eslint/no-misused-promises': [
        'error',
        {
          checksVoidReturn: {
            arguments: true,     // catches passing async fn to non-async callback
            attributes: true,
          },
        },
      ],
    },
  },

  // Ignore generated files
  {
    ignores: ['dist/', '.wrangler/', '**/*.d.ts'],
  },
]

export default config
```

---

## Worker examples: what the rule catches

```typescript
// workers/api/src/index.ts
import type { Env } from './types'

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {

    // BAD: floating promise — KV write silently dropped if Worker exits fast
    // eslint error: Promises must be awaited, end with a call to .catch, or end with
    // a call to .then with a rejection handler.
    env.KV.put('last-hit', new Date().toISOString())

    // GOOD: awaited
    await env.KV.put('last-hit', new Date().toISOString())

    // GOOD: background via waitUntil
    ctx.waitUntil(env.KV.put('last-hit', new Date().toISOString()))

    // BAD: unawaited D1 write — response returns before insert completes
    env.DB.prepare('INSERT INTO hits (url) VALUES (?)').bind(request.url).run()

    // GOOD: awaited
    await env.DB.prepare('INSERT INTO hits (url) VALUES (?)').bind(request.url).run()

    // BAD: floating IIFE (ignoreIIFE: false catches this)
    ;(async () => {
      await env.DB.prepare('UPDATE stats SET count = count + 1').run()
    })()

    // GOOD: handed to waitUntil
    ctx.waitUntil(
      (async () => {
        await env.DB.prepare('UPDATE stats SET count = count + 1').run()
      })(),
    )

    return new Response('ok')
  },
}
```

---

## Escape hatch: explicit void

When you genuinely want fire-and-forget (not in a Worker exit path) you can silence
the rule with `void` — this is opt-in and searchable:

```typescript
// Deliberate fire-and-forget: telemetry that must not block the response
void sendTelemetry(request)   // explicit: "I know this is unawaited"
```

This is cleaner than a `// eslint-disable` comment because `void` is visible in
code review and caught by the `ignoreVoid: true` option.

---

## Custom rule: flag ctx.waitUntil without a Promise

If you want to also catch `ctx.waitUntil` called with a non-Promise value (a common
copy-paste mistake), add a lightweight custom rule:

```typescript
// eslint-rules/require-waituntil-promise.ts
import type { Rule } from 'eslint'

const rule: Rule.RuleModule = {
  meta: {
    type: 'problem',
    docs: { description: 'ctx.waitUntil must receive a Promise' },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        if (
          node.callee.type === 'MemberExpression' &&
          node.callee.property.type === 'Identifier' &&
          node.callee.property.name === 'waitUntil' &&
          node.arguments.length > 0
        ) {
          const arg = node.arguments[0]
          // Warn if the argument is not an AwaitExpression or a known async call
          if (arg.type === 'Literal' || arg.type === 'Identifier') {
            context.report({ node, message: 'ctx.waitUntil() should receive a Promise' })
          }
        }
      },
    }
  },
}

export default rule
```

Register in `eslint.config.ts`:

```typescript
import waitUntilRule from './eslint-rules/require-waituntil-promise'

// Inside the config array:
{
  plugins: { local: { rules: { 'require-waituntil-promise': waitUntilRule } } },
  rules:   { 'local/require-waituntil-promise': 'warn' },
}
```

---

## Anti-patterns

- **Disabling the rule project-wide** with `// eslint-disable @typescript-eslint/no-floating-promises` in a shared config — this hides the very bugs the rule exists to catch.
- **Using `ignoreVoid: false`** and then sprinkling `// eslint-disable-next-line`
  comments — `ignoreVoid: true` is the right escape hatch; it forces an explicit `void`
  keyword in the source instead of a comment that reviewers may miss.
- **Forgetting `no-misused-promises`** — it catches the complementary case where an
  async function is passed as a synchronous callback (e.g. to `Array.forEach`).
- **Running without `project: true`** — without type information `@typescript-eslint`
  cannot detect which expressions are Promises; the rule silently reports nothing.

---

## Gotchas

- `project: true` triggers a TypeScript program build on every `eslint` run. In a large
  monorepo this can be slow; mitigate with `TSPROJECT_CACHE=1` or by scoping the rule
  to `src/**` only.
- The rule does not fire on `Promise.all` / `Promise.allSettled` calls that are
  themselves not awaited — the outer call is still a floating promise even though the
  inner calls are collected. Wrap with `await Promise.all(...)`.
- Workers `Response` constructors are synchronous; only the *body reading* methods
  (`res.json()`, `res.text()`) return Promises and need awaiting.
- ESLint flat config uses `import.meta.dirname` which requires Node.js 20.11+. On
  older Node use `__dirname` (CJS) or `path.resolve()`.

---

## Verification

```bash
# Run ESLint with type checking enabled
pnpm eslint src/ --rule '{"@typescript-eslint/no-floating-promises": "error"}'

# Or via the project config
pnpm eslint src/

# Confirm the rule fires on a known-bad file
echo "export async function bad() { Promise.resolve() }" > /tmp/bad.ts
pnpm eslint --no-ignore /tmp/bad.ts
# Expected: 1 error — @typescript-eslint/no-floating-promises
```

---

## Related

- `eslint-v9-flat-config-cloudflare-workers.md`
- `eslint-concurrency-performance-governance.md`
- `eslint-no-eval-workers-security-rule.md`
- `typescript-cloudflare-workers-strict.md`

---

## Sources

- https://typescript-eslint.io/rules/no-floating-promises/
- https://typescript-eslint.io/rules/no-misused-promises/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://eslint.org/docs/latest/use/configure/configuration-files
