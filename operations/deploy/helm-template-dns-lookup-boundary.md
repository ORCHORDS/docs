# Helm template DNS lookup boundary

**Issue**

Enabling DNS during template rendering makes output depend on live network state and can leak queried names or create nondeterministic releases.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep `--enable-dns` disabled for reproducible render and policy lanes.
- If required, isolate and allowlist resolver access in a separate discovery step.
- Capture resolved inputs as reviewed values before deployment.

## Verification

1. Render offline and with controlled DNS answers.
2. Simulate timeout, NXDOMAIN, and changed records.
3. Require identical deployment manifests for identical reviewed inputs.

## Gotchas

- DNS lookup during rendering is not service readiness.
- Responses can change between render and apply.
- Template authors control queried names.

## Official source

- [Official documentation](https://helm.sh/docs/helm/helm_template/)
