# systemd-service-hardening

**Issue:** Most systemd units ship with near-zero sandboxing, so any successful RCE in a network-facing service (Node exporter, a Flask admin app, Redis, a custom worker) runs with full user privileges, full filesystem visibility, and the ability to escalate via SUID binaries. This article covers how to measure a unit's exposure with `systemd-analyze security` and systematically apply the filesystem, privilege, and syscall sandboxing directives that turn a default unit into a contained one — without breaking it in production.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why Default Units Are Dangerous

1. **Exposure score of ~9.5 out of the box.** `systemd-analyze security <unit>.service` scores every unit from 0.0 (safe) to 10.0 (unsafe), and a typical vendor unit with no hardening keys scores around 9.5 because no sandboxing directives are set at all.
2. **Vendor units prioritize compatibility.** Distro and upstream package maintainers deliberately ship permissive units so the service works on every possible configuration, which means the hardening work is pushed to the operator — this was the explicit motivation behind Fedora's system-wide systemd hardening change proposal for default services.
3. **RCE impact equals user compromise.** Without sandboxing, code execution inside the service can read `/etc`, other users' home directories, cloud instance metadata via curl, and any secrets in environment files — a foothold from which privilege escalation is usually trivial.
4. **Enablement is additive and measurable.** Each directive is independent, so hardening can be rolled out incrementally: baseline the score, apply a safe drop-in, validate functionality, and re-score until the unit sits below an agreed threshold (commonly < 2.0 for internet-facing services).
5. **Score is a checklist, not a verdict.** The exposure score weights directives by impact and ignores whether a specific service actually needs a capability (e.g., a service that legitimately changes users), so treat it as a tracking metric and apply judgment per directive.

## Filesystem and Process Isolation

1. **ProtectSystem=strict with explicit exceptions.** `strict` mounts the entire filesystem hierarchy read-only for the service; you then punch writable holes only where needed with `ReadWritePaths=` (e.g., `/var/lib/myapp`), which converts arbitrary file-tampering into a denial-of-service at worst.
2. **ProtectHome=yes and PrivateTmp=yes.** `ProtectHome` makes `/home`, `/root`, and `/run/user` inaccessible — killing the "read the operator's SSH keys" attack path — while `PrivateTmp` gives the service its own namespaced `/tmp` and `/var/tmp` so it cannot plant or read files used by other services.
3. **DynamicUser=yes paired with StateDirectory.** For stateless or simple-state services, `DynamicUser` allocates an ephemeral, unprivileged UID per start (no `/etc/passwd` entry to attack), and `StateDirectory=`/`CacheDirectory=`/`LogsDirectory=` auto-create owned writable paths under `/var/lib`, `/var/cache`, and `/var/log` for it.
4. **ProtectKernelTunables, ProtectKernelModules, ProtectKernelLogs.** These three make `/proc/sys`, `/sys`, kernel log access, and module loading read-only or inaccessible, blocking the classic container-and-host escape primitive of rewriting `core_pattern` or loading a hostile kernel module from a compromised service.
5. **PrivateDevices and ProtectClock.** `PrivateDevices=yes` gives the service a minimal `/dev` with no raw block devices (no direct disk access), and `ProtectClock=yes` blocks `settimeofday` so a compromised service cannot shift time to break certificate validation or log forensics.

## Privilege and Syscall Reduction

1. **NoNewPrivileges=yes.** This is the single highest-value line in most hardening drop-ins: it sets `PR_SET_NO_NEW_PRIVS` so setuid binaries (including `sudo` and `su`) can never grant elevated privileges to anything executed by the service, defusing the entire SUID attack surface.
2. **CapabilityBoundingSet and AmbientCapabilities.** Drop all Linux capabilities by default (`CapabilityBoundingSet=` empty), then grant back only the minimal ones via `AmbientCapabilities=` — for example a port-443 binding helper needs only `CAP_NET_BIND_SERVICE`, not the full root capability set of running as UID 0.
3. **RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6.** Limiting the socket address families the service may use blocks exotic kernel attack surfaces such as AF_PACKET (raw packet injection) and AF_NETLINK (interface manipulation); anything that only speaks TCP/IP has no reason to open them.
4. **SystemCallFilter with a deny baseline.** Apply `SystemCallFilter=@system-service deny:...` (or an `@allowed` allowlist for aggressive cases) to block `execve`-style process spawning, `ptrace`, module init, and the `@privileged`/`@resources` groups; combine with `SystemCallArchitectures=native` to block x32-abuse of syscall numbers.
5. **MemoryDenyWriteExecute, LockPersonality, RestrictSUIDSGID, RestrictNamespaces.** This cluster blocks W+X memory mappings (defeating many shellcode payloads), locks the process personality/ABI, prevents creating SUID/SGID files on writable paths, and blocks namespace creation used to wrap the process in a different view of the system.

## Workflow and Pitfalls

1. **Always harden via drop-ins, not by editing vendor units.** Use `systemctl edit <unit>` (creating `/etc/systemd/system/<unit>.d/override.conf`) so package upgrades that replace the vendor unit file never silently discard your hardening; changes take effect only after `systemctl daemon-reload` and `restart`.
2. **Validate after every directive, not at the end.** Aggressive options break real services — `ProtectSystem=strict` breaks anything writing outside its granted paths, `PrivateNetwork=yes` breaks DNS for anything resolving names, and `SystemCallFilter` can kill JIT runtimes — so add directives in small batches and exercise the service (health check, real request) between batches.
3. **Automation tools exist for the boilerplate.** Synacktiv's SHH (Systemd Hardening Helper) generates a candidate hardening option set for a unit, and `systemd-analyze security --offline` can score units from files in CI, letting you enforce a maximum exposure score as a pipeline gate on unit-file PRs.
4. **Expect interaction with containers.** Inside Docker/Podman many directives are already applied or conflict with the outer runtime; for Podman, the same directives apply to quadlet `.container` files, but nesting sandboxing inside a container namespace occasionally produces EPERM failures that only appear at runtime.
5. **Some services legitimately need what you are removing.** Services that fork workers, bind low ports, read `/etc` dynamically, or use JITs need scoped exceptions (`ReadWritePaths=`, `AmbientCapabilities=`, `MemoryDenyWriteExecute=no`); document each exception in the drop-in with a comment so the next operator knows it is deliberate, not oversight.
