# systemd service sandboxing through incremental hardening

**Issue:** A compromised service inherits unnecessary host filesystem, privilege, namespace, and kernel access when its unit lacks confinement.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use systemd execution controls such as `NoNewPrivileges=`, `ProtectSystem=`, `ProtectHome=`, private namespaces, and capability restrictions to reduce a service's reachable attack surface. Add controls incrementally from observed requirements; a copied hardening block can break legitimate startup, logging, networking, or updates.

## Controls and verification

- Run `systemd-analyze security` as guidance, not a proof of safety.
- Start with a canary and inspect denied operations.
- Prefer explicit writable paths over broad filesystem access.
- Minimize capabilities and system-call exposure from measured behavior.
- Test restart, upgrade, backup, diagnostics, and failure recovery.
- Keep rollback available and version drop-ins in configuration management.

## Sources

- [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
- [systemd-analyze](https://www.freedesktop.org/software/systemd/man/latest/systemd-analyze.html)
