# dependency-confusion-attack

**Issue:** Public package registries can be poisoned with higher-versioned packages that shadow private internal packages
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
If an organization uses private packages (e.g., `@company/internal-lib`) but the npm/PyPI/RubyGems resolver also checks public registries, an attacker can publish a malicious public package with the same name at a higher version number. The package manager picks the public version.

## Pattern / Solution
```json
// npm — pin private scopes to private registry in .npmrc
@company:registry=https://registry.company.internal
//registry.company.internal/:_authToken=${NPM_INTERNAL_TOKEN}

// Alternatively, use npm workspaces with explicit overrides
// package.json
{
  "overrides": {
    "@company/internal-lib": "file:./packages/internal-lib"
  }
}
```
```toml
# pip — use --index-url to force private registry for scoped packages
# pip.conf
[global]
index-url = https://pypi.company.internal/simple
extra-index-url = https://pypi.org/simple
```
```bash
# Proactive defense — claim your internal package names on public registries
# Publish a stub with your company contact and version 0.0.1
```

## Gotchas
- `extra-index-url` in pip does NOT give the private registry priority — use `index-url` only or handle ordering carefully.
- Gradle resolves from all repositories and picks the highest version by default — set `repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS` and use a single trusted source.
- Namespace squatting (publishing empty stubs) on npm/PyPI is the simplest mitigation — do it for all internal package names.
- CI pipelines with auto-updated lock files are prime targets.

## Related
- `typosquatting-npm-prevention.md`
- `supply-chain-integrity-sigstore.md`
- `supply-chain-npm-security.md`
