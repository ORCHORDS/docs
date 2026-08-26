# supply-chain-npm-security

**Issue:** npm supply chain security for edge deployments — lockfile integrity, audit, Dependabot, Workers bundle, pinning GitHub Actions
**Date:** 2026-08-11
**Status:** documented

## Symptom
A transitive dependency is compromised (event-stream 2018, ua-parser-js
2021, node-ipc 2022). `npm install` fetches a different version than
you tested. A GitHub Action runs arbitrary code from a mutable tag.
`npm audit` shows 12 high-severity vulnerabilities you've never seen.

## Root cause
**The npm ecosystem is shallow-trust by default.** Any published
package can be replaced by a malicious version via account takeover,
typosquatting, or dependency confusion. GitHub Actions tags are
mutable — `actions/checkout@v4` can point to different code after a
force-push.

**Source:** https://docs.npmjs.com/cli/v10/commands/npm-audit
https://docs.github.com/en/code-security/supply-chain-security/keeping-your-dependencies-updated-automatically/about-dependabot-version-updates

## What matters for Cloudflare Workers bundles

Workers bundles are built by `wrangler` at deploy time using esbuild.
**node_modules are never shipped to the edge** — only the bundled JS.
This changes the threat model:

| Risk | Traditional Node.js | Cloudflare Workers |
|---|---|---|
| Runtime postinstall scripts | High | Medium (runs at build time only) |
| Transitive dep compromise | High | High (bundled into worker) |
| Prototype pollution | High | Medium (no shared process between requests) |
| Dependency confusion | High | High (affects build) |
| `node_modules` at runtime | Yes | No |

The main attack surface for Workers is **build-time**: a malicious
package exfiltrates secrets via environment variables during
`npm install` or the build step.

## Lockfile integrity — always commit package-lock.json

```bash
# Never skip the lockfile
git add package-lock.json
git commit -m "chore: update lockfile"

# Use --frozen-lockfile in CI (fails if lockfile is out of sync)
npm ci  # not npm install
```

```yaml
# .github/workflows/deploy.yml
- name: Install dependencies
  run: npm ci  # uses package-lock.json exactly; fails if out of sync
```

`npm ci` differences from `npm install`:
- Requires `package-lock.json` to exist
- Fails if `package-lock.json` doesn't match `package.json`
- Always installs a fresh `node_modules`
- Never writes to `package-lock.json`

## Running npm audit

```bash
# Audit all dependencies
npm audit

# Audit only production deps (what's bundled into the Worker)
npm audit --omit=dev

# Machine-readable output for CI
npm audit --json | jq '.metadata.vulnerabilities'

# Auto-fix (safe upgrades only)
npm audit fix

# Fix including breaking changes (review carefully)
npm audit fix --force
```

In CI, fail the build on high/critical:
```yaml
- name: Audit dependencies
  run: npm audit --audit-level=high --omit=dev
```

## Dependabot configuration

```yaml
# .github/dependabot.yml
version: 2
updates:
  # npm dependencies
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Europe/Yerevan"
    open-pull-requests-limit: 10
    groups:
      # Group minor/patch updates to reduce PR noise
      minor-and-patch:
        update-types:
          - "minor"
          - "patch"
    ignore:
      # Pin major versions manually after review
      - dependency-name: "hono"
        update-types: ["version-update:semver-major"]
    labels:
      - "dependencies"
      - "automated"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      actions:
        patterns: ["*"]
```

## Pinning GitHub Actions to commit SHAs

Mutable tags (`@v4`) can be repointed by an attacker who compromises
the action's repository. Pin to the commit SHA that corresponds to the
version you audited.

```yaml
# ❌ Mutable — tag can be force-pushed
- uses: actions/checkout@v4

# ✅ Immutable — pinned to a specific commit
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

# How to get the SHA:
# 1. Go to https://github.com/actions/checkout/releases/tag/v4.2.2
# 2. Click the commit link next to the tag
# 3. Copy the full 40-char SHA
```

Automate SHA pinning with `pin-github-action`:
```bash
npx pin-github-action .github/workflows/deploy.yml
```

Or use Dependabot to update the pinned SHAs automatically (it handles
both tag and SHA updates when `package-ecosystem: github-actions` is
configured).

## Full CI workflow example

```yaml
name: Deploy to Cloudflare Workers
on:
  push:
    branches: [main]

permissions:
  contents: read  # least privilege

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - uses: actions/setup-node@39370e3970a6d050c480ffad4ff0ed4d3fdee5af  # v4.1.0
        with:
          node-version: "20"
          cache: "npm"

      - name: Install (frozen lockfile)
        run: npm ci

      - name: Audit production deps
        run: npm audit --audit-level=high --omit=dev

      - name: Type check
        run: npm run typecheck

      - name: Deploy
        uses: cloudflare/wrangler-action@392082e81ffbcb9a3526e5562e914e4d2d89a71e  # v3.14.0
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
        env:
          # Secrets are injected via wrangler.toml [vars] or wrangler secret
          NODE_ENV: production
```

## Detecting dependency confusion attacks

Dependency confusion: attacker publishes a public package with the same
name as your private package at a higher version. `npm install` picks
the public one.

```bash
# List private scopes in .npmrc
@orchords:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NPM_TOKEN}
```

Use a private registry scope (`@orchords/`) for all internal packages.
The scope forces npm to check the private registry first.

## Checking for typosquatting

```bash
# Socket Security (free tier): scans for supply chain issues
npx @socketsecurity/cli report package-lock.json

# Or use the GitHub App:
# https://socket.dev/
```

## Subresource Integrity for CDN assets

If example.com loads any third-party scripts (analytics, fonts) from a
CDN, add SRI hashes:

```html
<script
  src="https://cdn.example.com/lib.min.js"
  integrity="sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K/ux6fqSehcj8y7rB..."
  crossorigin="anonymous"
  nonce="...">
</script>
```

Generate the hash:
```bash
curl -s https://cdn.example.com/lib.min.js | openssl dgst -sha384 -binary | openssl base64 -A
```

## Verification
- `npm ci` in a clean checkout succeeds and lockfile is unchanged
- `npm audit --omit=dev` returns zero high/critical issues
- Merge a Dependabot PR; verify CI passes and Worker deploys cleanly
- Check `.github/workflows/*.yml` — all `uses:` lines should have
  `@<40-char-sha>  # v<version>` comments
- `cat .npmrc` — private scopes should be listed

## Gotchas
- **The "wrangler audit" gotcha.** `npm audit` checks the lockfile, not
  the bundle. A devDependency vulnerability shows up in audit but is not
  present in the Worker bundle. Use `--omit=dev` to focus on what ships.
- **The "postinstall script" gotcha.** Malicious packages run
  `postinstall` scripts during `npm install`, even in CI. Use
  `npm ci --ignore-scripts` for reproducibility — but test that your
  legitimate build still works (some packages need `postinstall`).
- **The "Dependabot grouping" gotcha.** Without `groups:`, Dependabot
  opens one PR per package update. This creates 50+ weekly PRs on a
  large repo. Always configure `groups:`.
- **The "SHA expiry" gotcha.** Pinned commit SHAs are permanent — but
  the GitHub repository could be deleted, force-pushed to (possible for
  non-protected branches), or the account could be compromised. Prefer
  actions from `actions/` or well-known organizations.
- **The "npm audit false positives" gotcha.** Audit sometimes flags
  vulnerabilities in packages that are only exploitable under
  conditions that don't apply to your Worker (e.g., server-side SSRF
  in a package you only use for date formatting). Use `npm audit --json`
  to inspect the vulnerability path before marking as low-priority.

## Related
- `security/slsa-supply-chain.md`
- `security/secrets-encryption-at-rest.md`
- `security/gitleaks-cloudflare-webhook.md`
- `cloudflare/workers-best-practices.md`
- npm audit docs: https://docs.npmjs.com/cli/v10/commands/npm-audit
- Dependabot: https://docs.github.com/en/code-security/supply-chain-security/keeping-your-dependencies-updated-automatically/about-dependabot-version-updates
- SLSA: https://slsa.dev/
- Socket Security: https://socket.dev/
- GitHub Actions pinning: https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions
