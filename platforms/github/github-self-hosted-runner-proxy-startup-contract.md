# GitHub Self-Hosted Runner Proxy Startup Contract

**Issue:** A runner may configure successfully in an interactive shell but fail as a service because proxy variables are read at startup, use different casing, or do not reach Docker-based actions.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Set `https_proxy`, `http_proxy`, and `no_proxy` before starting or configuring the runner. Prefer lowercase names on Linux and macOS to avoid case-sensitivity conflicts.
- Restart the runner service after changing proxy settings; the runner reads them when it starts.
- For stable service configuration, place proxy variables in the runner installation directory's `.env` file or in the service manager environment with appropriately protected permissions.
- Configure the Docker daemon and container runtime separately when jobs or actions pull images through the proxy; runner connectivity does not prove container connectivity.
- Use hostnames, not IP addresses, in `no_proxy`, following the runner's documented limitation.
- Keep proxy credentials out of repository workflows and diagnostic output. Use a narrowly scoped account and rotate it through the host's secret-management process.

## Verification
- From the service account, restart the runner and run a job that reaches GitHub, downloads an action, and pulls a container image.
- Test an internal hostname covered by `no_proxy` and an external hostname requiring the proxy.
- Inspect runner and proxy logs for credential leakage and verify revoked proxy credentials stop working.

## Gotchas
Shell exports used during installation do not automatically become service environment. Diagnose the runner process, Docker daemon, and job container as separate network paths.

## Official sources
- https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/using-a-proxy-server-with-self-hosted-runners
