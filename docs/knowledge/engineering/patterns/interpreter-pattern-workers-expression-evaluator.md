# Interpreter Pattern — Workers Expression Evaluator

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to evaluate user-defined rules at runtime — routing conditions, access-control
expressions, feature-flag criteria, or pricing formulas — without deploying new code.
Hard-coded `if/else` chains can't keep up; pushing arbitrary JS to `eval()` is a security
disaster. The Interpreter pattern turns a small, well-scoped grammar into safe, testable
objects that run inside a Worker with no eval, no cold-start penalty, and no external
process.

## Context

A Cloudflare Worker sits in front of every request. It's the ideal place to evaluate
lightweight rule expressions — "is this user in the 'beta' group AND their plan is
'pro'?" — before forwarding, blocking, or enriching the request. The grammar is small
enough to parse inline; the evaluation tree is just TypeScript objects that the V8
isolate handles cheaply. KV or D1 stores the serialised expression; the Worker
deserialises and evaluates it per-request with zero network round-trips.

## Grammar Design

Keep the grammar small and safe. A good starting set:
- Literals: strings, numbers, booleans
- Identifiers: paths into a context object (`user.plan`, `geo.country`)
- Comparison operators: `eq`, `neq`, `gt`, `lt`, `gte`, `lte`, `contains`
- Logical combinators: `and`, `or`, `not`

```typescript
// types.ts
export type Literal = { kind: 'literal'; value: string | number | boolean };
export type Identifier = { kind: 'identifier'; path: string };
export type Comparison = {
  kind: 'comparison';
  op: 'eq' | 'neq' | 'gt' | 'lt' | 'gte' | 'lte' | 'contains';
  left: Expr;
  right: Expr;
};
export type Logical = {
  kind: 'and' | 'or';
  operands: Expr[];
};
export type Not = { kind: 'not'; operand: Expr };

export type Expr = Literal | Identifier | Comparison | Logical | Not;

// Evaluation context: a flat or nested object the rule reads from
export type Context = Record<string, unknown>;
```

## Expression Nodes as Interpreter Classes

Each node type is a class that knows how to evaluate itself.

```typescript
// interpreter.ts
import type { Expr, Context } from './types';

function resolve(path: string, ctx: Context): unknown {
  return path.split('.').reduce<unknown>((acc, key) => {
    if (acc !== null && typeof acc === 'object') {
      return (acc as Record<string, unknown>)[key];
    }
    return undefined;
  }, ctx);
}

export function evaluate(expr: Expr, ctx: Context): boolean | number | string {
  switch (expr.kind) {
    case 'literal':
      return expr.value;

    case 'identifier':
      return resolve(expr.path, ctx) as boolean | number | string;

    case 'comparison': {
      const l = evaluate(expr.left, ctx);
      const r = evaluate(expr.right, ctx);
      switch (expr.op) {
        case 'eq':  return l === r;
        case 'neq': return l !== r;
        case 'gt':  return (l as number) > (r as number);
        case 'lt':  return (l as number) < (r as number);
        case 'gte': return (l as number) >= (r as number);
        case 'lte': return (l as number) <= (r as number);
        case 'contains':
          return typeof l === 'string' && l.includes(String(r));
      }
    }

    case 'and':
      return expr.operands.every(op => evaluate(op, ctx) === true);

    case 'or':
      return expr.operands.some(op => evaluate(op, ctx) === true);

    case 'not':
      return !evaluate(expr.operand, ctx);
  }
}
```

## Storing and Loading Expressions

Expressions are JSON-serialisable trees. Store them in KV keyed by rule ID.

```typescript
// rule-store.ts
import type { Expr } from './types';

export async function loadRule(
  kv: KVNamespace,
  ruleId: string,
): Promise<Expr | null> {
  const raw = await kv.get(ruleId, 'json');
  return raw as Expr | null;
}

export async function saveRule(
  kv: KVNamespace,
  ruleId: string,
  expr: Expr,
): Promise<void> {
  await kv.put(ruleId, JSON.stringify(expr));
}
```

## Worker Entry Point

Build the context from the incoming request, load the rule, evaluate, branch.

```typescript
// worker.ts
import { evaluate } from './interpreter';
import { loadRule } from './rule-store';

export interface Env {
  RULES: KVNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const ruleId = url.searchParams.get('rule') ?? 'default';

    const expr = await loadRule(env.RULES, ruleId);
    if (!expr) {
      return new Response('Rule not found', { status: 404 });
    }

    // Build context from request data
    const ctx = {
      geo:  { country: req.cf?.country ?? 'XX' },
      user: { plan: req.headers.get('x-plan') ?? 'free' },
      path: url.pathname,
    };

    const result = evaluate(expr, ctx);
    if (result === true) {
      return Response.redirect('https://app.example.com' + url.pathname, 302);
    }
    return new Response('Access denied', { status: 403 });
  },
};
```

## Example Rule (stored in KV)

```json
{
  "kind": "and",
  "operands": [
    { "kind": "comparison", "op": "eq",
      "left":  { "kind": "identifier", "path": "user.plan" },
      "right": { "kind": "literal",    "value": "pro" } },
    { "kind": "comparison", "op": "neq",
      "left":  { "kind": "identifier", "path": "geo.country" },
      "right": { "kind": "literal",    "value": "CN" } }
  ]
}
```

## Anti-patterns

- **Embedding arbitrary JS strings** — `eval()` and `new Function()` are banned in
  Workers. Don't try to work around this; use the tree-based interpreter instead.
- **Unbounded recursion** — Without a depth cap, a malicious stored expression could
  blow the call stack. Add a depth counter to `evaluate` and throw after ~50 levels.
- **Fat contexts** — Passing hundreds of keys into the context makes auditing hard.
  Keep contexts shallow and document which paths are available in the grammar.

## Gotchas

- `req.cf` is typed as `IncomingRequestCfProperties | undefined` in recent type
  packages; always guard with `?? 'XX'` or similar.
- KV reads add ~1–5 ms of latency. Cache the parsed expression in the module scope
  with a short TTL if the same rule is evaluated on every request.
- The `evaluate` function returns `boolean | number | string`. Use strict `=== true`
  comparisons in routing logic to avoid truthiness surprises with strings.

## Verification

```typescript
import { evaluate } from './interpreter';

const rule = {
  kind: 'and' as const,
  operands: [
    { kind: 'comparison' as const, op: 'eq' as const,
      left:  { kind: 'identifier' as const, path: 'user.plan' },
      right: { kind: 'literal'    as const, value: 'pro' } },
  ],
};

console.assert(evaluate(rule, { user: { plan: 'pro' } }) === true);
console.assert(evaluate(rule, { user: { plan: 'free' } }) === false);
```

Run with `wrangler dev` and hit `?rule=<id>` with test headers to validate live rules
against real request context.

## Related

- `strategy-pattern-workers-kv.md` — switching evaluation strategies per tenant
- `specification-pattern-d1-query-building.md` — similar composable predicate approach
- `feature-flags-implementations.md` — storing and toggling runtime rules

## Sources

- GoF *Design Patterns* (1994) — Interpreter, pp. 243–255
- Cloudflare Workers runtime limits: https://developers.cloudflare.com/workers/platform/limits/
- KV read performance: https://developers.cloudflare.com/kv/reference/how-kv-works/
