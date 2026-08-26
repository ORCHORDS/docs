# Biome — Unified Linter, Formatter, and Import Organizer

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your CI pipeline runs ESLint, Prettier, and an import sorter as three
separate steps taking 45 seconds total. Configuration lives across
`.eslintrc.json`, `.prettierrc`, `.prettierignore`, `.eslintignore`,
and an import-sort plugin config. A new developer joins and spends
an hour resolving conflicts between Prettier and ESLint formatting
rules. Meanwhile, your team debates whether to also adopt oxlint for
speed or deno lint for Deno projects — each tool adding another
config file and CI step.

## Context

Biome (biomejs.dev) is the Rust-based successor to the Rome toolchain,
forked after Rome's original maintainer stepped back in 2023. It
unifies linting, formatting, and import organization in a single
binary with a single config file (`biome.json`), positioned as a
drop-in replacement for the ESLint + Prettier combination. The current
stable line is v2.x with 500+ lint rules. Biome supports JavaScript,
TypeScript, JSX, TSX, JSON/JSONC, HTML, CSS, and GraphQL. Vue/Svelte/
Astro support is partial (embedded script blocks only, not full SFC
parsing). Published benchmarks claim ~35x faster than Prettier for
formatting and 50-100x faster than ESLint for linting.

## Configuration

```json
// biome.json — single file replaces .eslintrc + .prettierrc
{
  "$schema": "https://biomejs.dev/schemas/2.5.0/schema.json",
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 80
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "correctness": {
        "noUnusedVariables": "error"
      },
      "suspicious": {
        "noExplicitAny": "warn"
      }
    }
  },
  "organizeImports": {
    "enabled": true
  },
  "javascript": {
    "formatter": {
      "quoteStyle": "single",
      "semicolons": "always"
    }
  },
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true
  }
}
```

```
Biome subcommands:

  biome check           Run format + lint + imports (report only)
  biome check --write   Run format + lint + imports (auto-fix)
  biome format          Format only
  biome lint            Lint only
  biome ci              CI mode — fail on any diff (no writes)

  Single command replaces:
    prettier --check . && eslint . && import-sort --check
```

## Migration from ESLint and Prettier

```bash
# Migrate ESLint config to biome.json rules
biome migrate eslint --write

# Migrate Prettier config to biome.json formatter
biome migrate prettier --write
```

```
Migration capabilities:
  → Converts rule config (kebab-case → camelCase)
  → Maps plugin configs: typescript-eslint, jsx-a11y, react, unicorn
  → Handles flat config and legacy .eslintrc formats
  → Converts extends chains and overrides
  → Imports .eslintignore patterns

Limitations:
  → YAML ESLint configs not supported
  → "Inspired" rules need --include-inspired flag
  → Plugins with cyclic references can fail
  → Node.js required to resolve JS-based configs
  → JSON5/TOML/YAML Prettier configs not supported
  → Biome defaults differ (tabs vs spaces default)
```

## Comparison with alternatives

```
Tool          Speed vs ESLint  Formatting  Type-aware  Config
────────────────────────────────────────────────────────────────
Biome         50-100x faster   Built-in    Approximate biome.json
oxlint        ~2x faster       No          Full (tsgo) oxlintrc.json
                than Biome                  integration
deno lint     Similar to       No          No          deno.json
              Biome                        (Deno only)
ESLint        Baseline         No          Full (tsc)  eslint.config
              (slowest)        (Prettier)

Pick ESLint: plugin ecosystem breadth, type-aware rules
Pick Biome: single tool for lint + format, fastest combined
Pick oxlint: raw lint speed is the bottleneck, need type-aware
```

```
Type-aware linting:

  ESLint + typescript-eslint:
    → Full TypeScript compiler integration
    → 100% accuracy on type-dependent rules
    → Slower (runs tsc under the hood)

  Biome v2:
    → Lightweight type-inference engine
    → ~75% parity on floating-promise-style checks
    → Much faster (no full compiler invocation)
    → Accuracy tradeoffs on complex type gymnastics

  oxlint (2026):
    → Integrates with tsgo (Go port of tsc)
    → Full TypeScript-checker compatibility
    → ~2x faster than Biome for pure linting
```

## CI integration

```yaml
# GitHub Actions
- name: Biome CI check
  run: npx @biomejs/biome ci .

# Or with direct binary (faster, no npx overhead)
- name: Install Biome
  run: curl -fsSL https://biomejs.dev/install.sh | sh
- name: Biome CI check
  run: biome ci .
```

## Anti-patterns

- **Running ESLint and Biome on the same files** — rules overlap
  and conflict. Migrate fully or exclude file sets. Running both
  doubles CI time with no additional coverage.
- **Assuming Prettier output parity** — Biome claims ~97%
  compatibility with Prettier output but differences exist in
  edge cases. Run `biome format` and diff against Prettier output
  before switching to catch surprises.
- **Relying on Biome for full type-aware linting** — Biome's
  type inference is approximate (~75% parity). Projects needing
  strict floating-promise or type-conditional rules should keep
  typescript-eslint for those specific checks.
- **Ignoring per-language overrides** — Biome's defaults (tabs,
  double quotes) differ from common community conventions.
  Configure `javascript.formatter` explicitly during migration.

## Gotchas

- **Vue/Svelte SFC partial support** — Biome processes embedded
  `<script>` blocks but does not parse template syntax or style
  blocks. Full SFC linting still requires framework-specific tools.
- **`biome check --write` modifies files** — unlike `biome ci`
  (which only reports), `check --write` auto-fixes. Use `biome ci`
  in CI pipelines to avoid unintended modifications.
- **Migration does not delete old configs** — `biome migrate`
  creates `biome.json` but leaves `.eslintrc` and `.prettierrc`
  in place. Remove them manually to avoid confusion.
- **GraphQL and HTML support is newer** — rule coverage for these
  languages is less mature than JS/TS. Check the rule list before
  dropping dedicated GraphQL or HTML linters.

## Verification

- `biome.json` configured with formatter, linter, and import organizer.
- CI uses `biome ci` (not `biome check --write`) for fail-on-diff.
- Old ESLint and Prettier configs removed after migration.
- Per-language formatter overrides set to match team conventions.
- Type-aware rules validated against typescript-eslint output.
- VS Code extension installed and configured for format-on-save.

## Related

- `documentation/docs/policies/devtools/ai-code-review-tools-comparison.md`
- `documentation/docs/policies/worktree/git-hooks-husky-lint-staged-commitlint.md`
- `documentation/docs/policies/frontend/react-19-server-components-streaming-ssr.md`

## Source URLs (verified 2026-08-16)

- Migrate from ESLint and Prettier — Biome docs — https://biomejs.dev/guides/migrate-eslint-prettier/
- Biome Official Site — https://biomejs.dev/
- Benchmarking oxlint vs Biome — Peterbe.com — https://www.peterbe.com/plog/benchmarking-oxlint-vs-biome
- Biome vs Oxlint Comparison 2026 — https://jsmanifest.com/biome-oxlint-comparison-2026
