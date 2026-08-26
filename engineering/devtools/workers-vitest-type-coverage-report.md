# TypeScript Type Coverage Reporting for Cloudflare Workers with `type-coverage`

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers codebase grows and silently accumulates `any` types — especially in D1 query results, `env` bindings, and third-party SDK responses. Without a coverage gate in CI, type safety degrades incrementally and is only noticed when a runtime bug surfaces. You need a measurable, enforced threshold that blocks PRs when type coverage drops below an acceptable floor.

---

## Context

`type-coverage` (npm: `type-coverage`) is a CLI tool that walks your TypeScript project and counts what percentage of identifier nodes are typed (i.e., not `any` or `any`-equivalent). It integrates cleanly with `wrangler`-based Workers projects because it reads `tsconfig.json` directly — no bundler involvement needed. The `--detail` flag emits a per-file breakdown useful for PR comments. A threshold of **95 %** is a reasonable starting point for a Workers API service: D1 row types and `satisfies` bindings typically cover the remaining 5 % once properly annotated. GitHub Actions can capture the CLI output and post it as a PR comment using the `actions/github-script` action.

---

## Section 1 — tsconfig & package setup

```json
// tsconfig.json (relevant excerpt)
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  },
  "include": ["src/**/*.ts"]
}
```

```jsonc
// package.json (scripts excerpt)
{
  "scripts": {
    "type-coverage": "type-coverage --detail --strict --at-least 95",
    "type-coverage:json": "type-coverage --detail --strict --at-least 95 --output-json coverage/type-coverage.json"
  },
  "devDependencies": {
    "type-coverage": "^2.29.1"
  }
}
```

---

## Section 2 — Typing D1 results and env bindings

```typescript
// src/types/env.ts
export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  BUCKET: R2Bucket;
  API_KEY: string;
}

// Validate env shape at module load time — caught at type-check, not runtime
export type EnvCheck = typeof checkEnv;
declare const checkEnv: Env;

// src/db/queries.ts
import type { Env } from '../types/env';

export interface UserRow {
  id: number;
  email: string;
  created_at: string;
  is_active: number; // SQLite boolean
}

export async function getUserById(
  db: D1Database,
  id: number
): Promise<UserRow | null> {
  // Without the generic, .results is `Record<string, unknown>[]` → any territory
  const result = await db
    .prepare('SELECT id, email, created_at, is_active FROM users WHERE id = ?')
    .bind(id)
    .first<UserRow>();

  return result;
}

// src/worker.ts
import type { Env } from './types/env';
import { getUserById } from './db/queries';

// `satisfies` ensures the object literal matches Env without widening to Env
// This keeps individual property types narrow for type-coverage to count
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const idParam = url.searchParams.get('id');

    if (!idParam) {
      return new Response('Missing id', { status: 400 });
    }

    const id = parseInt(idParam, 10);
    if (Number.isNaN(id)) {
      return new Response('Invalid id', { status: 400 });
    }

    const user = await getUserById(env.DB, id);
    if (!user) {
      return new Response('Not found', { status: 404 });
    }

    return Response.json(user);
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — GitHub Actions integration

```yaml
# .github/workflows/type-coverage.yml
name: Type Coverage

on:
  pull_request:
    branches: [main]

jobs:
  type-coverage:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Run type-coverage
        id: coverage
        # Capture output; exit code non-zero if below threshold
        run: |
          set +e
          OUTPUT=$(npx type-coverage --detail --strict --at-least 95 2>&1)
          EXIT_CODE=$?
          echo "output<<EOF" >> $GITHUB_OUTPUT
          echo "$OUTPUT" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
          echo "exit_code=$EXIT_CODE" >> $GITHUB_OUTPUT
          exit $EXIT_CODE

      - name: Post coverage comment
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const output = `${{ steps.coverage.outputs.output }}`;
            const exitCode = '${{ steps.coverage.outputs.exit_code }}';
            const icon = exitCode === '0' ? '✅' : '❌';
            const body = [
              `## ${icon} Type Coverage Report`,
              '```',
              output,
              '```',
            ].join('\n');

            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
            });

            const existing = comments.find(c =>
              c.body?.startsWith('## ') && c.body.includes('Type Coverage Report')
            );

            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: existing.id,
                body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
                body,
              });
            }
```

---

## Anti-patterns

- **Casting to `any` to silence D1 results** — use `.first<RowType>()` or `.all<RowType>()` generics instead; each `as any` cast counts as an untyped node and lowers your score.
- **Placing `// @ts-ignore` on env binding access** — the `satisfies ExportedHandler<Env>` pattern eliminates the need; ignores are invisible to `type-coverage` but mask real type gaps.
- **Running `type-coverage` only on `src/` but shipping compiled files from `dist/`** — configure `include` in `tsconfig.json` to match exactly what Wrangler compiles; mismatches produce misleading coverage numbers.

---

## Gotchas

- `type-coverage` counts *identifier nodes*, not lines — a single `Promise<any>` return type penalises multiple call-site nodes that infer from it.
- `--strict` mode treats `unknown` as typed but `any` propagated through generics (e.g., `Array<any>`) as untyped — enable it to get accurate numbers.
- The `@cloudflare/workers-types` package ships `DurableObjectState` and some R2 types as `any` internally; pin `@cloudflare/workers-types@^4` which has improved generics.
- `type-coverage` does **not** run `tsc` — it uses the TypeScript compiler API. If your project has `tsc` errors, results may be inaccurate; always run `tsc --noEmit` first in CI.

---

## Verification

```bash
# Install
npm install --save-dev type-coverage

# One-shot check — exits 1 if below 95 %
npx type-coverage --detail --strict --at-least 95

# Emit machine-readable JSON
mkdir -p coverage
npx type-coverage --detail --strict --output-json coverage/type-coverage.json
cat coverage/type-coverage.json | jq '.percentage'

# Show only files with untyped nodes
npx type-coverage --detail --strict 2>&1 | grep -v '100%'
```

---

## Related

- `workers-typescript-path-aliases-wrangler.md`
- `wrangler-dev-remote-mode-staging.md`

---

## Sources

- type-coverage npm package — https://www.npmjs.com/package/type-coverage
- TypeScript `satisfies` operator — https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-9.html
- Cloudflare D1 TypeScript generics — https://developers.cloudflare.com/d1/worker-api/d1-database/
- actions/github-script — https://github.com/actions/github-script
