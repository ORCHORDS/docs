# systemd Service Credentials for Runtime Secret Delivery

**Issue:** Putting service secrets in unit files, command-line arguments, or ordinary environment variables makes them easy to expose through configuration, process inspection, logs, and accidental commits.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use systemd's credential mechanism for host services:

- `LoadCredential=` imports a credential from a protected file or socket.
- `LoadCredentialEncrypted=` loads a credential encrypted for the target host or an allowed scope.
- The service reads the material from a file below `$CREDENTIALS_DIRECTORY`; pass that path to the application rather than expanding secret contents into the unit.
- Apply a sandbox with a dedicated user, `NoNewPrivileges=yes`, minimal filesystem access, and only required capabilities.
- Provision encrypted blobs through the deployment system and keep plaintext out of source control and generated unit text.

Credentials are size-limited and intended for small opaque values, not general configuration or large datasets. Rotation should update the source/blob and restart or reload the consumer through an explicit, tested procedure.

## Verification

- Inspect the effective unit with `systemctl cat` and verify it contains no plaintext.
- Check process arguments, exported environment, journal output, crash reports, and deployment logs.
- Run the service as its configured identity and confirm only that process can read the runtime credential.
- Exercise missing, malformed, expired, and rotated credentials.
- Confirm restart cleanup and that backup/diagnostic tooling does not collect the plaintext runtime directory.

## Gotchas

Encryption at rest is not authorization by itself; scope and host identity matter. An application can still leak a credential after reading it. Never place a real credential in a test fixture. Prefer short-lived or narrowly scoped credentials and audit downstream use.

## Sources

- [systemd.exec credentials](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#Credentials)
- [systemd-creds](https://www.freedesktop.org/software/systemd/man/latest/systemd-creds.html)
- [systemd credentials design](https://systemd.io/CREDENTIALS/)
