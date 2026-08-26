# macOS runner thermal and disk capacity signals

**Issue**

Sustained compilation, simulators, and artifact creation can trigger thermal throttling or disk exhaustion, lengthening checks and making failures appear flaky.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Collect thermal state, CPU load, free space, inode/file growth, swap, and job duration outside workflow-controlled paths.
- Set admission thresholds that drain rather than accept a job when safe workspace headroom is unavailable.
- Bound DerivedData, simulator, package, and artifact retention with exact paths.
- Keep required checks intact; capacity pressure delays work rather than skipping it.

## Verification

1. Run sustained production-shaped workloads and correlate thermal state with duration.
2. Fill a disposable volume to each threshold and verify drain/cleanup behavior.
3. Reboot and confirm telemetry and capacity admission recover.

## Gotchas

- Temperature sensors and thermal state are not identical signals.
- Deleting broad cache roots can destroy active jobs.
- APFS free-space reporting and snapshots need explicit observation.

## Official sources

- [Apple ProcessInfo thermalState](https://developer.apple.com/documentation/foundation/processinfo/thermalstate)
- [Apple File System Programming Guide](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/)
