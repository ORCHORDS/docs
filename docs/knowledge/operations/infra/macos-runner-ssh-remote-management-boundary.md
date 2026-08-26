# Headless macOS runner SSH boundary

**Issue**

Remote Login is an administrative path to the runner host and can bypass workflow-level isolation if accounts, keys, or forwarding are broad.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable Remote Login only for named operator accounts and restrict it at the network boundary.
- Use managed SSH keys, host-key verification, short access lifetimes, and auditable privilege escalation.
- Disable agent forwarding and remote command features not required for operations.
- Separate the runner service account from administrator login accounts.

## Verification

1. Attempt access as allowed, removed, and runner-service identities.
2. Rotate host and user keys in a canary procedure.
3. Audit login, sudo, and runner maintenance events without capturing secrets.

## Gotchas

- GitHub runner registration does not secure SSH.
- A stolen operator key can access cached workflow material.
- Headless recovery still needs an out-of-band path.

## Official sources

- [Apple allow remote login](https://support.apple.com/guide/mac-help/allow-a-remote-computer-to-access-your-mac-mchlp1066/mac)
- [OpenSSH sshd_config](https://man.openbsd.org/sshd_config)
