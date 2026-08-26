# Cloudflare Pages Custom Build Config

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your Cloudflare Pages project fails to build because the default framework preset does not match your monorepo layout, custom output directory, or non-standard build command. You need to configure the build pipeline to use a specific root directory, inject environment-specific variables, or chain multiple build steps without committing CI hacks to the repo.

## Context

Cloudflare Pages supports two configuration surfaces: the dashboard (project settings) and `wrangler.toml` / `pages.json` for programmatic control. Build configuration determines the command run during the managed build, the directory Pages serves, and which environment variables are exposed at build time. Mismatches between these settings and actual project structure produce silent partial builds or incorrect asset roots.

---

## 1. wrangler.toml Pages Build Block

Declare build configuration in `wrangler.toml` so it is version-controlled and applied consistently across all environments.

```toml
# wrangler.toml
name = "my-pages-project"
pages_build_output_dir = "dist"

[env.production]
name = "my-pages-project-prod"
pages_build_output_dir = "dist"

[env.staging]
name = "my-pages-project-staging"
pages_build_output_dir = "dist"
```

Deploy with environment targeting:

```bash
# Build and deploy to staging branch
wrangler pages deploy dist --project-name my-pages-project --branch staging

# Build and deploy to production
wrangler pages deploy dist --project-name my-pages-project --branch main
```

---

## 2. Custom Build Command via CI

When the managed Pages build is insufficient, use `wrangler pages deploy` from your own CI after running an arbitrary build step.

```yaml
# .github/workflows/pages-deploy.yml
name: Pages Deploy
on:
  push:
    branches: [main, staging]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Custom build step
        env:
          VITE_API_URL: ${{ secrets.VITE_API_URL }}
          NODE_ENV: production
        run: |
          npm run generate:types
          npm run build:css
          npm run build

      - name: Deploy to Pages
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler pages deploy dist --project-name my-pages-project --branch ${{ github.ref_name }}
```

---

## 3. Monorepo Root Directory Override

For monorepos where the Pages app lives in a subdirectory, set the root directory so the managed build resolves `package.json` and installs dependencies from the correct location.

```typescript
// scripts/pages-deploy.ts — programmatic deploy for monorepo
import { execSync } from 'child_process';
import { resolve } from 'path';

const APP_DIR  = resolve(__dirname, '../apps/web');
const DIST_DIR = resolve(APP_DIR, 'dist');
const PROJECT  = 'my-pages-project';
const BRANCH   = process.env.GITHUB_REF_NAME ?? 'main';

// Build inside the app directory so relative paths resolve correctly
execSync('npm run build', { cwd: APP_DIR, stdio: 'inherit' });

// Deploy from the workspace root so wrangler picks up root wrangler.toml
execSync(
  `npx wrangler pages deploy ${DIST_DIR} --project-name ${PROJECT} --branch ${BRANCH}`,
  { stdio: 'inherit' }
);
```

---

## 4. Build-Time Environment Variable Injection

Inject per-environment secrets as Pages build environment variables. Variables prefixed with the framework convention (e.g. `VITE_`, `NEXT_PUBLIC_`) are embedded into the static bundle at build time.

```typescript
// scripts/set-pages-build-vars.ts
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;
const PROJECT    = process.env.PAGES_PROJECT_NAME!;

const vars: Record<string, { value: string }> = {
  VITE_API_URL:      { value: process.env.API_URL! },
  VITE_SENTRY_DSN:   { value: process.env.SENTRY_DSN! },
  VITE_APP_VERSION:  { value: process.env.npm_package_version! },
};

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/${PROJECT}`,
  {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      deployment_configs: {
        production: { env_vars: vars },
      },
    }),
  }
);

if (!res.ok) throw new Error(`Failed to set build vars: ${await res.text()}`);
console.log('Build environment variables updated');
```

---

## 5. Build Output Validation Before Deploy

Validate the build artifact directory before uploading to catch misconfigured output paths early.

```typescript
// scripts/validate-pages-build.ts
import { existsSync, statSync, readdirSync } from 'fs';
import { resolve } from 'path';

const DIST = resolve(process.cwd(), process.env.BUILD_OUTPUT_DIR ?? 'dist');
const REQUIRED_FILES = ['index.html', '_headers', '_redirects'];

if (!existsSync(DIST)) {
  throw new Error(`Build output directory not found: ${DIST}`);
}

const stats = statSync(DIST);
if (!stats.isDirectory()) {
  throw new Error(`${DIST} is not a directory`);
}

for (const file of REQUIRED_FILES) {
  if (!existsSync(resolve(DIST, file))) {
    console.warn(`Warning: expected file missing from build: ${file}`);
  }
}

const files = readdirSync(DIST, { recursive: true }) as string[];
console.log(`Build output: ${files.length} files in ${DIST}`);

if (files.length < 3) {
  throw new Error('Build output appears empty — aborting deploy');
}
```

---

## 6. Pages Functions Co-deployment

When your Pages project uses Functions (server-side), ensure the `functions/` directory is present in the build output root and that compatibility dates are pinned.

```toml
# wrangler.toml — Functions compatibility config
name = "my-pages-project"
pages_build_output_dir = "dist"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

[env.production]
compatibility_date = "2025-09-01"
```

```typescript
// functions/api/[[route]].ts — Pages Function catch-all
export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, params } = context;
  const route = (params['route'] as string[]).join('/');
  // Forward to Worker via service binding
  return env.API_WORKER.fetch(request);
};
```

---

## Anti-Patterns

- **Setting build environment variables in the dashboard only** — they are invisible to CI and not reproducible; use the API or `wrangler.toml` instead.
- **Deploying from a nested subdirectory path** — `wrangler pages deploy apps/web/dist` resolves relative to CWD; use absolute paths or `cd` to avoid deploy-path drift.
- **Omitting `pages_build_output_dir` in wrangler.toml** — Pages falls back to framework detection, which silently picks the wrong directory for custom frameworks.
- **Mixing managed builds and direct uploads in the same project** — toggling between modes resets build settings on the dashboard.

## Gotchas

- `_headers` and `_redirects` files must be placed in the **build output** directory, not the source root. Frameworks like Vite require them in `public/` to copy them through.
- Pages Functions are only bundled when `functions/` exists at the build output root **or** the project source root — not both. Placing it in `src/functions/` is ignored.
- The `compatibility_date` set in `wrangler.toml` only applies to Functions; static asset serving is unaffected.
- Direct upload deploys (`wrangler pages deploy`) do not trigger the dashboard's managed build pipeline — they upload a pre-built artifact directly.

## Verification

1. Run `wrangler pages deployment list --project-name <name>` and confirm the latest deployment shows the expected branch and build duration.
2. Fetch `https://<branch>.<project>.pages.dev/` and verify the correct `index.html` is served.
3. Check the Pages deployment log in the dashboard for the effective build command and output directory used.
4. Confirm all required `_headers` rules apply with `curl -I https://<url>/some-path`.

## Related

- `cloudflare-pages-build-cache-optimization.md`
- `cloudflare-pages-preview-deployments.md`
- `pages-functions-env-var-management.md`
- `pages-deployment-hooks-post-deploy-scripts.md`
- `wrangler-pages-direct-upload-ci.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/build-configuration/
- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/workers/wrangler/commands/#pages-deploy
- https://developers.cloudflare.com/pages/configuration/headers/
