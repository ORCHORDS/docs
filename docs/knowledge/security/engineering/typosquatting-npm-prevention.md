# typosquatting-npm-prevention

**Issue:** Malicious npm packages misspell popular package names to intercept developer installs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers mistype package names (e.g., `lodahs`, `expres`, `recat`) during install and pull malicious packages that exfiltrate environment variables, secrets, and SSH keys in postinstall scripts.

## Pattern / Solution
```bash
# 1. Lock dependency versions in package-lock.json / yarn.lock — commit and enforce
npm ci  # installs exactly what's in lockfile, no resolution

# 2. Use npm audit and socket.dev in CI
npx socket scan .

# 3. Enable npm's built-in security features
npm config set ignore-scripts true  # disable postinstall scripts globally during audit

# 4. Verify package before install
npm info express | grep -E 'name|version|homepage'
```
```yaml
# GitHub Actions — use socket-security/socket-action
- uses: SocketDev/socket-github-action@v2
  with:
    api-key: ${{ secrets.SOCKET_API_KEY }}
```

## Gotchas
- Postinstall scripts run with full shell access — `ignore-scripts` in `.npmrc` prevents this in non-CI envs too.
- `npm pack` and inspect the tarball before publishing internal packages to catch accidental inclusions.
- Scoped packages (`@company/pkg`) are harder to typosquat but not immune — `@cornpany/pkg` is valid.
- Check that your CI image's npm cache is not poisoned by a previous malicious install.

## Related
- `dependency-confusion-attack.md`
- `supply-chain-integrity-sigstore.md`
- `supply-chain-npm-security.md`
