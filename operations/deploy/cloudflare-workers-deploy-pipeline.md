# Cloudflare Workers Deploy Pipeline

## Overview

Cloudflare Workers can be deployed from GitHub Actions with Wrangler. Keep the build reproducible, validate the exact revision before deployment, and scope the Cloudflare credential to only the resources and operations the deployment needs.

Primary reference: [Cloudflare Workers — GitHub Actions](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/).

## Authentication boundary

Cloudflare's current Workers GitHub Actions guidance uses a Cloudflare API token plus the account ID for non-interactive Wrangler authentication. Do not substitute a long-lived Global API Key.

Store the API token as a GitHub secret, preferably on a protected production Environment when that fits the repository's deployment model. The account ID is an identifier rather than a secret, but keeping deployment configuration together as an environment variable/secret is acceptable.

Create the narrowest API token that can deploy the intended Worker/account resources. Do not print, return, serialize, upload, or write the token into deployment evidence.

## Reproducible GitHub Actions example

The example below intentionally runs the repository-pinned Wrangler dependency instead of resolving a mutable deployment action or package at run time. Replace the commented action SHAs only after reviewing the corresponding official action release and verifying the commit belongs to that repository.

```yaml
name: Deploy Worker

on:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: worker-production
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-24.04
    environment: production
    timeout-minutes: 15

    steps:
      - name: Checkout exact revision
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v5.0.0
        with:
          persist-credentials: false
          fetch-depth: 1

      - name: Setup Node
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v6.0.0
        with:
          node-version: 24
          cache: npm

      - name: Install locked dependencies
        run: npm ci

      - name: Validate
        run: npm test

      - name: Deploy exact checked-out source
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: npx wrangler deploy --env production
```

Requirements for this pattern:

- commit `package-lock.json` and pin Wrangler in `devDependencies`;
- use `npm ci`, not `npm install`, in CI;
- do not use `npx --yes wrangler@latest` or another runtime dependency resolution in the deployment job;
- keep validation and deployment bound to the same reviewed source revision;
- use a protected Environment/reviewer policy where appropriate;
- never expose deployment credentials to untrusted pull-request code.

If the project intentionally uses `cloudflare/wrangler-action`, review its current primary documentation and pin the action implementation to an immutable full commit SHA rather than a movable major-version tag.

## Worker runtime secrets

Worker runtime secrets are not ordinary Wrangler configuration variables and must never be returned to callers.

Application code may read a secret from `env`, but it must use the value only for the intended internal operation:

```javascript
export default {
  async fetch(request, env) {
    await verifyRequest(request, env.MY_SECRET);
    return new Response("ok");
  },
};
```

Do not include a literal "bad example" that returns a secret value: even documentation examples are copied into real systems and scanned by repository guards. State the prohibition instead. Do not log the value, include it in exception text, persist it to D1/R2/KV for debugging, place it in a GitHub job summary, or upload it as an artifact.

Use Wrangler's documented secret-management command or dashboard/API flow to create runtime secrets. Do not place runtime secret values directly in `wrangler.toml`/`wrangler.jsonc`.

## Environment routing

Use explicit named environments when a repository genuinely deploys more than one Worker target:

```toml
name = "my-worker"
main = "src/index.js"
compatibility_date = "2026-08-18"

[env.production]
name = "my-worker-production"

[env.staging]
name = "my-worker-staging"
```

Deploy the intended environment explicitly:

```bash
npx wrangler deploy --env production
```

Keep secrets/configuration separated by target. A staging credential must not implicitly grant production access.

## Deployment safety

Before a production deploy:

1. Require the full validation suite on the exact revision.
2. Confirm the workflow is running from the intended repository/ref and not arbitrary fork code.
3. Keep `GITHUB_TOKEN` permissions read-only unless the job has a documented write requirement.
4. Keep the Cloudflare API token narrowly scoped and unavailable outside the deploy job/environment.
5. Avoid build-once/deploy-different-source drift: either deploy the validated immutable artifact with provenance or rebuild from the exact validated commit using the same lockfile/toolchain.
6. Record non-secret deployment metadata such as commit SHA, Worker name, environment, workflow run, and result.
7. Treat rollback as a production change: validate the target version and obtain the same required authorization as any other production deployment.

## Rollback and versions

Wrangler's version/deployment commands evolve. Before automating rollback, verify the exact command against the current Wrangler documentation and test it in a non-production environment. Do not keep a stale copy-pasted `rollback` command in a runbook as if its flags are permanent API.

For incident response, record immutable deployment/version identifiers and retain enough provenance to identify the source commit and configuration used for each production version.

## References

- [Cloudflare Workers — GitHub Actions](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)
- [Cloudflare Wrangler commands](https://developers.cloudflare.com/workers/wrangler/commands/)
- [GitHub Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
