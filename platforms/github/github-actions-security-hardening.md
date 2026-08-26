# GitHub Actions Security Hardening Playbook

## Overview

GitHub Actions workflows routinely process untrusted input, repository contents, deployment credentials, and privileged tokens. Treat every external action, shell interpolation, and credential boundary as part of the supply chain.

Primary reference: [GitHub Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use).

## Minimum token permissions

Declare `permissions` explicitly and grant only what the job needs. A validation-only workflow usually needs no write permissions:

```yaml
permissions:
  contents: read
```

Grant write scopes at the narrowest job possible. Do not copy broad examples such as `contents: write`, `packages: write`, or `deployments: write` into jobs that do not require them.

## Prefer short-lived identity where the provider supports it

GitHub OIDC lets a job request a short-lived identity token instead of storing a long-lived cloud credential. OIDC must be deliberately enabled for the job:

```yaml
permissions:
  contents: read
  id-token: write
```

`id-token: write` only permits requesting an OIDC token; the cloud provider must independently trust and authorize the repository/job identity. Restrict the provider-side trust policy by repository, branch/tag or protected environment. See [GitHub deployment security hardening](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments) and the provider-specific OIDC guide before implementation.

Do not claim OIDC support for a provider unless its current primary documentation supports the flow. For providers that require an API token in CI, use the narrowest token possible and protect it with an environment when appropriate.

## Secrets management

Never place a credential value in command text, arguments that are likely to be echoed, workflow output, a job summary, generated evidence, or an example response.

Prefer environment-scoped secret injection:

```yaml
- name: Deploy
  shell: bash
  env:
    DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
  run: |
    test -n "$DEPLOY_TOKEN"
    ./scripts/deploy.sh
```

The invoked deploy tool should read the credential from its documented environment variable or protected input mechanism. Do not `echo`, `printf`, `cat`, serialize, or return the secret. If a tool requires a credential file, create it with restrictive permissions in `$RUNNER_TEMP`, avoid tracing the command, and delete it in an `always()` cleanup step.

Never interpolate `${{ secrets.* }}` directly into shell program text. GitHub expressions are evaluated before the shell parses the script, which creates avoidable quoting/injection and logging risk.

## Pin actions correctly

GitHub recommends pinning actions to a full-length commit SHA. A checkout `ref` selects **repository content**; it does not pin the `actions/checkout` implementation.

```yaml
- name: Checkout
  uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v5.0.0
  with:
    persist-credentials: false
```

A full-length action commit SHA is immutable in normal Git usage and is the strongest supported pinning form. Verify that the SHA belongs to the intended action repository before adopting it. Repository/organization policy can require full-length SHA pins.

Apply the same review standard to reusable third-party workflows. A mutable tag such as `@v3` is not equivalent to an immutable commit pin.

## Protect deployment jobs

For production deployment jobs:

- use a protected GitHub Environment when available;
- restrict deploy triggers to the intended branch/tag and validate any manually supplied revision;
- keep deployment credentials out of pull-request workflows that execute untrusted code;
- separate validation from deployment so validation jobs do not inherit deployment secrets;
- set `persist-credentials: false` on checkout unless later Git operations genuinely require the checkout token;
- use concurrency controls appropriate to the deployment target;
- fail closed when required provenance/evidence cannot be produced.

## Shell and input safety

Treat branch names, issue/PR fields, commit messages, workflow inputs, and API responses as untrusted strings. Pass them through environment variables or structured APIs rather than interpolating expressions into shell code.

```yaml
- name: Validate requested target
  shell: bash
  env:
    TARGET: ${{ inputs.target }}
  run: |
    case "$TARGET" in
      staging|production) ;;
      *) echo "::error::unsupported target"; exit 1 ;;
    esac
```

Do not enable shell tracing (`set -x`) in credential-bearing steps.

## Runner isolation

Persistent self-hosted runners have a larger trust boundary than fresh hosted VMs because filesystem state, credentials, sockets, package caches, and privileged services can survive between jobs. Prefer ephemeral runners for untrusted workloads. When persistent self-hosted runners are required, limit who can submit runnable code, isolate deployment workloads, clean workspaces, minimize local privileges, and do not place unrelated production secrets on the host.

## Review checklist

Before merging a workflow change, verify:

- every external action is reviewed and pinned to an immutable full-length SHA where policy permits;
- `permissions` is explicit and minimal;
- secrets are neither interpolated into shell source nor printed/returned;
- protected deployment credentials are unavailable to untrusted PR execution;
- dependency installation is lockfile-based and reproducible;
- environment and trigger restrictions match the intended deployment boundary;
- generated logs, summaries, artifacts, caches, and evidence cannot contain credentials;
- cleanup executes on failure for temporary credential material or remote sessions.

## References

- [GitHub Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [Security hardening your deployments](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments)
- [OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [Managing GitHub Actions settings for a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
