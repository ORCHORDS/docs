# github-packages-npm-registry

**Issue:** Publishing and consuming npm packages via GitHub Packages registry
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams want to publish internal npm packages without a paid npmjs.com org plan. GitHub Packages provides a private npm registry scoped to the GitHub org, authenticated via `GITHUB_TOKEN`.

## Pattern / Solution
**`package.json` — scope the package to your org:**
```json
{
  "name": "@myorg/my-package",
  "version": "1.0.0",
  "publishConfig": {
    "registry": "https://npm.pkg.github.com"
  }
}
```

**`.npmrc` in the project root (publishing):**
```
@myorg:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}
```

**Publish workflow:**
```yaml
name: Publish package

on:
  release:
    types: [published]

permissions:
  contents: read
  packages: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://npm.pkg.github.com'
          scope: '@myorg'

      - run: npm ci
      - run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Consuming the package in another repo:**
```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://npm.pkg.github.com'
          scope: '@myorg'

      - run: npm ci
        env:
          NODE_AUTH_TOKEN: ${{ secrets.READ_PACKAGES_TOKEN }}
```

**`.npmrc` for consumers:**
```
@myorg:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}
```

## Gotchas
- `GITHUB_TOKEN` can publish packages from the same repo, but consuming packages from *another* repo requires a PAT with `read:packages` scope — `GITHUB_TOKEN` is repo-scoped
- Package names must be scoped (`@org/name`) — unscoped packages cannot be published to GitHub Packages
- Deleting package versions requires `packages:delete` scope and is often irreversible for public packages
- GitHub Packages does not support `npm search` or package discovery through `npm info` the same way npmjs.com does
- Storage and bandwidth count against GitHub billing — each org has a free tier (500 MB / 1 GB bandwidth) then pay-per-use

## Related
- `github-actions-docker-build-push.md`
- `github-release-automation-2026.md`
- `github-fine-grained-personal-access-tokens.md`
