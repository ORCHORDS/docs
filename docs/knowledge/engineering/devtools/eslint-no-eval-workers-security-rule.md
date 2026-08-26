# ESLint `no-eval` Security Rule for Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A security audit flags `eval()` or `new Function()` usage in a Cloudflare Workers codebase.
Because the Workers runtime does not support `eval()` — it throws at runtime regardless —
catching it at lint time is both a security control and a DX improvement that surfaces the
bug before deployment.

The built-in ESLint `no-eval` rule covers `eval()` but misses several related patterns that
Workers developers commonly introduce:

- `new Function("return " + code)()`
- `setTimeout("someCode()", 0)` (string-form setTimeout)
- `setInterval("someCode()", 0)`
- Dynamic `import()` with a non-literal specifier (a distinct security concern)
- `globalThis.eval()` (bypasses the standard `no-eval` check)
- Indirect eval via destructured `const { eval: e } = globalThis`

This article shows how to configure the built-in rules and write a custom ESLint rule plugin
that catches all Workers-relevant eval-equivalent patterns.

---

## Context

Cloudflare Workers run in V8 isolates with dynamic code evaluation disabled by default.
Attempting `eval("1+1")` at runtime throws:
```
EvalError: Code generation from strings disallowed for this context
```

This is a security boundary enforced by the V8 `--disallow-code-generation-from-strings`
flag. Sentry, Datadog, and other third-party SDKs bundled into Workers have historically
smuggled in eval paths that only fail at runtime. Catching them at lint time prevents silent
broken deployments.

ESLint's built-in `no-eval` (from `@typescript-eslint` or core) handles the obvious case.
The custom rule in this article adds coverage for the remaining patterns.

---

## Step 1 — Enable Built-in Rules

```typescript
// eslint.config.ts (flat config)
import tseslint from "typescript-eslint";
import js from "@eslint/js";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.ts", "src/**/*.tsx"],
    rules: {
      // Core eval prevention
      "no-eval": ["error", { allowIndirect: false }],
      // new Function() and string-form timers
      "no-new-func": "error",
      // Forbids string first arg to setTimeout/setInterval
      "no-implied-eval": "error",
      // Script injection via script element (not relevant in Workers but catches copy-paste)
      "no-script-url": "error",
    },
  }
);
```

---

## Step 2 — Custom Rule: `workers/no-dynamic-code-eval`

The custom rule extends coverage to `globalThis.eval`, destructured eval aliases, and
`new Function` called via a variable.

```typescript
// eslint-plugins/workers/rules/no-dynamic-code-eval.ts
import type { Rule } from "eslint";

const rule: Rule.RuleModule = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Disallow eval() and equivalent dynamic code generation in Cloudflare Workers",
      recommended: true,
    },
    schema: [],
    messages: {
      evalCall:
        "eval() is forbidden in Cloudflare Workers — the runtime throws EvalError at execution.",
      newFunctionCall:
        "new Function() is forbidden in Cloudflare Workers — the runtime throws EvalError at execution.",
      globalThisEval:
        "globalThis.eval() is forbidden in Cloudflare Workers.",
      stringTimerArg:
        "Passing a string to setTimeout/setInterval is equivalent to eval() and is forbidden.",
    },
  },

  create(context) {
    return {
      // Direct eval("...")
      'CallExpression[callee.name="eval"]'(node) {
        context.report({ node, messageId: "evalCall" });
      },

      // globalThis.eval("...")
      'CallExpression[callee.type="MemberExpression"]'(node: Rule.Node) {
        const callNode = node as any;
        const callee = callNode.callee;
        if (
          callee.type === "MemberExpression" &&
          callee.property.type === "Identifier" &&
          callee.property.name === "eval" &&
          callee.object.type === "Identifier" &&
          (callee.object.name === "globalThis" || callee.object.name === "global")
        ) {
          context.report({ node, messageId: "globalThisEval" });
        }
      },

      // new Function(...)
      'NewExpression[callee.name="Function"]'(node) {
        context.report({ node, messageId: "newFunctionCall" });
      },

      // setTimeout("code", delay) and setInterval("code", delay)
      'CallExpression[callee.name=/^(setTimeout|setInterval)$/]'(node: Rule.Node) {
        const callNode = node as any;
        const firstArg = callNode.arguments[0];
        if (firstArg && firstArg.type === "Literal" && typeof firstArg.value === "string") {
          context.report({ node, messageId: "stringTimerArg" });
        }
      },
    };
  },
};

export default rule;
```

---

## Step 3 — Plugin Entry Point

```typescript
// eslint-plugins/workers/index.ts
import noDynamicCodeEval from "./rules/no-dynamic-code-eval";

export const plugin = {
  meta: {
    name: "workers",
    version: "1.0.0",
  },
  rules: {
    "no-dynamic-code-eval": noDynamicCodeEval,
  },
};

export default plugin;
```

```typescript
// eslint.config.ts (updated)
import tseslint from "typescript-eslint";
import js from "@eslint/js";
import workersPlugin from "./eslint-plugins/workers/index";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    plugins: {
      workers: workersPlugin,
    },
    files: ["src/**/*.ts"],
    rules: {
      "no-eval": ["error", { allowIndirect: false }],
      "no-new-func": "error",
      "no-implied-eval": "error",
      // Custom rule covering globalThis.eval and additional patterns
      "workers/no-dynamic-code-eval": "error",
    },
  }
);
```

---

## Step 4 — Rule Unit Tests with `RuleTester`

```typescript
// eslint-plugins/workers/rules/__tests__/no-dynamic-code-eval.test.ts
import { RuleTester } from "eslint";
import rule from "../no-dynamic-code-eval";

const tester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
  },
});

tester.run("workers/no-dynamic-code-eval", rule, {
  valid: [
    // Normal function calls are fine
    { code: "console.log('hello')" },
    // Arrow function in setTimeout is fine
    { code: "setTimeout(() => doWork(), 100)" },
    // Template literals in setTimeout args that are functions
    { code: "setInterval(function handler() { doWork(); }, 500)" },
  ],
  invalid: [
    {
      code: "eval('1 + 1')",
      errors: [{ messageId: "evalCall" }],
    },
    {
      code: "globalThis.eval('danger')",
      errors: [{ messageId: "globalThisEval" }],
    },
    {
      code: "new Function('return 42')()",
      errors: [{ messageId: "newFunctionCall" }],
    },
    {
      code: "setTimeout('doSomething()', 1000)",
      errors: [{ messageId: "stringTimerArg" }],
    },
    {
      code: "setInterval('poll()', 5000)",
      errors: [{ messageId: "stringTimerArg" }],
    },
  ],
});
```

---

## Step 5 — CI Enforcement

```yaml
# .github/workflows/lint.yml
- name: Lint Workers source
  run: pnpm eslint src/ --max-warnings=0
```

The `--max-warnings=0` flag treats any warning as a pipeline failure.
All `workers/no-dynamic-code-eval` violations are configured as `"error"` (not `"warn"`),
so they block the pipeline regardless.

---

## Step 6 — Detecting Eval in Third-Party Bundles

ESLint only checks source files, not node_modules. To audit bundled third-party code for
eval before deployment, add a bundle-scan step using `grep` or `ripgrep` on the Wrangler
output:

```bash
# scripts/check-bundle-eval.sh
set -euo pipefail

BUNDLE="dist/worker.js"

if grep -Pn '\beval\s*\(' "$BUNDLE"; then
  echo "ERROR: eval() found in bundle output — check third-party dependencies"
  exit 1
fi

if grep -Pn '\bnew\s+Function\s*\(' "$BUNDLE"; then
  echo "ERROR: new Function() found in bundle output"
  exit 1
fi

echo "Bundle eval scan passed."
```

```yaml
# .github/workflows/deploy.yml
- name: Build Worker
  run: pnpm wrangler deploy --dry-run --outdir dist

- name: Scan bundle for eval
  run: bash scripts/check-bundle-eval.sh
```

---

## Anti-patterns

**Using `allowIndirect: true` in `no-eval`:**
```jsonc
// BAD — allows (0, eval)("code") which is indirect eval and still dangerous
"no-eval": ["error", { "allowIndirect": true }]

// GOOD
"no-eval": ["error", { "allowIndirect": false }]
```

**Suppressing the rule at the use site without a tracked exception:**
```typescript
// BAD — silently hides a real Workers incompatibility
// eslint-disable-next-line workers/no-dynamic-code-eval
const result = eval(code);

// GOOD — if you genuinely need a suppression, document why and track it
// eslint-disable-next-line workers/no-dynamic-code-eval -- TODO: replace with static dispatch #1234
```

**Only linting `src/` and not `test/`:**
Test files that use `eval()` for mocking or dynamic fixture generation can mask the pattern
in developers' muscle memory. Lint test files too and use `vitest.fn()` / `vi.spyOn()`
instead.

---

## Gotchas

- The built-in `no-new-func` rule from ESLint core covers `new Function(...)` but does not
  detect `const F = Function; new F(...)`. The custom rule above only covers the direct
  `new Function()` form; variable aliasing of `Function` is an advanced evasion case.
- Workers `compatibility_flags` can enable the `nodejs_compat` flag which exposes a
  limited `vm` module, but `vm.runInNewContext()` still fails at runtime. Extend the
  custom rule to flag `vm.runInNewContext`, `vm.runInThisContext`, and `vm.Script` if
  `nodejs_compat` is enabled in your project.
- `RuleTester` from `eslint` v9 requires `languageOptions` instead of `parserOptions`.
  The test example above uses the correct v9 API.
- If your project uses `@typescript-eslint/parser`, the AST node shapes are identical for
  these patterns — no separate TypeScript-specific selectors are needed.
- Biome has a `suspicious/noEval` rule as well. If your project uses Biome for formatting
  and ESLint for linting, ensure both are enabled to avoid gaps when one tool is skipped.

---

## Verification

```bash
# Verify the rule fires on a known-bad fixture
echo "eval('1')" > /tmp/eval-test.ts
pnpm eslint /tmp/eval-test.ts --rule '{"no-eval": "error"}' --no-eslintrc

# Run the full rule test suite
pnpm vitest run eslint-plugins/

# Lint the production source with zero-warning threshold
pnpm eslint src/ --max-warnings=0

# Scan the built bundle
pnpm wrangler deploy --dry-run --outdir dist && bash scripts/check-bundle-eval.sh
```

---

## Related

- `eslint-v9-flat-config-cloudflare-workers.md`
- `eslint-custom-rule-workers-globals-validator.md`
- `eslint-mcp-server-trust-boundary.md`
- `semgrep-custom-rules-ci-security.md`
- `esbuild-workers-plugins-custom-transforms.md`

---

## Sources

- ESLint `no-eval` rule docs: https://eslint.org/docs/latest/rules/no-eval
- ESLint `no-new-func` rule docs: https://eslint.org/docs/latest/rules/no-new-func
- ESLint `no-implied-eval` rule docs: https://eslint.org/docs/latest/rules/no-implied-eval
- Cloudflare Workers security model (isolate sandboxing): https://developers.cloudflare.com/workers/reference/security-model/
- ESLint custom rule guide: https://eslint.org/docs/latest/extend/custom-rules
- V8 `--disallow-code-generation-from-strings` flag: https://v8.dev/docs/embed#code-evaluation
