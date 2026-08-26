# Dependency Audit, pnpm Overrides for Transitive Vulnerabilities, and SBOM Policy

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Automated security scanners flag transitive dependency vulnerabilities in the monorepo
that the direct-dependency maintainer has not yet patched. CI pipelines stall because
`pnpm audit` exits non-zero on moderate-severity CVEs in deeply nested packages that
cannot be updated by bumping a direct dependency version.

## Context

example project (example.com) runs `pnpm audit` as a required CI gate. Because the monorepo
installs hundreds of transitive dependencies across the Next.js app and the Cloudflare
Worker bundle, the surface area for known CVEs is significant. The team uses a layered
policy:

1. **Audit gate**: CI fails on `high` or `critical` severity CVEs.
2. **Override mechanism**: `pnpm.overrides` in the root `package.json` pins a safe
   version of a transitive package when an upstream maintainer has not released a patch.
3. **SBOM generation**: a Software Bill of Materials is generated on every release for
   supply-chain compliance.
4. **Minimum release age**: new direct dependencies must be at least 7 days old before
   merging (covered in `pnpm-minimum-release-age-supply-chain-delay.md`).

Key tool versions:

| Tool    | Version  |
|---------|----------|
| pnpm    | 9.x      |
| Node.js | 20 LTS   |
| syft    | 1.x (SBOM) |
| grype   | 0.x (CVE scan) |

## pnpm audit Severity Levels

| Level    | CVSS score | example project policy  |
|----------|-----------|--------------|
| critical | 9.0–10.0  | Block merge  |
| high     | 7.0–8.9   | Block merge  |
| moderate | 4.0–6.9   | Warn in CI, track in issue |
| low      | 0.1–3.9   | Informational |
| info     | 0.0       | No action    |

## Running pnpm audit

```bash
# Audit the entire workspace
pnpm audit

# Only show high and critical
pnpm audit --audit-level high

# JSON output for parsing
pnpm audit --json > audit-results.json

# Audit only production dependencies (exclude devDependencies)
pnpm audit --prod

# Audit a single workspace package
pnpm --filter @example project/worker audit
```

## CI Gate (GitHub Actions)

```yaml
# .github/workflows/security.yml
name: Security audit

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "0 6 * * 1"   # Weekly Monday 06:00 UTC

permissions:
  contents: read
  security-events: write   # for uploading SARIF to GitHub Security tab

jobs:
  audit:
    name: pnpm audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Audit high and critical CVEs
        run: pnpm audit --audit-level high
        # Exits 1 if any high/critical found → fails the job

      - name: Audit moderate (warn only)
        run: pnpm audit --audit-level moderate || true
        # || true prevents job failure on moderate-only findings
```

The weekly schedule catches newly published CVEs against the existing lockfile even
when no code has changed.

## pnpm.overrides for Transitive Patches

`pnpm.overrides` in the root `package.json` forces a specific version of a transitive
dependency across the entire dependency tree. It is the pnpm equivalent of npm's
`overrides` or Yarn's `resolutions`.

### Syntax

```json
// package.json (workspace root)
{
  "pnpm": {
    "overrides": {
      "semver": "^7.6.0",
      "tough-cookie": "^4.1.3",
      "ws": "^8.17.1",
      "axios": "^1.7.4",
      "braces": "^3.0.3"
    }
  }
}
```

After adding or changing an override, regenerate the lockfile:

```bash
pnpm install
pnpm audit --audit-level high
# Should now exit 0 if the override resolved the CVE
```

### Scoped overrides

To override a package only when required by a specific parent:

```json
{
  "pnpm": {
    "overrides": {
      "some-parent>vulnerable-dep": "^2.0.1"
    }
  }
}
```

This pins `vulnerable-dep` to `^2.0.1` only when it appears as a dependency of
`some-parent`, leaving other consumers unaffected.

### Override lifecycle

| Stage | Action |
|-------|--------|
| CVE published | Add override, verify `pnpm audit` passes |
| Upstream patch released | Bump direct dep, remove override |
| Override lingering > 90 days | Create issue to reassess |

Track every override with a comment and a linked CVE reference:

```json
{
  "pnpm": {
    "overrides": {
      // CVE-2024-28863: tar path traversal — remove when @isaacs/tar releases >=7.1.0
      "tar": "^6.2.1"
    }
  }
}
```

JSON does not support comments. Use a companion `SECURITY_OVERRIDES.md` in the repo
root to document the rationale.

### SECURITY_OVERRIDES.md format

```markdown
| Package | Override version | CVE          | Added      | Upstream fix ETA |
|---------|------------------|--------------|------------|-----------------|
| tar     | ^6.2.1           | CVE-2024-28863 | 2026-08-22 | tar >=7.1.0     |
| ws      | ^8.17.1          | CVE-2024-37890 | 2026-07-01 | ws >=8.17.1 (done) |
```

## SBOM Generation

A Software Bill of Materials records every dependency at a point-in-time snapshot. example project
generates a CycloneDX JSON SBOM on every release.

### Tool: syft

```bash
# Install syft (single binary)
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

# Generate SBOM for the workspace node_modules
syft dir:. -o cyclonedx-json=sbom.cdx.json

# Generate SBOM for the Worker bundle specifically
syft file:packages/worker/dist/index.js -o cyclonedx-json=worker-sbom.cdx.json
```

### SBOM in CI

```yaml
  sbom:
    name: Generate SBOM
    runs-on: ubuntu-latest
    needs: [audit]   # only run if audit passes
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Install syft
        run: |
          curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh \
            | sh -s -- -b /usr/local/bin

      - name: Generate SBOM
        run: syft dir:. -o cyclonedx-json=sbom.cdx.json

      - name: Upload SBOM artifact
        uses: actions/upload-artifact@v4
        with:
          name: sbom-${{ github.sha }}
          path: sbom.cdx.json
          retention-days: 90

      - name: Attach SBOM to GitHub Release
        if: github.event_name == 'release'
        run: |
          gh release upload ${{ github.ref_name }} sbom.cdx.json
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### CVE scan against SBOM (grype)

```bash
# Install grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

# Scan SBOM for CVEs
grype sbom:sbom.cdx.json --fail-on high
```

This is a belt-and-suspenders check: `pnpm audit` uses npm's advisory database while
grype uses the NVD / GitHub Advisory Database, catching different CVE subsets.

## Supply-Chain Policy Summary

```
┌────────────────────────────────────────────────────────────┐
│              example project Supply-Chain Policy                      │
├──────────────────────────┬─────────────────────────────────┤
│ pnpm audit --audit-level │ high — blocks merge             │
│ Override tracking        │ SECURITY_OVERRIDES.md + comment │
│ Override expiry review   │ 90-day issue reminder           │
│ SBOM format              │ CycloneDX JSON                  │
│ SBOM retention           │ 90 days (artifact) + GitHub     │
│ grype scan               │ runs after SBOM on release      │
│ Min release age          │ 7 days (see separate article)   │
└──────────────────────────┴─────────────────────────────────┘
```

## Anti-patterns

- **Using `--audit-level critical` only**: high-severity CVEs in authentication or
  cryptography libraries are routinely exploitable and must not be let through.
- **Adding overrides without documentation**: an undocumented `pnpm.overrides` entry
  looks like an arbitrary version pin to the next developer. Always add a SECURITY_OVERRIDES
  entry and CVE reference.
- **Removing an override before verifying the upstream fix landed**: check that the
  direct dependency's latest version pulls a safe transitive version before removing
  the override.
- **Running `pnpm audit` only in CI**: run it locally before opening a PR to avoid
  introducing CVEs that block teammates. Add it to a pre-push git hook via Husky.
- **Applying overrides in individual package `package.json` files**: overrides must
  be in the workspace root `package.json`. Per-package override declarations are
  silently ignored by pnpm.

## Gotchas

- **`pnpm audit` vs. `npm audit`**: pnpm delegates to the npm registry's advisory
  endpoint. CVE coverage is the same as `npm audit`, not the full NVD database.
  Use grype for broader CVE coverage.
- **Overrides do not affect the Worker bundle's external dependencies**: the Wrangler
  build bundles Worker code with esbuild. If a bundled package has a CVE, patching it
  via `pnpm.overrides` works only if the override forces the correct version into
  `node_modules` before the bundle step.
- **`--prod` flag audits only `dependencies`, not `devDependencies`**: a vulnerable
  Vite plugin or test runner in `devDependencies` does not affect the Worker runtime
  but may affect developer machines. Audit without `--prod` on a periodic schedule.
- **pnpm lockfile must be regenerated after adding overrides**: `pnpm install` rewrites
  the lockfile. Commit the updated `pnpm-lock.yaml` alongside the `package.json` change.

## Verification

```bash
# 1. Clean install to verify lockfile integrity
pnpm install --frozen-lockfile

# 2. Audit gate
pnpm audit --audit-level high
# Expected: exit 0 (no high/critical CVEs)

# 3. Confirm override is active
pnpm why tar
# Expected: shows "tar@6.2.1" (overridden version) in the tree

# 4. SBOM generation
syft dir:. -o cyclonedx-json=/tmp/sbom-check.cdx.json
jq '.metadata.component.name' /tmp/sbom-check.cdx.json
# Expected: "." or the workspace package name

# 5. grype scan
grype sbom:/tmp/sbom-check.cdx.json --fail-on high
# Expected: exit 0 if all high/critical are resolved
```

## Related

- `pnpm-overrides-materialization.md` — deep dive on how pnpm applies overrides
- `pnpm-minimum-release-age-supply-chain-delay.md` — supply-chain timing policy
- `npm-sbom-generation-scope-and-reproducibility.md` — npm SBOM comparison
- `npm-audit-signatures-registry-key-verification.md` — registry integrity signing
- `semgrep-custom-rules-ci-security.md` — static analysis for security rules
- `sbom-generation-tools.md` — syft vs. cdxgen vs. trivy comparison

## Sources

- https://pnpm.io/cli/audit
- https://pnpm.io/package_json#pnpmoverrides
- https://cyclonedx.org/specification/overview/
- https://github.com/anchore/syft
- https://github.com/anchore/grype
