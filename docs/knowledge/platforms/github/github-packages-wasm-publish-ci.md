# GitHub Packages WASM Publish CI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You build a Rust or AssemblyScript crate that compiles to WebAssembly for use
in Cloudflare Workers, and want GitHub Actions to automatically publish the
resulting `.wasm` + glue JS/TS as an npm package to GitHub Packages (GHCR npm
registry) on every tagged release.

## Context

`wasm-pack` (Rust) and `asc` (AssemblyScript) both emit an npm-compatible
package directory. GitHub Packages supports scoped npm packages under the org
or user namespace. The key differences from a plain npm publish are: the
registry URL must point to `npm.pkg.github.com`, the `NODE_AUTH_TOKEN` must be
the Actions `GITHUB_TOKEN`, and the package name must be scoped to the GitHub
owner (`@org/package`).

## Rust + wasm-pack Build

```yaml
# .github/workflows/wasm-publish.yml
name: WASM Publish

on:
  push:
    tags: ["v*.*.*"]

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: wasm32-unknown-unknown

      - name: Install wasm-pack
        run: curl https://rustwasm.github.io/wasm-pack/installer/init.sh -sSf | sh

      - name: Build WASM package
        run: wasm-pack build --target bundler --out-dir pkg

      - name: Configure npm for GitHub Packages
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://npm.pkg.github.com"

      - name: Patch package name and version
        run: |
          cd pkg
          VERSION="${GITHUB_REF_NAME#v}"
          node -e "
            const fs = require('fs');
            const p = JSON.parse(fs.readFileSync('package.json','utf8'));
            p.name = '@${{ github.repository_owner }}/' + p.name;
            p.version = process.env.VERSION;
            p.publishConfig = { registry: 'https://npm.pkg.github.com' };
            fs.writeFileSync('package.json', JSON.stringify(p, null, 2));
          "
        env:
          VERSION: ${{ github.ref_name }}

      - name: Publish to GitHub Packages
        run: cd pkg && npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## AssemblyScript Build Variant

```yaml
      - name: Build AssemblyScript WASM
        run: |
          npm ci
          npx asc src/index.ts \
            --target release \
            --outFile dist/index.wasm \
            --textFile dist/index.wat \
            --exportRuntime
          # Copy glue JS into dist/
          cp src/glue.js dist/

      - name: Prepare package.json
        run: |
          node -e "
            const fs = require('fs');
            const pkg = {
              name: '@${{ github.repository_owner }}/my-wasm-module',
              version: '${GITHUB_REF_NAME}'.replace(/^v/,''),
              main: 'index.js',
              files: ['*.wasm','*.js','*.d.ts'],
              publishConfig: { registry: 'https://npm.pkg.github.com' }
            };
            fs.writeFileSync('dist/package.json', JSON.stringify(pkg, null, 2));
          "
```

## Consuming the WASM Package in a Worker

```typescript
// src/index.ts  (Cloudflare Worker)
import init, { processData } from "@myorg/my-wasm-module";

// Workers support top-level await for WASM init
const instance = await init();

export default {
  async fetch(req: Request): Promise<Response> {
    const input = await req.arrayBuffer();
    const result = processData(new Uint8Array(input));
    return new Response(result, { headers: { "Content-Type": "application/octet-stream" } });
  },
};
```

## npmrc for Local Development

```ini
# .npmrc  (commit to repo, no secrets here)
@myorg:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${GITHUB_TOKEN}
```

## Caching wasm-pack and cargo

```yaml
      - name: Cache cargo registry and wasm-pack
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target/
          key: wasm-${{ runner.os }}-${{ hashFiles('**/Cargo.lock') }}
          restore-keys: wasm-${{ runner.os }}-
```

## Anti-patterns

- **Publishing unscoped packages to GHCR npm** — GitHub Packages requires the npm package name to be scoped to `@owner`. An unscoped name will be rejected with a 422.
- **Using a PAT instead of `GITHUB_TOKEN`** — for `packages: write` from the same repo, `GITHUB_TOKEN` is sufficient and doesn't require secret rotation.
- **Committing `.npmrc` with a token** — the `.npmrc` should reference `${GITHUB_TOKEN}` as an env var; the token is injected at runtime by `setup-node`.
- **Skipping `--target bundler`** — wasm-pack's `--target web` produces ESM with `fetch`-based init that doesn't work in Workers; use `--target bundler` or `--target nodejs`.

## Gotchas

- `wasm-pack build` emits a `package.json` with the crate name as the package name (without scope). You must patch it before publish.
- GitHub Packages npm registry is immutable: once a version is published it cannot be overwritten. Use `npm dist-tag` to manage `latest`.
- Workers' `wasm_modules` binding (via wrangler.toml) is an alternative to npm WASM — it embeds the `.wasm` at deploy time rather than install time. Choose npm when the WASM is shared across multiple Workers.
- Package visibility follows the repository visibility by default; make it public via the GitHub Packages settings page if needed.

## Verification

```bash
# After the workflow runs, verify the package exists
gh api /orgs/MY_ORG/packages/npm/my-wasm-module/versions \
  --jq '.[0] | {name, version: .name, created: .created_at}'

# Install and test locally
npm install @myorg/my-wasm-module --registry https://npm.pkg.github.com
node -e "const m = require('@myorg/my-wasm-module'); console.log(Object.keys(m));"
```

## Related

- `github-packages-npm-registry.md`
- `github-packages-internal-workers-libraries.md`
- `github-actions-wasm-build-caching-workers.md`

## Sources

- https://rustwasm.github.io/docs/wasm-pack/commands/build.html
- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-npm-registry
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
