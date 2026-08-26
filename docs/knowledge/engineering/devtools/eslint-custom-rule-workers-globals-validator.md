# ESLint Custom Rule: Workers Globals Validator

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Developers accidentally reference Cloudflare Workers-only globals
(`caches`, `WebSocketPair`, `DurableObjectStorage`, `ScheduledEvent`,
`ExecutionContext`) inside shared library code that also runs in Node.js or
the browser. The bug surfaces only at runtime in the non-Workers environment.
Standard ESLint `no-undef` cannot distinguish "available in Workers but not
Node" from a genuinely undefined symbol when `@cloudflare/workers-types` is
installed project-wide.

---

## Context

Workers-specific globals are injected by `@cloudflare/workers-types`. In a
monorepo the types package is often installed at the root, making the globals
appear valid everywhere. A custom ESLint rule that checks the current file's
"environment context" — inferred from `wrangler.toml` proximity, filename
conventions, or an explicit pragma comment — can reject Workers-only references
in non-Worker files.

The rule runs in ESLint v9 flat-config format (`plugin:cloudflare-workers/*`).

---

## 1. Plugin Scaffold

```
packages/eslint-plugin-workers/
├── package.json
├── src/
│   ├── index.ts            # plugin entry
│   ├── rules/
│   │   └── no-workers-globals-in-shared.ts
│   └── utils/
│       ├── workers-globals.ts
│       └── is-workers-context.ts
└── tsconfig.json
```

```json
// packages/eslint-plugin-workers/package.json
{
  "name": "@org/eslint-plugin-workers",
  "version": "0.1.0",
  "main": "dist/index.js",
  "scripts": {
    "build": "tsup src/index.ts --format cjs --dts"
  },
  "peerDependencies": { "eslint": ">=9" },
  "devDependencies": { "eslint": "^9", "tsup": "^8", "typescript": "^5" }
}
```

---

## 2. Workers-Only Globals Registry

```typescript
// src/utils/workers-globals.ts

/** Globals that exist in the Workers runtime but NOT in Node.js or browsers. */
export const WORKERS_ONLY_GLOBALS = new Set([
  "caches",             // CacheStorage — different from browser Cache API
  "WebSocketPair",
  "DurableObjectStorage",
  "DurableObjectTransaction",
  "DurableObjectState",
  "ExecutionContext",
  "ScheduledEvent",
  "ScheduledController",
  "MessageEvent",       // Workers version has extra fields
  "TailEvent",
  "TraceEvent",
  "EmailMessage",
  "R2Bucket",
  "R2Object",
  "R2ObjectBody",
  "R2MultipartUpload",
  "KVNamespace",
  "Queue",
  "Fetcher",
  "D1Database",
  "D1PreparedStatement",
  "Vectorize",
  "Ai",
]);

/** Globals shared with browsers but with Workers-specific sub-types. */
export const WORKERS_EXTENDED_GLOBALS = new Set([
  "Request",   // Workers Request has extra properties like `.cf`
  "Response",  // Workers Response may differ
  "fetch",     // Workers fetch ignores HTTPS redirects differently
]);
```

---

## 3. Context Detector

```typescript
// src/utils/is-workers-context.ts
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";

/** Walk up from `filePath` looking for a wrangler.toml */
function hasWranglerConfig(filePath: string): boolean {
  let dir = dirname(filePath);
  for (let i = 0; i < 8; i++) {
    if (
      existsSync(join(dir, "wrangler.toml")) ||
      existsSync(join(dir, "wrangler.json")) ||
      existsSync(join(dir, "wrangler.jsonc"))
    ) {
      return true;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return false;
}

const WORKERS_PATH_RE = /\/(workers?|cloudflare|edge)\//i;
const SHARED_PATH_RE = /\/(shared|lib|utils|packages)\//i;

/** A file is considered "shared" (non-Worker) if it lives outside a known
 *  Workers source root. Override with `@workers-context: true` pragma. */
export function isWorkersOnlyContext(
  filePath: string,
  sourceCode: string
): boolean {
  // Pragma wins
  if (/\/\*\s*@workers-context:\s*true\s*\*\//.test(sourceCode)) return true;
  if (/\/\*\s*@workers-context:\s*false\s*\*\//.test(sourceCode)) return false;

  if (WORKERS_PATH_RE.test(filePath)) return true;
  if (SHARED_PATH_RE.test(filePath)) return false;

  return hasWranglerConfig(filePath);
}
```

---

## 4. The ESLint Rule

```typescript
// src/rules/no-workers-globals-in-shared.ts
import type { Rule } from "eslint";
import { WORKERS_ONLY_GLOBALS } from "../utils/workers-globals.js";
import { isWorkersOnlyContext } from "../utils/is-workers-context.js";

const rule: Rule.RuleModule = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Disallow Cloudflare Workers-only globals in shared/library code.",
      category: "Possible Errors",
      recommended: true,
      url: "https://github.com/org/eslint-plugin-workers/docs/no-workers-globals-in-shared.md",
    },
    schema: [
      {
        type: "object",
        properties: {
          additionalGlobals: { type: "array", items: { type: "string" } },
          allowInTests: { type: "boolean" },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      workerGlobalInShared:
        "'{{name}}' is a Cloudflare Workers-only global. " +
        "Do not reference it in shared code that runs outside Workers. " +
        "Move this to a Workers-specific module or inject it via dependency.",
    },
  },

  create(context) {
    const opts = (context.options[0] ?? {}) as {
      additionalGlobals?: string[];
      allowInTests?: boolean;
    };

    const filePath = context.physicalFilename ?? context.filename;
    const sourceCode = context.sourceCode.getText();

    // Skip files already in a Workers context
    if (isWorkersOnlyContext(filePath, sourceCode)) return {};

    // Skip test files if configured
    if (opts.allowInTests && /\.(test|spec)\.[tj]s$/.test(filePath)) return {};

    const blocklist = new Set([
      ...WORKERS_ONLY_GLOBALS,
      ...(opts.additionalGlobals ?? []),
    ]);

    return {
      Identifier(node) {
        if (!blocklist.has(node.name)) return;

        // Only flag top-level / global references, not property access targets
        const parent = node.parent;
        if (parent?.type === "MemberExpression" && parent.object !== node) {
          return; // e.g., `foo.R2Bucket` — fine
        }

        // Skip import/export declarations
        if (
          parent?.type === "ImportDefaultSpecifier" ||
          parent?.type === "ImportSpecifier" ||
          parent?.type === "ExportSpecifier"
        ) {
          return;
        }

        context.report({
          node,
          messageId: "workerGlobalInShared",
          data: { name: node.name },
        });
      },
    };
  },
};

export default rule;
```

---

## 5. Plugin Entry and Flat Config Registration

```typescript
// src/index.ts
import noWorkersGlobalsInShared from "./rules/no-workers-globals-in-shared.js";
import type { ESLint } from "eslint";

const plugin: ESLint.Plugin = {
  meta: { name: "@org/eslint-plugin-workers", version: "0.1.0" },
  rules: {
    "no-workers-globals-in-shared": noWorkersGlobalsInShared,
  },
  configs: {},
};

plugin.configs = {
  recommended: {
    plugins: { workers: plugin },
    rules: {
      "workers/no-workers-globals-in-shared": "error",
    },
  },
};

export default plugin;
```

```typescript
// eslint.config.ts (project root)
import workersPlugin from "@org/eslint-plugin-workers";

export default [
  workersPlugin.configs.recommended,
  {
    files: ["packages/shared/**/*.ts"],
    rules: {
      "workers/no-workers-globals-in-shared": [
        "error",
        { additionalGlobals: ["MY_CUSTOM_WORKERS_GLOBAL"], allowInTests: true },
      ],
    },
  },
];
```

---

## 6. Unit-Testing the Rule

```typescript
// src/rules/__tests__/no-workers-globals-in-shared.test.ts
import { RuleTester } from "eslint";
import rule from "../no-workers-globals-in-shared.js";

const tester = new RuleTester({
  languageOptions: { ecmaVersion: 2022, sourceType: "module" },
});

tester.run("no-workers-globals-in-shared", rule, {
  valid: [
    // In a Workers context via pragma
    {
      code: "/* @workers-context: true */ const c = caches.default;",
      filename: "/project/packages/shared/util.ts",
    },
    // Property access — not a bare global reference
    {
      code: "const x = env.KVNamespace;",
      filename: "/project/packages/shared/lib.ts",
    },
  ],
  invalid: [
    {
      code: "const store = new KVNamespace();",
      filename: "/project/packages/shared/storage.ts",
      errors: [{ messageId: "workerGlobalInShared", data: { name: "KVNamespace" } }],
    },
    {
      code: "await caches.open('v1');",
      filename: "/project/packages/shared/cache.ts",
      errors: [{ messageId: "workerGlobalInShared", data: { name: "caches" } }],
    },
  ],
});
```

---

## Anti-patterns

- **Relying solely on TypeScript to catch this** – TypeScript will not error
  when `@cloudflare/workers-types` is in `types[]` for the whole project; the
  ESLint rule provides an additional, file-granular enforcement layer.
- **Blacklisting all `Request`/`Response`** – These are also browser globals.
  Only add them to the list if you need to enforce Workers-specific subtype
  usage; keep `WORKERS_EXTENDED_GLOBALS` separate.
- **Walking the full AST for every identifier** – The rule visitor above only
  fires on `Identifier` nodes, which is already scoped. Avoid additional `scope`
  analysis unless you need to check whether a symbol was locally re-declared.

---

## Gotchas

- `context.physicalFilename` is available in ESLint 9+; fall back to
  `context.filename` for older versions.
- The pragma `/* @workers-context: false */` only works when placed at the top
  of the file before any code that could trigger the rule.
- Monorepo setups that use path aliases can produce virtual file paths; ensure
  the context detector uses `physicalFilename`, not the aliased path.

---

## Verification

```bash
# Lint the shared package and expect errors
pnpm eslint packages/shared/src --rule '{"workers/no-workers-globals-in-shared": "error"}'

# Run rule unit tests
vitest run src/rules/__tests__/
```

---

## Related

- `eslint-v9-flat-config-cloudflare-workers.md`
- `eslint-flat-config-migration-and-plugin-compatibility.md`
- `typescript-cloudflare-workers-strict.md`
- `oxlint-eslint-hybrid-workers-monorepo.md`

---

## Sources

- ESLint custom rules guide: https://eslint.org/docs/latest/extend/custom-rules
- ESLint RuleTester API: https://eslint.org/docs/latest/integrate/nodejs-api#ruletester
- Cloudflare Workers runtime APIs: https://developers.cloudflare.com/workers/runtime-apis/
- `@cloudflare/workers-types` package: https://www.npmjs.com/package/@cloudflare/workers-types
