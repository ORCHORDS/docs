# systemd DynamicUser and managed directory lifecycle

**Issue:** Long-lived static service accounts accumulate host privileges and files, while dynamically allocated user IDs can be recycled and make unmanaged persistent paths unsafe.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `DynamicUser=yes` only for services compatible with transient identities. Let systemd provision writable locations through `StateDirectory=`, `CacheDirectory=`, `LogsDirectory=`, and `RuntimeDirectory=`; keep the rest of the filesystem read-only with service sandboxing. Do not grant ownership of arbitrary persistent host paths to a dynamic numeric UID. Explicitly classify data as runtime, cache, log, or durable state and back up only the durable class.

## Verification

Start and stop a disposable service repeatedly, confirm its identity allocation and directory ownership remain usable, and prove it cannot write outside managed locations. Reboot, upgrade, and restore a test state directory. Inspect the unit security posture and verify cleanup behavior for runtime versus persistent directories.

## Gotchas

Dynamic numeric IDs may be reused, so numeric ownership outside systemd-managed directories can cross a future service boundary. `DynamicUser=` is not a container and does not replace syscall, network, capability, or filesystem restrictions.

## Official sources

- https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
