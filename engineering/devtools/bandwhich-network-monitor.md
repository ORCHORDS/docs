# bandwhich-network-monitor

**Issue:** Unknown process consuming network bandwidth with no visibility into which connection
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Network is slow; cannot identify which process or connection is using bandwidth.

## Pattern / Solution
sudo bandwhich shows bandwidth usage by process, connection, and remote host in real time. Displays upload/download per process. Useful for finding unexpected data exfiltration or misconfigured services.

## Gotchas
- Requires root/sudo for network capture
- Ports with known services shown by name — use --raw for numeric ports

## Related
- bottom-system-monitor, wireshark-basics
