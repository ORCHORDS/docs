# Bandwhich Htop Network Diagnosis Recipes

Two small terminal tools answer the questions that general-purpose
monitors cannot. htop shows which processes are consuming CPU and
memory, with a per-core, per-thread view that `top` buries. bandwhich
shows which processes are consuming network bandwidth right now, broken
down by process, connection, and remote address. Together they turn "the
box is slow" into a named culprit in under a minute: htop for compute
and memory pressure, bandwhich for upload saturation, runaway sync
clients, and mystery connections. Both are TUI tools, both run on
macOS, Linux, and Windows, and both need elevated privileges for full
network visibility.

## Scope

Diagnosing local resource and network problems with htop and bandwhich:
installation and privilege requirements, what each screen actually
means, and repeatable recipes for the most common failure patterns on
developer machines and inside containers. Not covered: distributed
tracing, packet capture analysis (use Wireshark), or kernel-level
profiling.

## Workflow or implementation guidance

1. **Install both and accept the privilege model.** htop installs from
   every package manager (`brew install htop`, `apt install htop`,
   `scoop install htop`). bandwhich ships prebuilt binaries and via
   cargo (`cargo install bandwhich`); reading per-process socket
   statistics requires admin on Windows or root on macOS and Linux, so
   the normal invocation is `sudo bandwhich` or an elevated shell.
   bandwhich also offers a raw-mode style fallback for environments
   where the packet path is unavailable.
2. **Read htop correctly before acting.** The header bars show per-core
   CPU split by user/system; a load of stalled processes with idle CPU
   points at I/O or lock contention, not compute. The memory meters
   distinguish in-use from cache; "free memory is low" on a healthy
   Linux box is normal because cache is reclaimable. Sorting by
   `M_RESIDENT` or `PERCENT_CPU` (press F6 or use the column sort)
   finds the offender; `H` toggles threads, `l` lstrace-style
   per-process strace is available when htop is built with it, `k`
   sends a signal, and `F1` shows the whole keymap.
3. **Read bandwhich correctly.** It shows three synchronized panes:
   processes by current throughput, connections (local address and port
   to remote address and port), and remote addresses aggregated. The
   numbers are live bandwidth, not totals; leave it running for ten
   seconds before concluding anything, because short requests blink by.
4. **Recipe: saturating upload.** Video call quality collapses. Run
   bandwhich, sort the process pane by upload, and identify whether the
   consumer is a backup client, a Docker push, a sync tool, or the IDE
   uploading telemetry. htop in parallel confirms whether the same
   process is also burning CPU, which distinguishes active transfer
   from a stuck retry loop.
5. **Recipe: mystery traffic to an unknown remote.** A container or
   laptop is talking to an address nobody recognizes. bandwhich gives
   the process and the remote; the connection pane tells you the port,
   which narrows the protocol; then resolve ownership with a reverse
   DNS or WHOIS lookup. Combine with `htop` `F5` tree view to see which
   parent process spawned the child making the calls.
6. **Recipe: "the build machine is slow".** Open htop first. High
   `iowait` on a single core with low total CPU points at disk
   saturation; near-100 percent CPU on one compiler process is normal;
   dozens of node processes each at 5 percent is a watcher storm. Only
   if the disk is network-attached, switch to bandwhich to check
   whether the bottleneck is the link rather than the disk.
7. **Recipe: inside a container.** Run htop with pid and user namespace
   flags (`htop -p` against the host, or inside the container with
   `--pid=host` style launches) so host-wide visibility is preserved.
   bandwhich in the container shows only that container's sockets; for
   the whole host, run it on the host and map container PIDs back with
   the container runtime's `top` command.

## Controls

- **Least privilege for repeated use.** Granting developers passwordless
  elevation for bandwhich is a policy decision; on teams that forbid it,
  capture once as root with output redirection and analyze the text
  output instead of running the TUI elevated all day.
- **Read-only posture.** htop can send signals (kill) with one keypress
   by design; on shared machines prefer running it as a user that lacks
   permission to signal other users' processes rather than restricting
   the tool.
- **Run window discipline.** Both tools sample continuously; establish
   the habit of a fixed observation window (ten to thirty seconds) and
   a screenshot or saved output before making changes, so the
   before-and-after comparison exists.

## Validation evidence

A correct setup can be self-tested without a real incident:

1. Run htop and confirm the process list matches `ps aux` ordering for
   CPU; trigger a known load such as a tight loop in one shell and
   watch it appear at the top within the refresh interval.
2. Run bandwhich in one terminal and `curl -O` a large file in
   another; the curl process and the remote address of the download
   must appear in the corresponding panes, and throughput should be the
   same order as what the downloading tool reports.
3. Test privilege behavior deliberately: run bandwhich unelevated and
   confirm it fails with the documented permission error rather than
   silently showing empty panes; silent empties mean the wrong
   interface was captured.
4. In a container, start a known upload from inside it and verify
   whether the host-level bandwhich attributes it to the runtime
   process or the container process, which establishes how much
   indirection your environment adds.

## Failure modes and correction

- **bandwhich panes are empty despite traffic.** Elevated privileges
   missing, the wrong network interface selected (use the interface
   picker), or the traffic is on the loopback interface; check all
   three before blaming the tool.
- **Process attribution is a runtime process.** Containerized or
   Electron-style apps multiplex sockets through a parent process; use
   the connection pane plus `ss`/`netstat` per-PID to separate
   children.
- **htop shows a zombie or D-state process.** Uninterruptible sleep is
   usually I/O; the CPU sort will never surface it. Sort by state or
   check the `S` column, and treat persistent D-state as a storage or
   driver problem, not a process to kill.
- **Numbers disagree with the platform monitor.** Different accounting
   points (interface counters vs per-socket sampling) legitimately
   differ; use bandwhich for attribution and the platform monitor for
   totals.
- **Windows-specific gaps.** Elevated shells on Windows sometimes need
   the terminal started as administrator before launching bandwhich;
   launching it from a non-elevated shell can fail after startup.

## Limitations

- bandwhich reports bandwidth attribution, not payloads; it cannot
  decrypt, reassemble, or show request content — that is packet-capture
  territory.
- Both tools are point-in-time observers; intermittent spikes need a
  recording monitor or scripted sampling, not a human watching a TUI.
- Per-process network attribution on macOS and Windows depends on
  OS-specific socket tables and can be briefly inconsistent during
  connection churn.

## Canonical sources

- bandwhich GitHub repository (imsnif/bandwhich): https://github.com/imsnif/bandwhich
- htop official site: https://htop.dev/
- htop development repository (htop-dev/htop): https://github.com/htop-dev/htop
