# ci-pipeline-leaked-secrets

## Symptom

A CI log, build artifact, or error message contains a live API key, OAuth token, or database password. The secret is now in the CI system's log retention, potentially visible to anyone with read access to the pipeline history, and may be indexed by monitoring tools or forwarded to third-party integrations (Slack, Datadog, GitHub PR comments).

## Root cause

CI pipelines handle secrets as environment variables, but several common patterns leak them:

- **Echo / debug output**: `echo $DEPLOY_KEY` or `print(env)` in a debugging step.
- **Error messages**: a curl failure prints the full request including `Authorization: Bearer sk-...` in stderr.
- **Artifact upload**: a `.env` file or config with embedded secrets gets uploaded as a build artifact visible to all collaborators.
- **Log redaction gaps**: GitHub Actions redacts `secrets.*` values, but secrets injected via `env:` into third-party actions may not be redacted if the action prints them.
- **Fork-PR context**: secrets are intentionally withheld from fork PRs, but a PR author can exfiltrate them via a modified workflow if `pull_request_target` is used incorrectly.

## Fix

1. **Never echo secrets.** Remove all `echo $VAR`, `print(env)`, `set -x` near secret variables. Use `::add-mask::` in GitHub Actions to mask dynamic values.
2. **Redact in error handlers.** Wrap curl/fetch calls to strip auth headers from error output: `curl -sSf ... 2>&1 | sed 's/Bearer [^ ]*/Bearer [REDACTED]/g'`.
3. **Artifact hygiene.** `.gitignore` and `.dockerignore` must exclude `.env`, `*.key`, `*.pem`. Audit artifact upload steps with `actions/upload-artifact` to ensure only intended files are included.
4. **Never use `pull_request_target` with checkout of PR code.** This runs with write secrets. Use `pull_request` (no secrets) or run the checkout in a separate job without secrets.
5. **Rotate immediately on exposure.** If a secret appears in CI logs: revoke it, generate a new one, update the secret store, and force-push to squash the commit if the log is in git history.
6. **Scan CI configuration.** Run `gitleaks detect` or `trufflehog` on the `.github/workflows/` directory and CI scripts as part of pre-commit.
7. **Use OIDC, not long-lived tokens.** Replace `AWS_ACCESS_KEY_ID` secrets with GitHub OIDC federation — no static credentials to leak.

## Gotchas

- GitHub Actions masks `secrets.*` values, but NOT values derived from them (e.g., `echo ${TOKEN:0:10}` or base64-encoded variants).
- Fork PRs with `pull_request_target` + `actions/checkout` is a well-known supply-chain attack vector — treat it as a security boundary.
- CI log retention is often 90+ days by default. A leaked token may be valid long after you think it's been "deleted."
- Third-party actions can read your secrets and exfiltrate them via network calls. Pin actions to commit SHAs and audit their source.
- `set -x` in bash steps prints every variable assignment including secrets — use `set +x` around sensitive sections.

## Related

- `worktree/security-patch-process.md`
- `security/prompt-injection-defense.md`
- `github/github-actions-github-token-permission-minimization.md`
- `github/github-actions-artifact-attestations.md`
