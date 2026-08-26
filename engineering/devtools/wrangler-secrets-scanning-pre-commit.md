# Wrangler Secrets Scanning Pre-Commit Hooks

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A developer accidentally commits a Cloudflare API token, a D1 connection string, or a
third-party API key that was temporarily pasted into `wrangler.toml`, `.dev.vars`, or a
source file during debugging. The secret appears in git history and must be rotated even
after the file is corrected, because git history preserves it.

The risk is especially high in Cloudflare Workers projects because `.dev.vars` (the local
equivalent of `wrangler secret put`) is frequently used to hold plaintext secrets during
development, and `wrangler.toml` sometimes contains real binding values (KV namespace IDs,
D1 database IDs, or accidentally inlined tokens) that should be treated as sensitive in
certain deployment contexts.

## Context

Cloudflare Workers projects have several files that are high-value targets for accidental
secret commits:

- `.dev.vars` — plaintext key=value secrets for local `wrangler dev`; must never be
  committed
- `wrangler.toml` — may contain real resource IDs or (rarely) inlined secret values
- `.env`, `.env.local`, `.env.production` — common Node.js env files used alongside Workers
- Source files (`src/**/*.ts`) — API keys hardcoded during debugging

Pre-commit hooks that scan for these patterns intercept secrets before they enter git
history, which is far cheaper than rotating credentials and rewriting history after the
fact. The hook strategy combines file-name blocking (for known high-risk filenames) with
content-pattern scanning (for token patterns).

## Baseline .gitignore Rules

Before adding hooks, ensure `.gitignore` blocks the most dangerous files:

```gitignore
# .gitignore

# Wrangler local secrets — NEVER commit
.dev.vars
.dev.vars.*

# Wrangler local state (contains persisted KV/D1/R2 data)
.wrangler/

# Generic env files
.env
.env.local
.env.*.local
*.env

# Secret rotation scripts that may contain tokens
scripts/rotate-secrets*.sh
```

`.gitignore` is the first line of defence. Pre-commit hooks are the second.

## gitleaks Configuration for Workers Projects

`gitleaks` is a purpose-built secret scanner that ships with a default ruleset covering
hundreds of common token patterns. It can be run as a pre-commit hook via the `pre-commit`
framework or directly via `lefthook`.

```toml
# .gitleaks.toml
title = "Workers Monorepo Secret Rules"

[extend]
# Inherit the official default ruleset
useDefault = true

[[rules]]
id = "cloudflare-api-token"
description = "Cloudflare API Token"
regex = '''(?i)(cloudflare[_\-]?(api[_\-]?)?token|CF_API_TOKEN)['":\s=]+([A-Za-z0-9_\-]{40})'''
tags = ["cloudflare", "api-token"]

[[rules]]
id = "wrangler-account-id"
description = "Cloudflare Account ID inlined as secret"
# Account IDs are not technically secret but often accompany real tokens
regex = '''(?i)account_id\s*=\s*["']?[0-9a-f]{32}["']?'''
tags = ["cloudflare", "low-severity"]
[rules.allowlist]
regexes = [
  # Allow the canonical wrangler.toml account_id field (no quotes, no env var)
  '^account_id = "[0-9a-f]{32}"$',
]

[[rules]]
id = "dev-vars-file"
description = "Blocks .dev.vars file from being committed"
path = '''(^|/)\.dev\.vars(\..+)?$'''
tags = ["cloudflare", "high-severity"]

[[rules]]
id = "hardcoded-jwt"
description = "Hardcoded JWT in source (common in Workers auth code)"
regex = '''eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}'''
tags = ["jwt", "high-severity"]
[rules.allowlist]
# Allow JWTs in test fixtures and mock data
paths = [
  '''test/''',
  '''__tests__/''',
  '''fixtures/''',
]

[allowlist]
# Allow common false positives
regexes = [
  # Placeholder values used in documentation/examples
  '''YOUR_API_TOKEN_HERE''',
  '''<YOUR_TOKEN>''',
  '''REPLACE_ME''',
]
paths = [
  '''CHANGELOG\.md''',
  '''\.md$''',
]
```

## lefthook Integration

`lefthook` is the preferred hook runner for Workers monorepos because it runs hooks in
parallel across workspace packages and has low overhead.

```yaml
# lefthook.yml
pre-commit:
  parallel: false   # secret scanning must be serial to avoid interleaved output
  commands:
    block-dev-vars:
      glob: "**/.dev.vars*"
      run: |
        echo "ERROR: .dev.vars file staged for commit. Remove it and add to .gitignore."
        exit 1

    gitleaks:
      run: gitleaks protect --staged --config .gitleaks.toml --verbose
      fail_text: |
        Secret detected in staged files.
        If this is a false positive, add an allowlist entry to .gitleaks.toml.
        NEVER commit real secrets. Rotate any exposed credentials immediately.

    check-wrangler-toml:
      glob: "**/wrangler.toml"
      run: node scripts/check-wrangler-toml.js {staged_files}
```

```typescript
// scripts/check-wrangler-toml.js
// Scans staged wrangler.toml files for patterns that should never be committed

import { readFileSync } from "node:fs";

const FORBIDDEN_PATTERNS: [RegExp, string][] = [
  [/\[vars\][\s\S]*?(?:TOKEN|SECRET|KEY|PASSWORD)\s*=\s*"[^"]{8,}"/i,
   "plaintext secret in [vars] section"],
  [/api_token\s*=\s*"[A-Za-z0-9_\-]{40}"/i,
   "Cloudflare API token inlined in wrangler.toml"],
  [/secret\s*=\s*"[^"]{8,}"/i,
   "generic secret value inlined in wrangler.toml"],
];

const files = process.argv.slice(2);
let found = false;

for (const file of files) {
  const content = readFileSync(file, "utf8");
  for (const [pattern, description] of FORBIDDEN_PATTERNS) {
    if (pattern.test(content)) {
      console.error(`BLOCKED: ${file} — ${description}`);
      found = true;
    }
  }
}

if (found) {
  console.error(
    "\nUse `wrangler secret put VAR_NAME` to store secrets in Cloudflare's secret store."
  );
  process.exit(1);
}
```

## pre-commit Framework Alternative

If the team uses the Python `pre-commit` framework:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks

  - repo: local
    hooks:
      - id: block-dev-vars
        name: Block .dev.vars commits
        language: script
        entry: scripts/block-dev-vars.sh
        pass_filenames: true
        types: [file]

      - id: check-wrangler-toml
        name: Scan wrangler.toml for secrets
        language: node
        entry: node scripts/check-wrangler-toml.js
        files: wrangler\.toml$
        pass_filenames: true
```

```bash
# scripts/block-dev-vars.sh
#!/usr/bin/env bash
set -e
for file in "$@"; do
  if [[ "$file" == *".dev.vars"* ]]; then
    echo "ERROR: Refusing to commit $file — contains local secrets."
    echo "Add .dev.vars to .gitignore and use 'wrangler secret put' for production."
    exit 1
  fi
done
```

## GitHub Actions Scan (Defence in Depth)

Pre-commit hooks can be bypassed with `git commit --no-verify`. Add a CI job as a second
layer that scans the full diff on every push and pull request:

```yaml
# .github/workflows/secret-scan.yml
name: Secret Scan
on:
  push:
    branches: ["*"]
  pull_request:

jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history for baseline comparison

      - name: Run gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_CONFIG: .gitleaks.toml
          GITLEAKS_ENABLE_COMMENTS: true   # posts PR comment on detection
```

## Anti-patterns

- Relying solely on `.gitignore` — files can be force-added with `git add -f`, bypassing
  `.gitignore`. Hooks provide an additional layer that catches this.
- Writing custom regex-only scanners without entropy checks — pattern matching alone misses
  randomly generated tokens that do not follow a known prefix convention.
- Using overly broad allowlists (e.g. allowlisting all `*.ts` files) — this defeats the
  purpose of content scanning in source files where most accidental leaks occur.
- Not rotating a secret after a detection — even a locally-detected secret in a developer's
  staged changes should be treated as potentially exposed if the developer uses a shared
  machine, cloud IDE, or copilot with repo access.
- Scanning only the HEAD commit in CI (`git diff HEAD~1`) — branch pushes that squash
  multiple commits will miss secrets introduced in intermediate commits; use `--all-commits`
  or `fetch-depth: 0` with baseline comparison.

## Gotchas

- `gitleaks protect --staged` scans only staged files (the git index), not the working
  tree. Files modified but not staged are not checked. Educate developers to run
  `git add` before expecting hook coverage.
- Wrangler generates `.wrangler/` directories with SQLite files containing binding state.
  These are not secrets but can be large; ensure `.wrangler/` is in `.gitignore`.
- `CLOUDFLARE_API_TOKEN` set as a shell export will appear in shell history
  (`~/.zsh_history`, `~/.bash_history`) but not in git. Remind developers to use
  `export CLOUDFLARE_API_TOKEN=$(cat ~/.cf-token)` to avoid inline token exposure.
- D1 database IDs and KV namespace IDs in `wrangler.toml` are not secrets (they are
  visible in the Cloudflare dashboard to anyone with account access) but should still be
  kept out of public repositories.

## Verification

```bash
# 1. Install gitleaks
brew install gitleaks  # macOS
# or: curl -sSfL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks-linux-amd64.tar.gz | tar xz

# 2. Stage a file containing a test token pattern
echo 'CF_API_TOKEN="AbCdEfGhIjKlMnOpQrStUvWxYz1234567890abcd"' > /tmp/leak-test.ts
git add /tmp/leak-test.ts 2>/dev/null || true

# 3. Run gitleaks against staged content
gitleaks protect --staged --config .gitleaks.toml --verbose
# Expected: exit code 1 and "cloudflare-api-token" rule reported

# 4. Verify .dev.vars is blocked
echo "MY_SECRET=hunter2" > .dev.vars
git add .dev.vars
# lefthook pre-commit should fire and block the commit

# 5. Confirm hook is installed
git commit --allow-empty -m "test hook"
# Should trigger the hook even for empty commits
```

## Related

- `wrangler-secret-bulk-import-script.md` — bulk-managing secrets via Cloudflare API
- `wrangler-secret-diff-ci-audit.md` — auditing secret drift between environments
- `lefthook-parallel-hooks-workers-ci.md` — lefthook configuration patterns
- `semgrep-custom-rules-ci-security.md` — complementary SAST scanning

## Sources

- gitleaks GitHub: https://github.com/gitleaks/gitleaks
- Cloudflare Docs: "Secrets" — https://developers.cloudflare.com/workers/configuration/secrets/
- OWASP: "Credential Stuffing Prevention" — https://owasp.org/www-community/attacks/Credential_stuffing
