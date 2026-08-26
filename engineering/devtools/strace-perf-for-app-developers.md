# strace-perf-for-app-developers

**Issue:** The app behaves differently on the Linux box than locally: "file not found" for a file that is visibly there, permission denials with no audit trail, DNS resolving to the wrong IP, or a startup that crawls with no log output. Application logs stop at the process boundary; the answer is in the syscalls. strace shows what the program asked the kernel, perf shows where the cycles went — two different questions, two different tools.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## strace first aid

1. **Start with `strace -f -e trace=file ./app`.** `-f` follows child processes and threads (most real failures happen in a helper the parent spawns), and filtering to file syscalls removes the read/write noise of normal operation. For network mysteries swap in `-e trace=network`; for fork/exec chaos `-e trace=process`.
2. **Decode descriptors with `-y` (and `-yy` for sockets).** `-y` annotates every read/write with the path the fd points at — instantly answers "which of the five config files did it actually read?". `-yy` goes further and maps socket fds to local/remote addresses so you can see which peer each write went to.
3. **Attach to an already-running process with `strace -p <pid>`.** You do not need to restart a wedged service to see what it is doing; combining `-p` with `-f` and a filter keeps the firehose manageable. Run under `sudo` if the process runs as another user.
4. **Use `-c` for the summary view.** `strace -c ./app` prints a per-syscall count/error/total-time histogram — one screen that reveals "98k futex calls" or "stat called 40,000 times at startup" without reading a single line of trace.
5. **Know that strace slows the target, sometimes brutally.** ptrace-based tracing can slow syscall-heavy programs by 10-100x. It is a correctness tool ("what happened"), never a benchmarking tool — any timing you observe under strace is fiction; use perf for performance questions.

## The classic diagnoses

1. **ENOENT hunts: read the path list, not the error.** With `-e trace=file`, the lines immediately before the failure show every candidate path the app tried (`/etc/app.conf`, `./app.conf`, `$HOME/.apprc`...). The bug is usually a missing `chdir`, a wrong `HOME`, or a container working directory — visible in one glance.
2. **EACCES with context.** The openat line shows the exact path and flags; add `-y` to correlate later fd operations. Pair the trace with `namei -l /path/to/file` (or read the mode bits in the trace) to see *which* path component denied traversal — the classic missing execute bit on a parent directory.
3. **Wrong network destination.** `connect()` lines show the actual address the process dialed; when DNS or `/etc/hosts` lies, you see it here — no amount of `curl` reproducibility proves what *your* process resolved. Compare against the resolver config the process sees (it appears in the openat stream).
4. **The real argv/env of a process you did not start.** The `execve("/usr/bin/node", ["node", "server.js"], 0x7ffd... /* 60 vars */) = 0` line is ground truth for "which script/binary actually ran" and, with the full env dump (strace prints it under `-s 4096` or with `-v`), for "was the env var set". Debugging systemd-launched or container-exec'd processes starts here.
5. **Library and locale load failures.** A stream of failed `openat`s on `lib*.so` paths or locale archives before a crash identifies missing runtime packages on a minimal/base image — the difference between "works on my fat image, dies on distroless".

## perf without becoming a kernel engineer

1. **`perf stat` is the one-screen overview.** `perf stat ./app` (or `-p <pid>`) prints CPU cycles, context switches, page faults, and branch misses. A high context-switch rate or fault count points at an I/O or memory behavior problem before you profile a single stack.
2. **`perf record -g` + `perf report` for hot paths.** `-g` captures call graphs; `perf record -F 999 -g -- ./app` samples at 999Hz with negligible overhead relative to strace, and `perf report` browses the stacks. If stacks look truncated, record with `--call-graph dwarf` (DWARF-based unwinding; larger data, but works where binaries were built without frame pointers).
3. **On-CPU is only half the story.** Flame graphs of on-CPU time miss blocked time — for many server apps the majority of latency is off-CPU (waiting on locks, disk, network). Off-CPU analysis (wakeups and latency via eBPF-based tools like bcc/bpftrace) is the complement; if CPU is idle and the app is slow, stop profiling cycles and start measuring sleep.
4. **Read flame graphs as width, not height.** In a Brendan Gregg flame graph, a frame's horizontal width is the share of samples it was on the stack — scan for the widest plateaus, click to zoom. The workflow is three steps: `perf record -g`, collapse stacks (`stackcollapse-perf.pl`), render (`flamegraph.pl > out.svg`).
5. **escalation ladder: strace -> perf -> eBPF.** strace answers "what syscalls" on any box with no setup; perf answers "where did cycles go" with kernel counters and symbols; bpftrace/BCC answer custom questions ("who is blocking this futex", "what is the latency distribution of this syscall") in production without stopping the process. Each level needs more privileges and setup — climb it only as far as the question requires.

## Rules of thumb that prevent wasted days

1. **Match the tool to the question.** "Did it even try to open the file?" — strace. "Why is it slow?" — perf. "Where is this value corrupted?" — a debugger (or time-travel recording). Using strace to answer a performance question gives you a slowed-down system and a screenshot of the wrong timeline.
2. **Reproduce under the same identity and cwd as the failing run.** Permission and path failures are user/cwd-dependent; run strace as the same user (`sudo -u appuser strace ...`) from the same working directory or the trace lies by omission.
3. **Increase string size before concluding data is missing.** Default tracing truncates strings at 32 bytes; `-s 128` (or `-v` for full env) prevents "the path looks cut off" misdiagnoses. Verdicts on truncated output are how teams fix the wrong bug twice.
4. **Save the trace, not a screenshot.** `strace -o /tmp/app.strace` (and `perf record -o /tmp/app.perfdata`) leaves an artifact attachable to the ticket; a pasted fragment without timestamps (`-tt -T` for syscall durations) is unreproducible folklore an hour later.
5. **On Windows/MSYS you do not have these — plan accordingly.** strace/perf are Linux-only; the Git Bash environment on Windows cannot run them. For production diagnosis, capture the trace inside WSL2, the container, or the Linux host where the process actually runs, then analyze the text output anywhere.

## Related

- time-travel-debugging-rr (causal "how did state get here" questions)
- node-cpu-flame-graph-profiling (the Node-specific profiling path)
