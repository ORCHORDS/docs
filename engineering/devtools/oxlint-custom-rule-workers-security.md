# oxlint Custom Rules for Cloudflare Workers Security Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers codebase has security patterns that stock oxlint rules
do not enforce — for example:

- Prevent direct `request.headers.get("Authorization")` without normalisation.
- Ban `eval()` and `new Function()` in Worker code.
- Require all `fetch()` calls to go through a typed wrapper that enforces
  allow-listed origins.
- Flag accidental logging of the raw `env` object (which contains secrets).

ESLint custom rules exist but oxlint (v0.x) does not support a plugin API
for custom JS rules. Instead, the approach is **oxlint for the broad ruleset +
a focused custom ESLint rule layer only for Workers-specific security rules**
using the hybrid setup described here.

---

## Context

oxlint is written in Rust and intentionally does not expose a JavaScript plugin
API — it trades extensibility for speed (~50–100× faster than ESLint). As of
mid-2026, custom rules must be written in Rust and contributed upstream, or the
team must maintain a minimal ESLint layer alongside oxlint.

The recommended hybrid architecture:

```
oxlint              → runs ~500 built-in rules at Rust speed
eslint (no-lint)    → runs only your custom Workers security rules
                      (all built-in ESLint rules disabled)
```

This keeps CI fast (oxlint handles the bulk) while preserving the ability to
ship custom enforcement logic in TypeScript/JavaScript.

---

## Repository Layout

```
workers-app/
├── .oxlintrc.json
├── eslint.config.mjs          ← custom-rules-only ESLint config
├── eslint-rules/
│   └── workers-security/
│       ├── index.mjs          ← rule plugin barrel
│       ├── no-raw-env-log.mjs
│       ├── no-eval-workers.mjs
│       └── require-fetch-wrapper.mjs
├── src/
└── package.json
```

---

## oxlint Configuration (.oxlintrc.json)

```json
{
  "$schema": "https://raw.githubusercontent.com/oxc-project/oxc/main/crates/oxc_linter/src/rules/config.schema.json",
  "rules": {
    "no-eval": "error",
    "no-new-func": "error",
    "no-console": "warn"
  },
  "ignore": ["dist/**", "*.d.ts"]
}
```

Delegate the broader security baseline to oxlint — `no-eval`, `no-new-func`,
and `no-console` are covered. Custom Workers-specific rules go into ESLint.

---

## Custom ESLint Plugin (Workers Security)

### Plugin barrel

```javascript
// eslint-rules/workers-security/index.mjs
import noRawEnvLog      from "./no-raw-env-log.mjs";
import noEvalWorkers    from "./no-eval-workers.mjs";
import requireFetchWrapper from "./require-fetch-wrapper.mjs";

export default {
  meta: { name: "workers-security", version: "1.0.0" },
  rules: {
    "no-raw-env-log":       noRawEnvLog,
    "no-eval-workers":      noEvalWorkers,
    "require-fetch-wrapper": requireFetchWrapper,
  },
};
```

### Rule: no-raw-env-log

Prevents `console.log(env)` or `console.error(env, ...)` — the env object
contains secrets like API keys and D1 credentials.

```javascript
// eslint-rules/workers-security/no-raw-env-log.mjs
/** @type {import("eslint").Rule.RuleModule} */
export default {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow logging the raw Workers env object (contains secrets)",
      category: "Security",
    },
    messages: {
      noRawEnv:
        "Do not log the env object directly — it contains secrets. " +
        "Log only the specific values you need.",
    },
    schema: [],
  },
  create(context) {
    return {
      CallExpression(node) {
        const { callee, arguments: args } = node;

        const isConsoleCall =
          callee.type === "MemberExpression" &&
          callee.object.type === "Identifier" &&
          callee.object.name === "console" &&
          callee.property.type === "Identifier" &&
          ["log", "warn", "error", "info", "debug"].includes(callee.property.name);

        if (!isConsoleCall) return;

        const logsEnv = args.some(
          (arg) => arg.type === "Identifier" && arg.name === "env"
        );

        if (logsEnv) {
          context.report({ node, messageId: "noRawEnv" });
        }
      },
    };
  },
};
```

### Rule: require-fetch-wrapper

Bans bare `fetch(url)` calls in Worker source — requires use of `apiFetch()`
which enforces allow-listed origins and adds auth headers.

```javascript
// eslint-rules/workers-security/require-fetch-wrapper.mjs
const ALLOWED_WRAPPERS = new Set(["apiFetch", "internalFetch", "cachedFetch"]);

/** @type {import("eslint").Rule.RuleModule} */
export default {
  meta: {
    type: "problem",
    docs: {
      description: "Require fetch() to be called through an approved wrapper",
    },
    messages: {
      useFetchWrapper:
        "Use an approved fetch wrapper (apiFetch, internalFetch, cachedFetch) " +
        "instead of bare fetch(). Wrappers enforce origin allow-lists and auth.",
    },
    schema: [
      {
        type: "object",
        properties: {
          allowedWrappers: { type: "array", items: { type: "string" } },
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const options = context.options[0] ?? {};
    const allowed = new Set([...ALLOWED_WRAPPERS, ...(options.allowedWrappers ?? [])]);

    return {
      CallExpression(node) {
        if (
          node.callee.type === "Identifier" &&
          node.callee.name === "fetch" &&
          !allowed.has(node.callee.name)
        ) {
          context.report({ node, messageId: "useFetchWrapper" });
        }
      },
    };
  },
};
```

---

## ESLint Config (Custom Rules Only)

```javascript
// eslint.config.mjs
import workersSecurityPlugin from "./eslint-rules/workers-security/index.mjs";

export default [
  {
    // Only run on Worker source files
    files: ["src/**/*.ts", "src/**/*.js"],
    plugins: { "workers-security": workersSecurityPlugin },
    rules: {
      // All built-in ESLint rules intentionally off — oxlint owns those
      "workers-security/no-raw-env-log":        "error",
      "workers-security/no-eval-workers":       "error",
      "workers-security/require-fetch-wrapper": ["error", {
        allowedWrappers: ["apiFetch"],
      }],
    },
  },
];
```

---

## package.json Scripts

```json
{
  "scripts": {
    "lint:fast":     "oxlint --config .oxlintrc.json src/",
    "lint:security": "eslint --no-warn-ignored src/",
    "lint":          "pnpm lint:fast && pnpm lint:security",
    "lint:ci":       "pnpm lint:fast --format github && pnpm lint:security --format github"
  },
  "devDependencies": {
    "oxlint":  "^0.16.0",
    "eslint":  "^9.0.0"
  }
}
```

---

## Testing Custom Rules

Use `eslint`'s built-in `RuleTester`:

```javascript
// eslint-rules/workers-security/__tests__/no-raw-env-log.test.mjs
import { RuleTester } from "eslint";
import rule from "../no-raw-env-log.mjs";

const tester = new RuleTester({
  languageOptions: { ecmaVersion: 2022, sourceType: "module" },
});

tester.run("no-raw-env-log", rule, {
  valid: [
    { code: `console.log(env.DB_URL)` },
    { code: `console.log("request received")` },
    { code: `logger.info({ event: "start" })` },
  ],
  invalid: [
    {
      code: `console.log(env)`,
      errors: [{ messageId: "noRawEnv" }],
    },
    {
      code: `console.error("context:", env)`,
      errors: [{ messageId: "noRawEnv" }],
    },
  ],
});

console.log("no-raw-env-log: all tests passed");
```

```bash
node eslint-rules/workers-security/__tests__/no-raw-env-log.test.mjs
```

---

## CI Integration (GitHub Actions)

```yaml
# .github/workflows/lint.yml
name: Lint
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile

      - name: oxlint (fast built-in rules)
        run: pnpm lint:fast --format github

      - name: ESLint (Workers security custom rules)
        run: pnpm lint:security --format github
```

---

## Anti-patterns

- **Writing oxlint custom rules in JavaScript.** oxlint does not have a JS
  plugin API. Attempts to load an ESLint plugin through oxlint configuration
  will be silently ignored or error.
- **Enabling all ESLint built-in rules alongside custom rules.** This defeats
  the purpose of the hybrid — run ESLint only for rules oxlint cannot provide.
- **Reporting on `callee.name` without checking `callee.type`.** If the callee
  is a member expression (`obj.fetch()`), `callee.name` is undefined. Always
  guard with `callee.type === "Identifier"`.
- **Skipping `RuleTester` unit tests.** Custom rules without tests drift
  silently as the codebase changes.

---

## Gotchas

- oxlint `--deny-warnings` is the equivalent of ESLint `--max-warnings 0`.
  Use it in CI to fail on warnings, not just errors.
- ESLint v9 flat config does not support `.eslintignore`. Use `ignores` inside
  the config array instead.
- `context.options[0]` is `undefined` when no options are passed; always
  default before destructuring.

---

## Verification

```bash
# Expect error on bare fetch()
echo 'fetch("https://evil.com/leak")' | npx eslint --stdin --stdin-filename src/test.js

# Expect pass
echo 'apiFetch("https://api.example.com/data")' | npx eslint --stdin --stdin-filename src/test.js

# Confirm oxlint catches no-eval
echo 'eval("1+1")' | oxlint --stdin-filename src/test.js -
```

---

## Related

- `oxlint-eslint-hybrid-workers-monorepo.md`
- `eslint-no-eval-workers-security-rule.md`
- `eslint-mcp-server-trust-boundary.md`
- `semgrep-custom-rules-ci-security.md`
- `biome-linter-formatter-cloudflare-workers.md`

---

## Sources

- https://oxc.rs/docs/guide/usage/linter.html
- https://eslint.org/docs/latest/extend/custom-rules
- https://eslint.org/docs/latest/use/configure/configuration-files
- https://github.com/oxc-project/oxc — oxlint source and planned plugin roadmap
- https://developers.cloudflare.com/workers/observability/logs/logpush/ (env logging risks)
