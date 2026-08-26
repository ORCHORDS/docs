# msys-gitbash-windows-quirks

**Issue:** Git Bash (MSYS2-based) on Windows is a POSIX-flavored shell driving native Windows programs, and that mismatch produces two classes of silent failure hit daily while building gmail-mcp-connector. First, shell functions and aliases shadow real coreutils — on this machine a `grep` function installed by the CLI tooling redirects to ugrep 7.5.0, whose flags differ from the GNU grep that scripts expect. Second, the MSYS runtime silently rewrites arguments that look like POSIX paths before handing them to native executables: a pattern like `^/foo` reaches the program as `^C:/path/to/project so anchored-regex greps fail with no error at all. On top of both: commands an agent emits for the HUMAN to paste must be PowerShell syntax, because the user's interactive shell is not the agent's Git Bash.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Shadowed coreutils: when `grep` is not grep

1. **Functions and aliases beat PATH lookup.** Bash resolves a command name through functions and aliases before touching `$PATH`, so a `grep()` function in a startup file invisibly replaces `/usr/bin/grep` for every interactive invocation. Verified on this machine: `type grep` reports `grep is a function` (installed by the CLI tooling) that delegates some flag forms to real grep and otherwise routes to ugrep.
2. **Different tool, different dialect.** `grep --version` here prints `ugrep 7.5.0 WIN64 +sse2; -P:pcre2jit; ...` while `command grep --version` prints `GNU grep 3.0`. Flag semantics differ (`-P`, `--ignore-files`, exit codes on binary files), so a command that "works" interactively can behave differently than documented GNU grep — or vice versa.
3. **`command grep` is the bypass.** `command <name>` skips functions and aliases and goes straight to PATH resolution. `command grep -c '^GET' access.log` guarantees GNU grep regardless of what the shell layer injects; `\grep` (backslash) and `enable -n grep` are weaker or more invasive alternatives.
4. **Diagnose with `type`, not vibes.** When a coreutils command behaves oddly, `type grep` (or `type -a grep` for all candidates) immediately reveals shadowing — one second of diagnosis beats an hour of misreading flag documentation.

## Silent MSYS argument path conversion

1. **The rule.** When a native Windows executable (node.exe, python.exe, cmd's children) is invoked from MSYS2/Git Bash, the runtime converts arguments that look like POSIX paths into Windows paths. Per the [MSYS2 filesystem docs](https://www.msys2.org/docs/filesystem-paths/), this also applies to `--opt=/foo` values and rewrites POSIX path lists (`/a:/b`) into `;`-separated Windows lists.
2. **Measured on this machine (2026-08-15),** invoking node.exe with test args: `/foo` arrived as `C:/path/to/project `/api/routes` likewise gained the Git-install prefix; and — the nasty one — `^/foo` arrived as `^C:/path/to/project because the converter rewrites the path-looking portion even behind a regex anchor character.
3. **Why anchored patterns fail silently.** `grep '^/api' server.log` therefore searches for a line starting with `C:/path/to/project — matches nothing, exits 0 (or 1), prints no error. The command "succeeds"; the answer is just wrong. Any leading-slash argument to a native program (URL paths, regex patterns, REST route strings) is a conversion candidate.
4. **Double slash is the exception.** `//server/share` passed through unchanged in the same test — MSYS treats leading `//` as a UNC path and leaves it alone, which is why Git Bash documentation recommends `cmd //c` style doubling as an ad-hoc escape.

## Controlling conversion

1. **`MSYS2_ARG_CONV_EXCL`.** Per the [MSYS2 docs](https://www.msys2.org/docs/filesystem-paths/), set it to `*` to exclude every argument from conversion, or to a `;`-separated list of prefixes matched against the whole argument string. Verified here: with `MSYS2_ARG_CONV_EXCL='*'`, `/foo` arrives as `/foo`; with `MSYS2_ARG_CONV_EXCL='^/'`, `^/foo` arrives intact — prefix matching is how you protect a specific pattern shape instead of everything.
2. **`MSYS_NO_PATHCONV=1`.** Git for Windows (not upstream MSYS2) honors this variable to disable conversion for a single command: `MSYS_NO_PATHCONV=1 npm.cmd /flag`. Useful when you cannot enumerate prefixes.
3. **`MSYS2_ENV_CONV_EXCL`.** The same conversion applies to environment variables crossing into native programs; this variable excludes them (same `*` or prefix-list semantics, matched against `KEY=VALUE`).
4. **`cygpath` for explicit conversions.** When you NEED a Windows path (`cygpath -w /foo`) or a POSIX one back (`cygpath -u 'C:\foo'`), do it deliberately instead of relying on the implicit heuristic — explicit conversion is testable, implicit conversion is a trap.

## Agent shell vs user shell

1. **The agent's shell is not the user's shell.** ZCode/agents here run Git Bash, but the human's default Windows terminal is PowerShell. A command the agent verifies in Git Bash will fail when pasted into PowerShell — different quoting, no `/c/...` paths, different wildcard expansion, and `grep` may not exist at all.
2. **Emit user-facing commands in PowerShell syntax.** Anything meant for the human to paste must be translated: `node C:\path\to\dist\index.js` (backslashes, no quotes needed), `Get-Content log | Select-String pattern` or an explicit `findstr`, `$env:VAR = "value"` for environment variables. Keep bash syntax for commands the agent itself will execute.
3. **State which shell a command targets.** In instructions and docs, label command blocks (`# PowerShell` / `# Git Bash`) — the fastest way to deconfuse a failing paste is knowing which interpreter was assumed.

## Diagnosis checklist

1. **`type <cmd>`** — is it a function/alias shadowing the binary you think you're running?
2. **`command <cmd> --version` vs `<cmd> --version`** — do they identify as different tools?
3. **Echo the argv the program actually receives** — `node -e "console.log(process.argv.slice(1))" <suspicious args>` shows conversion verbatim; this is how every claim above was verified.
4. **Try `MSYS2_ARG_CONV_EXCL='*'` on the failing command** — if it starts behaving, conversion was the culprit; then narrow to a prefix exclusion instead of leaving the blanket on.
