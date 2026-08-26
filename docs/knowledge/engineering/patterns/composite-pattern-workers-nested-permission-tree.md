# Composite Pattern — Workers Nested Permission Tree

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A multi-tenant SaaS has permissions that nest: an organisation grants a team access to
a resource, the team grants an individual override, and a superuser role collapses the
whole tree to `allow`. Encoding this as a flat RBAC table makes inheritance impossible;
encoding it with recursive SQL queries is expensive per-request. You need a structure
you can evaluate in memory after a single KV or D1 read, where both individual rules
and rule groups answer the same `check(action, subject)` question.

## Context

The Composite pattern lets you compose objects into tree structures and treat individual
objects and compositions uniformly. In a Worker this maps naturally: a `LeafPermission`
checks one `(action, subject)` pair; a `CompositePermission` holds children and
delegates — all of them (`AND`), any of them (`OR`), or an ordered priority chain
(`FIRST`). The entire tree is a plain JSON value stored in KV; the Worker deserialises
it once per request and evaluates in microseconds with no additional I/O.

## Node Interface

```typescript
// permission/types.ts
export type Effect = 'allow' | 'deny' | 'abstain';

export interface PermissionNode {
  /** Evaluate whether `actor` may perform `action` on `resource`. */
  check(action: string, resource: string, actor: string): Effect;
}
```

## Leaf Node

Matches specific action/resource patterns. Supports `*` wildcards.

```typescript
// permission/leaf.ts
import type { PermissionNode, Effect } from './types';

export interface LeafConfig {
  kind: 'leaf';
  effect: 'allow' | 'deny';
  action: string;    // exact or "*"
  resource: string;  // exact or "prefix:*"
  actors?: string[]; // optional actor whitelist; absent = applies to all
}

function matches(pattern: string, value: string): boolean {
  if (pattern === '*') return true;
  if (pattern.endsWith(':*')) {
    return value.startsWith(pattern.slice(0, -1));
  }
  return pattern === value;
}

export class LeafPermission implements PermissionNode {
  constructor(private readonly cfg: LeafConfig) {}

  check(action: string, resource: string, actor: string): Effect {
    if (!matches(this.cfg.action, action)) return 'abstain';
    if (!matches(this.cfg.resource, resource)) return 'abstain';
    if (this.cfg.actors && !this.cfg.actors.includes(actor)) return 'abstain';
    return this.cfg.effect;
  }
}
```

## Composite Nodes

Three composition strategies cover most real-world policies.

```typescript
// permission/composite.ts
import type { PermissionNode, Effect } from './types';

/** All children must allow; any deny short-circuits to deny. */
export class AndPermission implements PermissionNode {
  constructor(private readonly children: PermissionNode[]) {}

  check(action: string, resource: string, actor: string): Effect {
    let anyAllow = false;
    for (const child of this.children) {
      const e = child.check(action, resource, actor);
      if (e === 'deny') return 'deny';
      if (e === 'allow') anyAllow = true;
    }
    return anyAllow ? 'allow' : 'abstain';
  }
}

/** Any child allowing is sufficient; deny wins over allow if both present. */
export class OrPermission implements PermissionNode {
  constructor(private readonly children: PermissionNode[]) {}

  check(action: string, resource: string, actor: string): Effect {
    let anyAllow = false;
    for (const child of this.children) {
      const e = child.check(action, resource, actor);
      if (e === 'deny') return 'deny';
      if (e === 'allow') anyAllow = true;
    }
    return anyAllow ? 'allow' : 'abstain';
  }
}

/** Evaluate children in order; first non-abstain result wins. */
export class FirstMatchPermission implements PermissionNode {
  constructor(private readonly children: PermissionNode[]) {}

  check(action: string, resource: string, actor: string): Effect {
    for (const child of this.children) {
      const e = child.check(action, resource, actor);
      if (e !== 'abstain') return e;
    }
    return 'abstain';
  }
}
```

## Tree Deserialisation

Stored as JSON in KV; each node carries a `kind` discriminant.

```typescript
// permission/deserialise.ts
import type { PermissionNode } from './types';
import { LeafPermission, type LeafConfig } from './leaf';
import { AndPermission, OrPermission, FirstMatchPermission } from './composite';

interface AndNode  { kind: 'and';   children: AnyNode[] }
interface OrNode   { kind: 'or';    children: AnyNode[] }
interface FirstNode{ kind: 'first'; children: AnyNode[] }
type AnyNode = LeafConfig | AndNode | OrNode | FirstNode;

export function deserialise(raw: AnyNode): PermissionNode {
  if (raw.kind === 'leaf')  return new LeafPermission(raw);
  const children = raw.children.map(deserialise);
  if (raw.kind === 'and')   return new AndPermission(children);
  if (raw.kind === 'or')    return new OrPermission(children);
  if (raw.kind === 'first') return new FirstMatchPermission(children);
  throw new Error(`Unknown node kind: ${(raw as AnyNode).kind}`);
}
```

## Worker Integration

```typescript
// worker.ts
import { deserialise } from './permission/deserialise';

export interface Env {
  PERMISSIONS: KVNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url      = new URL(req.url);
    const tenantId = req.headers.get('x-tenant-id') ?? 'default';
    const actorId  = req.headers.get('x-actor-id')  ?? '';
    const action   = req.headers.get('x-action')    ?? '';
    const resource = url.pathname;

    const raw = await env.PERMISSIONS.get(`policy:${tenantId}`, 'json');
    if (!raw) return new Response('No policy', { status: 404 });

    const tree = deserialise(raw as any);
    const effect = tree.check(action, resource, actorId);

    if (effect !== 'allow') {
      return new Response('Forbidden', { status: 403 });
    }
    return new Response('OK');
  },
};
```

## Example Policy Stored in KV (`policy:acme`)

```json
{
  "kind": "first",
  "children": [
    {
      "kind": "leaf",
      "effect": "allow",
      "action": "*",
      "resource": "*",
      "actors": ["superuser@acme.com"]
    },
    {
      "kind": "or",
      "children": [
        { "kind": "leaf", "effect": "allow", "action": "read",  "resource": "docs:*" },
        { "kind": "leaf", "effect": "allow", "action": "write", "resource": "docs:*",
          "actors": ["editor@acme.com"] },
        { "kind": "leaf", "effect": "deny",  "action": "delete","resource": "docs:*" }
      ]
    }
  ]
}
```

## Anti-patterns

- **Returning boolean from `check`** — A boolean loses the `abstain` state, which is
  essential when a node doesn't match at all vs. explicitly denying. Keep three-valued
  logic throughout.
- **Storing policies per-user** — Put policies on the tenant or role, not on individual
  actors. Actors are just strings matched inside leaf nodes; per-actor KV keys don't
  scale.
- **Unbounded tree depth** — Add a `maxDepth` guard in `deserialise` to reject trees
  deeper than 10 levels; a crafted policy could cause deep recursion.

## Gotchas

- `FirstMatchPermission` is order-sensitive. Put superuser overrides first in the
  children array, not last.
- KV consistency is eventual. A permission change made in the admin panel may take up
  to 60 s to propagate. For security-critical writes use `cache: 'no-store'` KV reads
  or move to D1 with `consistent: true`.
- The `abstain` return means "this node has no opinion." The caller (the Worker) must
  decide the default effect when the root node abstains — fail closed with `403`.

## Verification

```typescript
import { deserialise } from './permission/deserialise';

const policy = deserialise({
  kind: 'or',
  children: [
    { kind: 'leaf', effect: 'allow', action: 'read', resource: 'docs:*' },
    { kind: 'leaf', effect: 'deny',  action: 'write', resource: 'docs:*' },
  ],
});

console.assert(policy.check('read',  'docs:guide', 'alice') === 'allow');
console.assert(policy.check('write', 'docs:guide', 'alice') === 'deny');
console.assert(policy.check('delete','docs:guide', 'alice') === 'abstain');
```

## Related

- `role-based-access-control.md` — flat RBAC as a starting point
- `feature-cookbook-permission-modeling-detail.md` — permission modelling strategies
- `specification-pattern-d1-query-building.md` — composable predicates in query context

## Sources

- GoF *Design Patterns* (1994) — Composite, pp. 163–173
- OWASP Access Control Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html
- Cloudflare KV consistency: https://developers.cloudflare.com/kv/reference/consistency/
