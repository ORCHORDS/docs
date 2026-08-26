# file-watcher-performance-watch-mode

**Issue:** Nearly every modern dev tool — bundlers, test runners, dev servers, the watch-mode skills in this repo — depends on file watching, and when watching is misconfigured the symptoms are confusing and expensive: editors and rebuilds burn CPU at idle, `EMFILE: too many open files` crashes the watcher on Linux, changes made inside a VM or Docker container never trigger a rebuild, or a save triggers three redundant rebuilds. File watching is not one mechanism but three (kernel event queues, recursive watchers, and polling) with radically different cost profiles per platform, so tuning it requires understanding which layer your tool actually uses. This article captures how watch mode works across Node.js tooling as of 2025-2026, how to diagnose watcher pressure, and how to configure the right backend for Windows, WSL, macOS, and CI.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How file watching actually works

1. **Kernel event APIs are the fast path.** Node's `fs.watch` delegates to `inotify` on Linux, `FSEvents`/`kqueue` on macOS, and `ReadDirectoryChangesW` on Windows. The kernel pushes events instead of the process scanning the disk, so an idle watcher costs nearly zero CPU. Everything else (chokidar, Vite, Turborepo, Jest) is a normalization layer over these APIs.
2. **Linux has no recursive inotify.** `fs.watch` supports recursive watching on macOS and Windows, but on Linux a watcher must be opened per directory — a large repo with deep `node_modules` can blow past the `fs.inotify.max_user_watches` sysctl and start silently dropping events. Raise it (`sysctl fs.inotify.max_user_watches=524288`) or exclude directories from watching entirely. Node issue nodejs/node#36005 tracks the missing recursive support.
3. **Polling is the compatibility fallback, not a default.** `usePolling` (chokidar) or `fs.watchFile` stat-scan the tree on an interval. It works on NFS, network drives, and some Docker/WSL mounts where kernel events never arrive, but a polling watcher on a big tree is a CPU space heater — stat calls every few hundred milliseconds across tens of thousands of files. Enable it surgically for the broken path only, never globally.
4. **Chokidar v4 is the current baseline.** Released September 2024, v4 dropped glob support and the bundled fsevents dependency, cutting the dependency count from 13 to 1 and rewriting in TypeScript. Migration note: pass explicit directories or resolve globs yourself before handing paths to chokidar. Most of the 2025-2026 toolchain (Vite 6/7, Vitest,tsx watch) has migrated; the lower supply-chain surface is itself a security win.

## Diagnosing watcher pressure

1. **Count open inotify watches on Linux.** Parse `/proc/sys/fs/inotify/max_user_watches` against actual usage (`find . -type d | wc -l` approximates worst case for non-recursive watchers). Hitting the ceiling produces `ENOSPC` errors or, worse, watchers that silently miss events.
2. **Check EMFILE limits on macOS.** Per-directory watchers each consume a file descriptor; deep trees exhaust `ulimit -n` (default 256 on some setups). Raise the limit in the shell profile or reduce watched scope.
3. **Profile idle CPU.** Run the watcher, touch nothing, and watch CPU with `bottom` or Task Manager. Anything above a few percent at idle means polling is active somewhere — hunt down the `usePolling` or `watchOptions` setting responsible.
4. **Distinguish missed events from slow rebuilds.** Use `strace -f -e trace=inotify_add_watch` (Linux) or Sysinternals Process Monitor (Windows) to confirm the watcher actually registered for the directory you are editing. If events arrive but nothing rebuilds, the problem is the tool's debounce queue, not the OS.

## Platform-specific fixes (Windows and WSL focus)

1. **Never watch across the Windows/WSL boundary.** Files edited by Windows tools inside a WSL filesystem mount (or vice versa) do not reliably emit inotify events. Keep the project and the editor on the same side of the boundary; this is the single most common "my watch mode doesn't trigger" report on Windows dev setups.
2. **Exclude noise directories everywhere.** Configure ignored paths (`node_modules`, `dist`, `.git`, `coverage`, `screenshots`) in the tool's watch options — Vite's `server.watch.ignored`, Jest's `watchPathIgnorePatterns`, VS Code's `files.watcherExclude`. Exclusion is cheaper than raising watcher limits because the watchers are never created.
3. **Docker Desktop on Windows needs polling or delegation.** Bind-mounted source from the Windows filesystem into a Linux container cannot propagate inotify events. Either enable polling inside the container for the source mount, or keep source inside the container filesystem and sync it, or run the watcher on the host and only run the app in the container.
4. **Prefer binary targets on Windows.** .NET's `FileSystemWatcher` (used by many .NET tools) wraps `ReadDirectoryChangesW` and can drop events under heavy load with an `Error` event — handle it by rebuilding the watch tree rather than assuming reliability.

## Scaling to very large monorepos

1. **Use a watcher daemon above ~50k files.** Meta's Watchman runs as a persistent daemon that maintains one watch tree for all clients, deduplicates crawls, and survives client restarts. Node clients connect via `fb-watchman`. It is the standard answer when per-process chokidar instances each re-crawl the same giant tree.
2. **Scope watchers to changed workspaces.** In a pnpm monorepo like this repo, point test watchers at affected packages rather than the root; `vitest --watch` in one package beats a root watcher that re-evaluates the whole graph.
3. **Debounce and batch at the consumer.** Editors firing multiple saves per second and formatters rewriting files produce event storms; ensure the tool aggregates events within a window (chokidar's `awaitWriteFinish`) so one logical save equals one rebuild.
4. **Verify before blaming the watcher.** A "watch mode is broken" bug is as often a stale process holding the port or an output cache serving old bundles. Kill the watcher, run once in non-watch mode, and compare before filing a bug against chokidar.

## Related

1. **chokidar v4 migration and internals.** The paulmillr/chokidar README and the Vite chokidar-v4 adoption issue (vitejs/vite#18129) document the glob removal and fsevents changes.
2. **Existing repo articles.** See `bottom-system-monitor.md` for idle-CPU profiling, `msys-gitbash-windows-quirks.md` for the Windows shell context, and `sysinternals-procmon-procexp.md` for event-level filesystem tracing on Windows.
