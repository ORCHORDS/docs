# Bruno API Client — Collection-as-Code Patterns

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

API collections live inside Postman cloud or inside an Insomnia
SQLite export file. Neither is human-readable in a pull request diff,
neither travels with the code that owns the endpoints, and both
require team members to log in to a vendor service before they can
send the first test request. When the backend changes a contract,
the collection update happens (maybe) in a separate commit that no
reviewer sees.

## Context

example project uses a standard approach: one repo owns one domain. The
HTTP collection for that domain belongs in the same repo, reviewed
alongside the route changes that break it. Bruno's `.bru` format
is plain UTF-8 text — diffable, mergeable, grepable. The platform
team mandates Bruno for all new service repos; legacy Postman
workspaces are migrated when a service moves to Hono/Cloudflare
Workers.

## .bru File Format

Each request is one `.bru` file. The structure is line-oriented
and human-writable without the GUI.

```bru
meta {
  name: Create shipment
  type: http
  seq: 1
}

post {
  url: {{baseUrl}}/v1/shipments
  body: json
  auth: bearer
}

auth:bearer {
  token: {{API_TOKEN}}
}

body:json {
  {
    "origin": "{{origin}}",
    "destination": "{{destination}}"
  }
}

script:pre-request {
  const ts = Date.now();
  bru.setVar("origin", "LHR");
}

assert {
  res.status: eq 201
  res.body.id: isDefined
}
```

Variables in `{{double braces}}` resolve from the active environment
or from `bru.setVar()` calls inside `script:pre-request` blocks.

## Git-Friendly Workflow vs Postman / Insomnia

| Dimension          | Bruno (.bru)        | Postman (cloud)      | Insomnia            |
|--------------------|---------------------|----------------------|---------------------|
| Storage            | files in repo       | cloud JSON export    | SQLite / cloud      |
| PR diff            | readable line diff  | minified JSON blob   | binary / JSON blob  |
| Conflict resolve   | standard merge      | manual re-import     | manual re-import    |
| Auth required      | none                | Postman account      | optional cloud sync |
| CI runner          | `bru run` binary   | newman (npm)         | inso (npm)          |
| Scripting language | JS in bru blocks   | JS (sandbox)         | JS (Nunjucks tmpl)  |

Migrate an existing Postman collection with the GUI (File → Import)
or export the Postman JSON and use `bru convert`:

```bash
bru convert --from postman --input postman_export.json \
            --output ./api/collections/shipments
```

## Environment Variables and Secrets

Environments live in `environments/<name>.bru`. The file is safe to
commit when it contains only variable _names_ — never values.

```
# environments/local.bru
vars {
  baseUrl: http://localhost:8787
  origin:
}
vars:secret [
  API_TOKEN
]
```

Secret values are injected at runtime from the OS environment or a
`.env` file that is gitignored. The Bruno GUI reads `.env` in the
collection root automatically. The CLI reads it too:

```bash
# .env (gitignored)
API_TOKEN=sk-test-abc123

# Run against the local environment
bru run --env local ./api/collections/shipments
```

Never commit `environments/local.bru` with values filled in. Add
`environments/local.bru` to `.gitignore` if your team keeps a
`local` environment for personal overrides.

## CI Integration with `bru run`

```yaml
# .github/workflows/api-tests.yml
- name: Install Bruno CLI
  run: npm install -g @usebruno/cli

- name: Run API collection
  env:
    API_TOKEN: ${{ secrets.API_TOKEN }}
    BASE_URL: ${{ vars.STAGING_URL }}
  run: |
    bru run \
      --env staging \
      --output results/bruno-report.json \
      --format json \
      api/collections/shipments
```

`bru run` exits non-zero if any assertion fails. The JSON report
is compatible with most test-result dashboard integrations.

## Scripting

`script:pre-request` and `script:post-response` blocks run Node.js.
The `bru` object provides `bru.setVar()`, `bru.getEnvVar()`, and
`bru.getVar()`. `require` works for Node core modules only — npm
packages are unavailable in the sandbox; inject computed values via
environment variables instead.

## Anti-patterns

- Storing request values (tokens, IDs) in committed `.bru` files
  instead of environment variables.
- One monolithic collection folder — use one subdirectory per
  resource.
- Running `bru run` without `--env` in CI — falls back silently to
  a developer's personal local environment.
- Relying on Bruno UI-only features (notes, themes) for things that
  must run in CI — the CLI silently ignores them.

## Gotchas

- `vars:secret` masks the value in the GUI but does NOT encrypt the
  file. The value must still come from outside git.
- Script blocks use CommonJS (`require`), not ESM (`import`).
- `bru run` without a path runs everything in the current directory
  — scope it to the collection subdirectory.
- `seq` controls GUI display order, not `bru run` execution order.

## Verification

```bash
# Confirm CLI
bru --version   # expect >= 1.30

# Full collection run with JSON output
bru run --env staging api/collections/shipments \
    --output /tmp/results.json --format json && \
    echo "All assertions passed"
```

## Related

- `devtools/httpie-patterns.md`
- `devtools/curl-advanced-usage.md`
- `devtools/postman-collections.md`
- `devtools/insomnia-patterns.md`
- `testing/api-contract-testing.md`

## Source URLs (verified 2026-08-17)

- https://www.usebruno.com/
- https://github.com/usebruno/bruno
- https://docs.usebruno.com/scripting/introduction
- https://docs.usebruno.com/bru-language-reference
- https://docs.usebruno.com/ci-cd/github-actions
