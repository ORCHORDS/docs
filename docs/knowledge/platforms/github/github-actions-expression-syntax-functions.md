# GitHub Actions Expression Syntax, Contexts, and Built-in Functions

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

GitHub Actions YAML contains a mini-expression language used in `if:` conditions, `env:` assignments, `with:` inputs, and `run:` steps. Developers hit these pain-points regularly:

- `if: github.ref == 'refs/heads/main'` evaluates to false when the branch name has a typo, and there's no error — the step just skips silently.
- `fromJSON` and `toJSON` are needed to pass structured data between jobs but the exact call shape isn't obvious.
- String functions like `contains`, `startsWith`, `endsWith` behave differently on arrays vs. strings.
- `${{ }}` delimiters inside `run:` steps interact with shell variable expansion in confusing ways.

This article is a reference for all expression contexts, types, operators, and functions.

---

## Context

Expressions use the `${{ <expression> }}` delimiter. They can appear in any YAML string value position except inside a `|` block scalar that starts with `run:` (where the `${{ }}` still works but competes with shell's `${ }` syntax).

**Supported literal types:**

| Type | Examples |
|---|---|
| Boolean | `true`, `false` |
| Null | `null` |
| Number | `0`, `3.14`, `-1`, `0x1F` (hex) |
| String | `'single-quoted'` (use `''` to escape a single quote inside) |

**Comparison operators:** `==`, `!=`, `<`, `<=`, `>`, `>=`
**Logical operators:** `&&`, `||`, `!`
**Property access:** `context.property` or `context['property']` (bracket form required for keys with hyphens or dots)

---

## The Main Contexts

### `github` context — event and repository metadata

```yaml
steps:
  - name: Inspect common github context values
    run: |
      echo "Event: ${{ github.event_name }}"
      echo "Ref: ${{ github.ref }}"
      echo "SHA: ${{ github.sha }}"
      echo "Actor: ${{ github.actor }}"
      echo "Repo: ${{ github.repository }}"
      echo "Default branch: ${{ github.event.repository.default_branch }}"
      echo "PR number: ${{ github.event.pull_request.number }}"
```

Useful properties:

| Property | Value |
|---|---|
| `github.ref` | `refs/heads/main`, `refs/tags/v1.0.0`, `refs/pull/42/merge` |
| `github.ref_name` | `main`, `v1.0.0`, `42/merge` (short form, since 2022) |
| `github.ref_type` | `branch` or `tag` |
| `github.event_name` | `push`, `pull_request`, `schedule`, `workflow_dispatch`, etc. |
| `github.actor` | login of the user or app that triggered the run |
| `github.run_id` | unique numeric ID for this workflow run |
| `github.run_attempt` | `1` on first run, `2` on re-run |

### `env` context — environment variables set in the workflow

```yaml
env:
  APP_NAME: myapp

jobs:
  deploy:
    env:
      REGION: us-east-1
    steps:
      - run: echo "${{ env.APP_NAME }} deploying to ${{ env.REGION }}"
```

`env` context is read-only within expressions. Variables set with `echo "X=Y" >> $GITHUB_ENV` are available via `env` context in **subsequent** steps, not the current one.

### `secrets` context — encrypted secrets

```yaml
steps:
  - run: echo "token length: ${{ secrets.MY_TOKEN != '' && 'set' || 'empty' }}"
```

Never print secret values directly. Use the `!= ''` check for presence. The `secrets` context is not available in `if:` conditions on reusable workflow jobs — use `inputs` or `vars` instead.

### `vars` context — repository/org/environment variables (non-secret)

```yaml
# Set at repo level: Settings → Secrets and variables → Variables
steps:
  - run: echo "Deploy target: ${{ vars.DEPLOY_TARGET }}"
```

Unlike `secrets`, `vars` values can appear in logs safely.

### `needs` context — outputs from prior jobs

```yaml
jobs:
  build:
    outputs:
      image_tag: ${{ steps.meta.outputs.version }}
    steps:
      - id: meta
        run: echo "version=1.2.3" >> $GITHUB_OUTPUT

  deploy:
    needs: build
    steps:
      - run: echo "Deploying ${{ needs.build.outputs.image_tag }}"
```

`needs.<job_id>.result` is `success`, `failure`, `cancelled`, or `skipped`.

### `steps` context — outputs and outcome from steps in the same job

```yaml
steps:
  - id: detect
    run: echo "changed=true" >> $GITHUB_OUTPUT

  - if: steps.detect.outputs.changed == 'true'
    run: echo "Something changed"
```

`steps.<step_id>.outcome` is the result before `continue-on-error` is applied; `steps.<step_id>.conclusion` is after.

### `matrix` context — current matrix value

```yaml
strategy:
  matrix:
    node: [18, 20, 22]
steps:
  - run: echo "Node version: ${{ matrix.node }}"
```

---

## Built-in Functions

### String functions

```yaml
# contains(search, item)
# Returns true if string contains substring, or if array contains item
- if: contains(github.event.pull_request.labels.*.name, 'hotfix')
  run: echo "Hotfix PR"

- if: contains(github.ref, 'release/')
  run: echo "Release branch"

# startsWith(searchString, searchValue) — case-insensitive
- if: startsWith(github.ref, 'refs/tags/v')
  run: echo "Version tag"

# endsWith(searchString, searchValue) — case-insensitive
- if: endsWith(github.actor, '[bot]')
  run: echo "Triggered by a bot"

# format(string, ...replacements) — like C# String.Format
- name: Set image name
  run: echo "IMAGE=${{ format('{0}/{1}:{2}', 'ghcr.io', github.repository, github.sha) }}" >> $GITHUB_ENV
```

### JSON functions

```yaml
# fromJSON(value) — parse a JSON string into an object
- id: matrix-gen
  run: echo "targets=[\"prod\",\"staging\"]" >> $GITHUB_OUTPUT

# In a subsequent job referencing needs:
strategy:
  matrix:
    target: ${{ fromJSON(needs.setup.outputs.targets) }}

# toJSON(value) — serialise a context object for debugging
- run: echo '${{ toJSON(github.event) }}'

# Example: pass a map between steps
- id: config
  run: |
    echo 'data={"region":"us-east-1","replicas":3}' >> $GITHUB_OUTPUT

- run: |
    REGION="${{ fromJSON(steps.config.outputs.data).region }}"
    echo "Deploying to $REGION"
```

### Array and object functions

```yaml
# join(array, separator) — concatenate array to string
# github.event.commits[*].id is an array of commit SHAs
- run: echo "Commits: ${{ join(github.event.commits.*.id, ', ') }}"

# toJSON trick to pretty-print any context for debugging
- run: echo '${{ toJSON(steps) }}'
```

### Status-check functions (only valid in `if:` expressions)

```yaml
# success() — true if all prior steps/jobs succeeded
- if: success()
  run: echo "All good"

# failure() — true if any prior step/job failed
- if: failure()
  run: echo "Something failed — sending alert"

# always() — runs regardless of prior results (replaces the deprecated syntax)
- if: always()
  run: echo "This always runs"

# cancelled() — true if the workflow was cancelled
- if: cancelled()
  run: echo "Run was cancelled"

# Combining status with other conditions
- if: failure() && github.ref == 'refs/heads/main'
  run: echo "Main branch failure — page on-call"
```

---

## Practical Patterns

### Ternary-style conditional assignment

Expressions have no ternary operator, but `&&` / `||` can simulate it:

```yaml
env:
  # If on main branch, set ENVIRONMENT to "production", else "preview"
  ENVIRONMENT: ${{ github.ref == 'refs/heads/main' && 'production' || 'preview' }}
```

Caveat: if the truthy value is itself falsy (`''`, `false`, `0`, `null`), this evaluates to the fallback. For that edge case, use a shell `if` in a `run:` step instead.

### Checking if a secret is set without revealing it

```yaml
- name: Validate secrets
  run: |
    if [ -z "${{ secrets.DEPLOY_TOKEN != '' && 'SET' || '' }}" ]; then
      echo "::error::DEPLOY_TOKEN is not configured"
      exit 1
    fi
```

### Deriving values from git ref

```yaml
env:
  # Strip "refs/tags/" prefix
  TAG_NAME: ${{ startsWith(github.ref, 'refs/tags/') && github.ref_name || '' }}
  IS_RELEASE: ${{ startsWith(github.ref, 'refs/tags/v') }}
```

### Dynamic job name using matrix

```yaml
jobs:
  test:
    name: "Test (${{ matrix.os }}, Node ${{ matrix.node }})"
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        node: [18, 20]
```

---

## Anti-patterns

- **Using double quotes inside `${{ }}`.** Expression strings must use single quotes. Double quotes inside `${{ }}` delimiters terminate the YAML string. Write `${{ 'my string' }}` not `${{ "my string" }}`.

- **Comparing `github.ref` to a short branch name.** `github.ref` is always the full ref (`refs/heads/main`). Comparing to `'main'` always evaluates false. Use `github.ref_name` for the short form, or `github.ref == 'refs/heads/main'`.

- **Trusting `contains()` for security decisions.** `contains('refs/heads/feature-something', 'feature')` matches any branch with "feature" anywhere in the name. For security-sensitive gates, use strict equality.

- **Chaining `fromJSON` on nested steps output without null-guard.** If the step that sets the output was skipped, `fromJSON(steps.x.outputs.data)` receives `''` and returns `null`, which causes cryptic downstream errors. Guard with `steps.x.outputs.data != '' && fromJSON(steps.x.outputs.data) || ...`.

- **Using `${{ }}` inside `run:` for secrets injection.** Even though it works, it bakes the secret value directly into the shell command string (visible in debug logs and process tables). Set secrets as `env:` on the step and reference them as `$VARNAME` in the shell script instead.

---

## Gotchas

- **Expression evaluation order.** The entire `if:` expression is evaluated before the step runs. You cannot reference `steps.X.outputs.Y` in an `if:` on step X itself — only in subsequent steps.

- **`null` in comparisons.** Missing context properties return `null`. `null == ''` is `false` in expressions. `null == false` is also `false`. Use `!= ''` rather than truthiness checks where you expect string values.

- **`contains()` on arrays uses equality, not substring match.** `contains(array, 'foo')` checks for an element equal to `'foo'` — it does not check if any element contains the string `'foo'` as a substring.

- **`format()` index is zero-based.** `format('{0} and {1}', 'a', 'b')` → `a and b`. There is no `{-1}` or named placeholder support.

- **`${{ }}` in multiline `run:` with heredoc.** Dollar-brace sequences inside a shell heredoc may expand shell variables before GitHub Actions parses them if you use `<<EOF` without quoting. Use `<<'EOF'` to prevent shell expansion, then handle `${{ }}` substitution separately.

---

## Verification

```yaml
# Diagnostic step — dump key expression values to the log
- name: Debug expressions
  run: |
    echo "ref=${{ github.ref }}"
    echo "ref_name=${{ github.ref_name }}"
    echo "ref_type=${{ github.ref_type }}"
    echo "is_tag=${{ startsWith(github.ref, 'refs/tags/') }}"
    echo "event=${{ github.event_name }}"
    echo "actor=${{ github.actor }}"
    echo "run_attempt=${{ github.run_attempt }}"
    echo "context_json=${{ toJSON(github) }}" | head -20
```

Enable debug logging for a run to see full expression evaluation traces:

```bash
gh workflow run deploy.yml \
  --field debug_enabled=true   # requires ACTIONS_RUNNER_DEBUG=true secret set to true
```

---

## Related

- `github-actions-job-outputs.md` — passing data between jobs via `outputs:`
- `github-actions-dynamic-matrix-and-fail-fast.md` — `fromJSON` for dynamic matrices
- `github-actions-security-hardening.md` — expression injection risks in `run:` steps
- `github-actions-environment-file-delimiter-injection.md` — `$GITHUB_ENV` injection
- `actions-job-summaries-annotations-reporting.md` — using expressions for conditional annotations

---

## Sources

- GitHub Docs: "Expressions" — https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/evaluate-expressions-in-workflows-and-actions
- GitHub Docs: "Contexts" — https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/accessing-contextual-information-about-workflow-runs
- GitHub Docs: "Variables" — https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/store-information-in-variables
