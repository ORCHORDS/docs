# systemd credential delivery and secret lifetime

**Issue:** Passing secrets in environment variables or command lines increases exposure through process inspection, logs, and inherited environments.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

systemd credentials can expose bounded credential files to a service through `LoadCredential=` and related encrypted-credential mechanisms. The application should read the provided credential path at runtime; never place real values in unit files or the repository.

## Controls and verification

- Restrict unit and source credential ownership.
- Encrypt credentials where the threat model and host keying support it.
- Avoid logging paths with contents or reading values into diagnostics.
- Rotate atomically and define whether restart/reload is required.
- Bound credential size and service access.
- Inspect the running service environment and command line to confirm no value leaks.

## Sources

- [systemd.exec: Credentials](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#Credentials)
- [systemd-creds](https://www.freedesktop.org/software/systemd/man/latest/systemd-creds.html)
