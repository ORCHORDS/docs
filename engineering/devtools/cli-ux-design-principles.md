# cli-ux-design-principles

**Issue:** Internal CLI tools accrete: one uses `--flag`, another `-flag`, another positional soup. Output mixes data with progress spinners so nothing pipes cleanly, exit codes are all `1` so scripts cannot branch on them, and `--help` exists on half the subcommands. The canonical modern reference is clig.dev (Command Line Interface Guidelines), and following it makes tools that humans can guess and scripts can trust.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Flags, arguments, and conventions

1. **Obey POSIX syntax.** Short flags bundle (`-abc` = `-a -b -c`), take values as `-f value` or `-fvalue`, long flags use two dashes and `--flag=value`, and `--` terminates flag parsing so filenames that start with `-` are safe. Single-dash long options (`-verbose`, tar-style) are the classic anti-pattern — new tools should not copy 1970s accidents.
2. **Provide `--help` and `--version` everywhere, always.** Help must work on every subcommand (`app deploy --help`), exit 0, print to stdout when asked for explicitly, and show real usage examples — not just a flag list. A subcommand without help is an undocumented API.
3. **Choose between flag and positional by requiredness.** Required inputs are positional and few (one, maybe two); optional behavior is flags. If you have more than two positionals, or users must remember their order, redesign — `app copy SRC DEST` is fine, `app do a b c d` is not.
4. **Never overload or invent conflicting reserved flags.** `-v` cannot mean verbose in one subcommand and version in another; `-h` is help, `-q` is quiet, `-n` is dry-run by widespread convention. Consistency with the ecosystem beats internal cleverness.
5. **Make configuration a documented precedence chain.** Flags override env vars, env vars override config file, config file overrides defaults — printed in `--help` so users can debug "why is my setting ignored". Support `NO_COLOR` (and `CLICOLOR_FORCE` for forced piping) — it is the accepted standard for disabling ANSI output.

## Output streams and modes

1. **stdout is data; stderr is everything else.** The pipelinability of your tool depends on this single rule: diagnostics, progress, warnings, and "next steps" hints go to stderr, so `app list | jq` works. Mixing them forces users into `2>/dev/null` archaeology.
2. **Ship a machine-readable mode from day one.** `--json` (or `--output json|yaml|table`) costs little to add initially and is nearly impossible to retrofit once humans parse your formatted tables. JSON output should be one object per line (JSONL) for streamability, stable field names, and documented as a contract.
3. **Offer `--quiet` and `--verbose` as ranges, not booleans.** `-q` suppresses non-essential output (still errors to stderr), `-v`/`-vv` increase diagnostics. A tool with no volume control is either useless in pipelines (too chatty) or useless in debugging (too silent).
4. **Detect TTY and degrade gracefully.** Spinners, progress bars, and animated output belong only on an interactive terminal: check `isatty(stdout)` (or your framework's equivalent) and fall back to plain, unanimated, periodic line output when piped or when `CI=true` is set. CI logs full of `\b`-backspace garbage are a badge of carelessness.
5. **Long operations owe the user progress.** Anything beyond ~2 seconds shows what is happening and, when enumerable, how far along (bytes, items, percent) with an ETA. Indeterminate spinners are the floor; silence makes users assume a hang and press Ctrl-C at 95%.

## Errors and exit codes

1. **Exit 0 if and only if the program succeeded.** This is the scripting contract: nonzero means failure, always — never "exit 1 on success with warnings" and never "exit 0 after printing an error". Everything from `set -e` shells to `git bisect run` and `xargs` is built on it.
2. **Differentiate exit codes by cause.** The common convention: `2` for usage errors (bad flags, missing arguments), `1` for runtime failures; many tools reserve `130` for SIGINT death and document codes for auth/network/not-found. Distinct codes let wrappers retry transient failures and halt on usage bugs.
3. **Errors are for humans: say what happened, why, and what to do.** `Error: port 4114 already in use (pid 3821). Try 'app stop' or pass --port.` beats `EADDRINUSE` a hundred times over. Include the underlying cause (errno, HTTP status, response snippet) and the likely fix; suggest the exact next command when one exists.
4. **Fail fast on bad input, and say which one.** Validate arguments before doing work, and report all detectable problems in one pass rather than making the user fix them one error per run. Nothing is more hostile than a five-round trip to typo-check five flags.
5. **Preserve stderr/stdout discipline on error paths too.** An error dump that accidentally goes to stdout corrupts the very pipelines your JSON mode serves; frameworks that route errors correctly (see below) are worth adopting precisely because hand-rolled prints drift.

## Lifecycle, robustness, and implementation

1. **Make mutations idempotent and offer `--dry-run`.** Re-running a command should converge (create-if-missing, upsert) rather than duplicate; destructive or slow operations print what they *would* do under `--dry-run` and skip confirmation with `--yes` for automation. Interactive confirmation only ever happens on a TTY.
2. **Respect Ctrl-C as a first-class exit path.** Catch SIGINT, clean up temp files and partial state, restore the terminal (cursor, colors), and exit 130. A tool that leaves the terminal mangled or a half-written lock file teaches users to fear it.
3. **Let a framework enforce the conventions.** clap (Rust), cobra (Go), and commander/oclif/yargs (Node) implement help generation, flag parsing, subcommand dispatch, shell completion, and exit-code plumbing for you; hand-rolled argv parsing is where POSIX violations are born. Choose the framework whose ecosystem you already ship in.
4. **Test the CLI like an API.** Golden-file tests for `--help` and `--json` output, assertions on exit codes per failure mode, and a TTY-less CI run that would catch spinner leakage — all cheap in CI, and the only way the contracts above stay true after refactors.
5. **Design for ten-minute adoption.** A new user should go from `app --help` to a successful first invocation without reading docs: sensible defaults, one canonical example in help, and an actionable error for the first wrong turn. The best internal CLIs are measured by how rarely someone asks the author how to use them.

## Related

- jq-json-processing (the downstream half of `--json` output)
- just-task-runner (where these conventions meet task runners)
