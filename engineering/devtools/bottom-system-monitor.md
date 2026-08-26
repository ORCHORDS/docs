# bottom-system-monitor

**Issue:** top/htop shows limited info; need better process and resource visualization
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Finding which process is spiking CPU or memory in a server environment with limited tools.

## Pattern / Solution
btm (bottom) shows CPU, memory, network, disk I/O, and process tree in TUI. Zoomable graphs. Filter processes with /. Kill process with dd. Battery widget for laptops. btm --basic for minimal mode on low-resource systems.

## Gotchas
- Install as bottom package; binary is btm
- Config at ~/.config/bottom/bottom.toml for persistent layout preferences

## Related
- bandwhich-network-monitor, tmux-configuration
