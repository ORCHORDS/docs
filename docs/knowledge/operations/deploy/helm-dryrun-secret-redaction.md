# Helm dry-run secret redaction

**Issue**

A Helm dry run can render Kubernetes Secret manifests into terminal and CI logs even though no release is installed.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `--hide-secret` for dry-run output and restrict artifact retention.
- Render sensitive values from secret managers at deployment time.
- Run schema and policy checks on redacted structure, not secret plaintext.

## Verification

1. Seed canary secrets and scan logs/artifacts for them.
2. Test client and server dry-run modes.
3. Verify failure diagnostics remain useful after redaction.

## Gotchas

- Redaction in Helm does not sanitize plugin or template debug output.
- Base64 is not secrecy.
- A real install still sends secrets to the cluster API.

## Official source

- [Official documentation](https://helm.sh/docs/helm/helm_install/)
