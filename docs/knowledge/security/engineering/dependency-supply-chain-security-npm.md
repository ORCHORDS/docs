# dependency-supply-chain-security-npm

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

`npm install` in CI silently resolves a different transitive version
than what was tested locally. `npm audit` reports 14 high-severity
vulnerabilities nobody has seen before. A newly published package
named `lodahs` appears in dependency graphs via a loose semver range.
The Workers deploy succeeds, but the bundled output contains a version
of a library that was never reviewed.

## Context

The npm ecosystem is shallow-trust by default: any registered account
can publish a new version, and semver ranges (`^`, `~`) make each
build only as stable as every upstream maintainer's account security.
Cloudflare Workers bundle dependencies at deploy time via
wrangler/esbuild — `node_modules` never reach the edge, so the threat
surface is the **build pipeline**. A compromised build-time package
can exfiltrate `CLOUDFLARE_API_TOKEN` via a `postinstall` script
before the Worker is deployed.

## Lockfile integrity — npm ci vs npm install

```bash
# CI must always use npm ci, never npm install
npm ci            # reads package-lock.json exactly
                  # fails if lockfile is out of sync
                  # never writes back to package-lock.json

pnpm install --frozen-lockfile   # pnpm equivalent
```

```yaml
# .github/workflows/ci.yml
- name: Install deps
  run: npm ci

- name: Audit production deps
  run: npm audit --audit-level=high --omit=dev
```

`npm install` silently updates the lockfile when ranges allow a newer
release; `npm ci` treats any lock mismatch as a hard failure.

## npm audit and pnpm audit

```bash
# Filter to high+critical, machine-readable
npm audit --json \
  | jq '.vulnerabilities | to_entries[]
        | select(.value.severity=="high"
                 or .value.severity=="critical") | .key'

pnpm audit --audit-level high --prod

npm audit fix           # safe fixes only
npm audit fix --force   # allows breaking changes — review diff first
```

## Dependabot vs Renovate

| Feature | Dependabot | Renovate |
|---|---|---|
| PR grouping | Yes (`groups:`) | Yes, more expressive |
| Auto-merge | GitHub native | Built-in config |
| Monorepo support | Basic | Excellent |
| Self-hosted | No | Yes |

```yaml
# .github/dependabot.yml — recommended minimum
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule: { interval: "weekly", day: "monday" }
    groups:
      minor-and-patch:
        update-types: ["minor", "patch"]
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "weekly" }
    groups:
      actions: { patterns: ["*"] }
```

## Package provenance and typosquatting detection

npm provenance (2023+) links a published package to the GitHub Actions
workflow that produced it, signed via Sigstore.

```bash
# Verify attestations on a package before adding it
npm info <package> dist.attestations
npm audit signatures      # check installed packages

# Socket Security CLI — free tier, scans the lockfile
npx @socketsecurity/cli report package-lock.json
```

**Pinning vs range strategy:**

| Strategy | Reproducibility | Maintenance |
|---|---|---|
| Exact pin `"1.2.3"` | Highest | High (manual bumps) |
| Patch range `"~1.2.3"` | Good | Medium |
| Minor range `"^1.2.3"` | Acceptable + Dependabot | Low |
| `"latest"` / `"*"` | None | Dangerous |

Pin exact versions for security-sensitive packages (`jsonwebtoken`,
`bcrypt`). Use `^` with Dependabot groups for utility packages.

## Anti-patterns

- Using `npm install` instead of `npm ci` in CI.
- Omitting `package-lock.json` from the repository.
- Running `npm audit fix --force` without reviewing the diff.
- Using `"*"` or `"latest"` as version specifiers.
- Installing packages with `postinstall` scripts without reading them.

## Gotchas

- **devDependencies inflate audit noise.** `npm audit` without
  `--omit=dev` reports on packages that never reach the Worker bundle.
- **postinstall scripts run at `npm ci` time.** Use
  `npm ci --ignore-scripts` in hardened CI, but verify builds pass.
- **Dependabot grouping.** Without `groups:`, Dependabot opens one
  PR per package update, producing 50+ weekly PRs on a large repo.
- **pnpm/npm lockfile mismatch.** Enforce a single package manager
  via `packageManager` in `package.json` and `.npmrc`.

## Verification

- `git log --oneline -- package-lock.json` — lockfile committed
  alongside every dependency change.
- `npm ci` in a clean checkout completes without modifying lockfile.
- `npm audit --audit-level=high --omit=dev` exits 0 in CI.
- `npx @socketsecurity/cli report package-lock.json` shows no
  high-confidence supply-chain flags.

## Related

- `security/supply-chain-npm-security.md`
- `security/slsa-supply-chain.md`
- `security/subresource-integrity-sri-cdn-assets.md`
- `security/container-image-scanning-hardening-signing.md`

## Source URLs (verified 2026-08-17)

- https://docs.npmjs.com/cli/v10/commands/npm-ci
- https://docs.npmjs.com/cli/v10/commands/npm-audit
- https://docs.npmjs.com/generating-provenance-statements
- https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-supply-chain-security
- https://socket.dev/
- https://renovatebot.com/docs/
