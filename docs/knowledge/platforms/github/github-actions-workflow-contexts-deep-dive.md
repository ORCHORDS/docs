# GitHub Actions Workflow Contexts Deep Dive

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Expressions like `${{ github.event.pull_request.head.sha }}` work in one place but return
empty in another. A secret referenced in a `run:` step resolves, but the same reference in
`with:` does not. Understanding which contexts are available at which scope — workflow,
job, or step — prevents silent failures and security mistakes.

## Context

GitHub Actions exposes information through **contexts**: structured objects accessible in
expressions (`${{ }}`) and in environment variables. The nine primary contexts are:

| Context    | Contains                                           |
|------------|----------------------------------------------------|
| `github`   | Event payload, repo, ref, actor, run IDs           |
| `env`      | Variables set with `env:` or `GITHUB_ENV`          |
| `vars`     | Repository / organisation / environment variables  |
| `jobs`     | Outcome of other jobs (reusable workflows only)    |
| `steps`    | Outputs and outcome of earlier steps in this job   |
| `runner`   | OS, temp dir, tool cache path                      |
| `secrets`  | Repository, environment, and organisation secrets  |
| `needs`    | Outputs and result of upstream jobs                |
| `inputs`   | `workflow_dispatch` / `workflow_call` inputs       |
| `matrix`   | Current matrix dimension values                    |

---

## github Context

```yaml
# Full reference of commonly used fields
- name: Dump github context
  run: |
    echo "Event name  : ${{ github.event_name }}"
    echo "Ref         : ${{ github.ref }}"          # refs/heads/main
    echo "Ref name    : ${{ github.ref_name }}"     # main
    echo "SHA         : ${{ github.sha }}"
    echo "Actor       : ${{ github.actor }}"        # username who triggered
    echo "Triggering  : ${{ github.triggering_actor }}"  # differs on re-runs
    echo "Repository  : ${{ github.repository }}"  # owner/repo
    echo "Run ID      : ${{ github.run_id }}"
    echo "Run number  : ${{ github.run_number }}"
    echo "Run attempt : ${{ github.run_attempt }}"
    echo "Workflow    : ${{ github.workflow }}"
    echo "Job         : ${{ github.job }}"
    echo "Server URL  : ${{ github.server_url }}"
    echo "API URL     : ${{ github.api_url }}"
```

`github.event` contains the full JSON payload of the triggering event. Fields vary by event
type — always check with `github.event_name` before accessing event-specific fields.

```yaml
# Safe access pattern for event-specific payload
- if: github.event_name == 'pull_request'
  run: echo "PR number ${{ github.event.pull_request.number }}"
- if: github.event_name == 'push'
  run: echo "Pusher ${{ github.event.pusher.name }}"
```

---

## env, vars, and secrets Contexts

```yaml
# env: is a workflow-scoped or job-scoped map; it IS available inside if: conditions
env:
  DEPLOY_ENV: production

jobs:
  deploy:
    env:
      WRANGLER_VERSION: "3.65.0"
    steps:
      - name: Show env
        run: echo "$DEPLOY_ENV / $WRANGLER_VERSION"
        # ${{ env.DEPLOY_ENV }} also works in expression position

      # vars: holds non-secret configuration (repository variables)
      - run: echo "Account ${{ vars.CF_ACCOUNT_ID }}"

      # secrets: not echoed in logs; masked automatically
      - run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

**Context availability in `if:` conditions:**

| Context   | Available in `if:`? |
|-----------|---------------------|
| `github`  | Yes                 |
| `env`     | Yes                 |
| `vars`    | Yes                 |
| `secrets` | **No** (use env var workaround) |
| `steps`   | Yes (same job only) |
| `needs`   | Yes                 |
| `inputs`  | Yes                 |

```yaml
# Workaround: check secret presence via env var
- name: Deploy if token present
  if: env.CF_TOKEN != ''
  env:
    CF_TOKEN: ${{ secrets.CF_API_TOKEN }}
  run: npx wrangler deploy
```

---

## needs Context: Inter-Job Outputs

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image-tag: ${{ steps.tag.outputs.value }}
    steps:
      - id: tag
        run: echo "value=sha-${{ github.sha }}" >> $GITHUB_OUTPUT

  deploy:
    needs: [build]
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying ${{ needs.build.outputs.image-tag }}"
      # Also check upstream result
      - if: needs.build.result == 'success'
        run: echo "Build passed"
```

`needs.<job>.result` is one of `success`, `failure`, `cancelled`, or `skipped`. It is set
even when the job failed — useful for conditional cleanup steps.

---

## steps Context: Intra-Job Step Outputs and Outcomes

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run tests
        id: tests
        run: npm test
        continue-on-error: true    # don't fail the job yet

      - name: Upload coverage
        if: steps.tests.outcome == 'success'
        uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: coverage/

      - name: Fail on test failure
        if: steps.tests.outcome == 'failure'
        run: exit 1
```

`steps.<id>.outcome` — result before `continue-on-error` is applied: `success`, `failure`,
`cancelled`, or `skipped`.
`steps.<id>.conclusion` — result after `continue-on-error`: always `success` when
`continue-on-error: true`.

---

## inputs Context: workflow_dispatch and workflow_call

```yaml
# Caller (workflow_dispatch)
on:
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [staging, production]
        default: staging
      dry-run:
        type: boolean
        default: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - run: |
          echo "Target: ${{ inputs.environment }}"
          echo "Dry run: ${{ inputs.dry-run }}"
          if [[ "${{ inputs.dry-run }}" == "true" ]]; then
            echo "Skipping actual deploy"
          else
            npx wrangler deploy --env ${{ inputs.environment }}
          fi
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

For `workflow_call`, `inputs` are defined under `on.workflow_call.inputs` and accessed
identically. The `secrets` context in a called workflow only contains secrets explicitly
passed with `secrets: inherit` or listed under `on.workflow_call.secrets`.

---

## matrix Context

```yaml
jobs:
  deploy-regions:
    strategy:
      matrix:
        region: [us-east-1, eu-west-1, ap-southeast-1]
        node:   [18, 20]
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "Region : ${{ matrix.region }}"
          echo "Node   : ${{ matrix.node }}"
          echo "Runner : ${{ runner.os }}"
```

`matrix` is only populated within a matrix job; it is `{}` in non-matrix jobs.

---

## runner Context

```yaml
steps:
  - name: Show runner details
    run: |
      echo "OS    : ${{ runner.os }}"          # Linux / Windows / macOS
      echo "Arch  : ${{ runner.arch }}"        # X64 / ARM64
      echo "Temp  : ${{ runner.temp }}"        # /tmp or C:/path/to/project
      echo "Tool  : ${{ runner.tool_cache }}"  # /opt/hostedtoolcache
      echo "Debug : ${{ runner.debug }}"       # 1 when ACTIONS_STEP_DEBUG=true
```

`runner.temp` is the correct path for temporary artefacts; it is cleaned between jobs. Do
not use hard-coded `/tmp` — it is unavailable on Windows runners.

---

## Anti-patterns

- **Interpolating `secrets` directly in `run:` strings** — the value is masked in logs but
  shell escaping can leak it via error messages. Always pass secrets as environment
  variables to `run:` blocks.
- **Using `github.actor` for authorization checks** — `actor` is the user who triggered the
  run and can be spoofed via forks. Use environment protection rules or `github.ref` checks
  instead.
- **Accessing `steps.<id>.outputs` before the step runs** — outputs are only populated after
  the step completes; a step cannot reference its own outputs.
- **Referencing `needs` in the same job** — `needs` only holds results from *upstream* jobs,
  not the current one.
- **Using `env:` context for secrets in `if:` conditions** — `${{ env.SECRET_VALUE != '' }}`
  may partially unmask the value in debug logs. Use a boolean flag environment variable
  instead.

---

## Gotchas

- `github.event.pull_request` is `null` on `push` events. Defensive access:
  `${{ github.event.pull_request && github.event.pull_request.head.sha || github.sha }}`
- Context expressions are evaluated at **job dispatch time** for `if:` and at **step
  runtime** for `run:` / `with:` — side effects of earlier steps are not visible in
  a job-level `if:`.
- `github.ref_name` on a tag push is the tag name (e.g. `v1.2.3`), not a branch name.
- `github.run_id` is unique per workflow run; `github.run_number` resets when the workflow
  file is deleted and recreated.
- `vars` context is not available on self-hosted runners that are offline at dispatch time;
  the value resolves to an empty string silently.

---

## Verification

```yaml
# Dump all contexts to the step summary for debugging
- name: Context dump
  if: runner.debug == '1'
  run: |
    cat >> $GITHUB_STEP_SUMMARY <<'EOF'
    ## Context Dump
    ```json
    ${{ toJSON(github) }}
    ```
    EOF
```

Enable `ACTIONS_STEP_DEBUG=true` as a repository secret, then rerun the workflow. The full
context dumps appear in the debug log stream.

---

## Related

- `github-actions-expression-syntax-functions.md` — functions usable inside `${{ }}`
- `github-actions-job-outputs.md` — passing data between jobs
- `github-actions-secrets-management.md` — secret scoping and injection
- `github-actions-reusable-workflows.md` — `inputs` and `secrets` in called workflows

---

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/accessing-contextual-information-about-workflow-runs
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/contexts
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows
