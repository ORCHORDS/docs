# sysinternals-procmon-procexp

**Issue:** On Windows, a large class of "not my code" failures, an app that cannot find its config file, a build tool blocked by a locked file, a service that dies reading a registry key, a DLL that loads from the wrong place, is invisible to source-level debuggers because the failing decision happens inside the OS or a third-party binary. Process Monitor and Process Explorer, the core Sysinternals pair, record the actual file, registry, process, and network operations so you can watch what the system really did instead of guessing from error dialogs. Windows developers who lack these tools end up rebooting, reinstalling, or blaming dependencies; the ones who have them usually find the answer in a two-minute trace.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Installation and hygiene

1. **Install via winget.** The suite is now package-managed: `winget install Microsoft.Sysinternals.Suite` gets everything, and individual tools are available under their own `Microsoft.Sysinternals.*` IDs. This replaces the old ritual of downloading a ZIP from the website.
2. **Prefer the Microsoft Store for auto-updates.** The Store version of Sysinternals updates itself, which matters because these tools actively follow Windows internals changes. A stale ProcMon that mishandles a new event type produces misleading traces.
3. **Accept the EULA per machine.** GUI tools prompt once, but command-line use in automation needs the `/accepteula` switch or the prompt silently blocks your script.
4. **Keep live.sysinternals.com in mind.** The live share always hosts the current binaries, useful for running a tool on a machine you cannot install anything on, such as a locked-down build agent or a colleague's laptop mid-incident.
5. **Run elevated when tracing system activity.** Without admin rights the tools see a fraction of the events, and the symptom is a trace that is mysteriously missing the very process you care about.

## Process Monitor fundamentals

1. **Know the four event classes.** ProcMon records file system, registry, process/thread, and network events, each with operation, path, result, and detail columns. Almost every investigation starts by deciding which of those four columns to filter on.
2. **Filter before you capture, not after.** A default trace collects hundreds of thousands of events per minute. Set a filter on your target process name before reproducing the issue, because a filtered 5,000-event trace gets read while an unfiltered 2-million-event one gets abandoned.
3. **Read the Result column religiously.** The most valuable filter is showing only failures: NAME NOT FOUND, ACCESS DENIED, SHARING VIOLATION. A missing config file being probed in six wrong directories is instantly visible as a cluster of NAME NOT FOUND probes.
4. **Use highlighting for the second axis.** While a filter narrows the trace, highlighting failures or a specific path lets you keep context around the interesting events without drowning. The combination of one filter plus one highlight covers most sessions.
5. **Save the trace, not a screenshot.** Save the PML file when a bug goes to another team or a vendor. A saved trace can be reopened, re-filtered, and exported to CSV or XML; a screenshot of it cannot.

## ProcMon workflows that pay off immediately

1. **The missing-file hunt.** Filter to your process, enable the result-is-failure preset, reproduce, and read the sequence of probed paths. The directory just before the failure is usually where the app expected its file; this single workflow solves most "works on my machine" deployment bugs.
2. **The locked-file identification.** When a build or git operation cannot delete or overwrite a file, filter to that path and look for the other process with an open handle, then use Process Explorer to close or identify the owner. This replaces reboot-as-a-service.
3. **The ACCESS DENIED triage.** Filter for ACCESS DENIED under your process and compare the requested access in the detail pane with the file or key's actual ACL. This distinguishes "wrong permissions" from "wrong identity," which leads to completely different fixes.
4. **The config-discovery trick.** Wondering where an opaque tool stores its settings? Filter to its process, close and reopen its settings dialog, and the registry writes or file saves in that window reveal the exact location.
5. **Boot logging for startup failures.** ProcMon can log across boots, capturing services and drivers from the earliest phase, which is the only practical way to debug "the service fails to start" or driver-load problems that occur before you could launch anything.
6. **Backtracking for last-known-good.** Enable the backtracking feature to see what a process did with a file before the current operation, which reconstructs the sequence leading to a surprise result instead of showing only the final error.

## Process Explorer workflows

1. **Inspect any process in the dual-pane view.** ProcExp shows a process's handles and loaded DLLs side by side, which answers "is the right DLL version actually loaded" and "what does this process hold open" in one window, the questions ProcMon traces are overkill for.
2. **Find the process locking a file.** Use the find-handle-or-DLL search on a filename, and ProcExp jumps to the owning process, where you can inspect or close the handle. This is the canonical replacement for restarting the machine to delete a file.
3. **Read the process tree during failures.** Parent-child relationships show what actually launched what, which exposes wrapper scripts, shadow-spawned helpers, and orphaned children that task manager's flat list hides entirely.
4. **Replace Task Manager.** ProcExp can install itself as the task manager replacement, so Ctrl-Shift-Esc opens a tool with command lines, verified signatures, and per-process CPU history instead of the bare name list.
5. **Verify image signatures and strings.** The columns for verified signer and company catch masquerading binaries, and the strings search inside a binary or running process often reveals embedded paths, versions, and error text in otherwise opaque executables.
6. **Watch threads and stacks.** The threads tab with per-thread stacks shows where a spinning process is spending time, a lightweight CPU investigation that frequently identifies the misbehaving subsystem without a full debugger attach.

## Making findings stick

1. **Export evidence for tickets.** Export filtered views to CSV and attach them alongside the saved PML, with one line in the ticket naming the culprit operation, path, and result. Vendors and platform teams act on that immediately.
2. **Save filter presets per workflow.** The failure-view, per-process, and per-path filters deserve saved presets so the next investigation starts at step two instead of rebuilding the filter.
3. **Turn traces into fixes, then documentation.** Once the missing path or denied key is found, fix it and write the real location into the project docs; the same ProcMon hunt should never be needed twice for one repository.
4. **Timebox the capture.** Reproduce quickly, stop the capture, then analyze. A three-second focused trace is a scalpel; an hour-long background capture is a haystack with the needle still in it.
