# logrotate-log-rotation-management

**Issue:** Unbounded log growth is one of the most common and most preventable causes of production incidents — a chatty service fills the root filesystem, the database crashes on a failed write, and the outage post-mortem discovers a 47 GB access.log that nobody was rotating. At the same time, log rotation is fragmented across three independent mechanisms that teams frequently conflate: logrotate for flat files, systemd-journald's built-in space management for the journal, and the container runtime's per-container log rotation for stdout/stderr. Applying logrotate rules to journald or Docker logs does nothing, and the journald defaults (up to 4 GB per default and scaling to as much as 10% of the filesystem) quietly balloon on large disks. This article covers a coherent rotation strategy across all three mechanisms, retention policy design, and verification.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three rotation systems and their owners

1. **logrotate owns flat files.** Traditional services writing to /var/log (nginx, postgresql, app logs redirected to files) are rotated by logrotate's daily cron or systemd timer, which renames, compresses, and deletes files per policy. It only works on files opened by append; it is the wrong tool for anything that streams to stdout.
2. **journald rotates itself.** The systemd journal manages its own binary files under /var/log/journal, capped by journald.conf settings (SystemMaxUse, SystemKeepFree, MaxFileSec); logrotate directives on journal files are ignored and can actually corrupt the journal if they forcibly move files out from under journald.
3. **Container runtimes own stdout/stderr.** Docker's json-file driver rotates per-container logs when given max-size and max-file log options (per container or globally in daemon.json), and kubelet enforces containerLogMaxSize and containerLogMaxFiles; without these, an aggressive logger inside a container writes an unbounded file under /var/lib/containers that no host logrotate ever touches.

## Sizing a retention policy

1. **Start from the consumer, not the disk.** Retention exists so someone can investigate; ask how far back incidents realistically get triaged (often 7-14 days hot locally) and what long-term retention compliance requires (often 90 days to a year, shipped to object storage or a log platform rather than kept on the host).
2. **Classic rotation shape.** Red Hat's long-standing guidance is still a sane default: keep 4-5 rotated and compressed generations (rotate 4 plus current), rotate weekly or daily depending on volume, compress with delaycompress so the freshest file stays readable during post-rotation races.
3. **Cap the journal explicitly.** Set SystemMaxUse to a real number (500 MB to 2 GB for typical servers) and understand the default behavior: journald's fallback is min(4 GB, 10% of filesystem), which on a 400 GB disk permits a 40 GB journal — almost always unintended.
4. **Cap container logs by size, not hope.** A common global policy is 50 MB per file with 3 files per container (150 MB worst case per container), set in daemon.json so every compose-up and ad-hoc run inherits it; per-workload overrides go in the compose file or pod spec for known-noisy services.

## Writing robust logrotate rules

1. **copytruncate versus rename-plus-reload.** The clean pattern renames the file and signals the service (postrotate with nginx -s reopen or systemctl reload) so the process reopens the new file descriptor; copytruncate is the fallback for software that cannot reopen logs, at the cost of a small window of lost lines during the copy.
2. **Use su directives for permissions.** Running logrotate as root into directories owned by service users (www-data, postgres) fails silently without su user group in the stanza; this is the single most common "why did rotation stop working" bug.
3. **Errors must be loud.** Logrotate failures are invisible by default — a bad glob or unreadable directory just skips the stanza; ship logrotate status files and the cron/timer output into your monitoring, or periodically assert that the newest rotated file's timestamp matches policy.
4. **Do not double-rotate.** If a service rotates internally (nginx does not, but postgres and many Go apps can), pick one owner; two rotators racing produces files with rotated and truncated suffixes interleaved and eventually lost logs.

## Verification and drift checks

1. **Audit with a scheduled probe.** A weekly script that lists the largest files under /var/log and /var/lib/docker/containers, flags anything exceeding a threshold, and reports per-host disk headroom catches the failure mode before users do — unrotated growth is gradual until the day it is not.
2. **Test configuration changes with dry runs.** logrotate -d parses and simulates without acting; validate syntax in CI for rules shipped through configuration management, the same as any other config file.
3. **Check the actual limits after deployment.** journalctl --disk-usage against the configured SystemMaxUse, docker info log config against the intended driver options, and a forced rotation run on a canary host prove the policy works rather than merely existing.
4. **Local rotation is not retention strategy.** Treat host-level rotation as a disk-protection mechanism with days-to-weeks of hot retention, and ship logs to the aggregation layer (Loki, Elasticsearch, or object storage) for anything longer; conflating the two is how teams end up either keeping a year of logs on every app server or deleting evidence they needed.
