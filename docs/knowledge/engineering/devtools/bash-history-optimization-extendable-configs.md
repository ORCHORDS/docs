# Bash History Optimization Extendable Configs

Bash ships with a history facility that is nearly useless in its default
configuration: it forgets most of what you typed, records duplicate
after duplicate, overwrites itself across terminals, and stores neither
timestamps nor exit status. Every one of those deficits is a settings
problem, not a shell limitation. With the right variables in
`.bashrc`/`.bash_profile`, bash keeps a large deduplicated history
appended from every open terminal, timestamped and re-loadable on any
machine. This is the cheapest developer-tooling improvement that
exists: ten lines of configuration that compound for years.

## Scope

Configuring GNU Bash history behavior for interactive developer use:
which shell variables control size, deduplication, append semantics, and
timestamping; how to structure the rc files so the configuration
survives across machines; and the interaction with Ctrl+R search and
history expansion. Not covered: replacing bash history with a database
tool such as Atuin, or zsh/fish equivalents.

## Workflow or implementation guidance

1. **Raise the retention limits.** Two variables cap history: the
   in-memory list (`HISTSIZE`) and the on-disk file (`HISTFILESIZE`).
   Defaults are tiny; set both to the same large number so nothing is
   silently truncated at exit:

   ```bash
   HISTSIZE=100000
   HISTFILESIZE=100000
   ```

2. **Enable append, disable overwrite.** The single most destructive
   default is that each exiting shell truncates the file with its own
   copy of the list. Setting `histappend` makes every shell add its
   session to the file instead, so parallel terminals stop erasing each
   other:

   ```bash
   shopt -s histappend
   ```

3. **Deduplicate and control what is recorded.** `HISTCONTROL` accepts
   a colon list; the two settings that matter are `ignorespace`, which
   skips commands prefixed with a space so secrets typed as
   ` export TOKEN=...` never land on disk, and `erasedups`, which
   removes older copies of a command when it is recorded again:

   ```bash
   HISTCONTROL=ignoreboth:erasedups
   ```

   Complement it with `HISTIGNORE` for commands that never earn a
   history slot: `ls*`, `pwd`, `clear`, `exit`, and frequent noisy
   prefixes such as `cd ..`.
4. **Record timestamps and shape the file format.** `HISTTIMEFORMAT`
   stamps every entry, which also changes the file to a
   `#<epoch>`-comment format that survives reordering:

   ```bash
   HISTTIMEFORMAT='%F %T '
   history          # now prints date and time per entry
   ```

   Optionally set `HISTFILE` to a non-default path so dotfile managers
   can symlink it, and `HISTSTAMPS`-style extras stay out of
   non-interactive contexts where the variables do nothing.
5. **Flush history immediately.** By default a command is written when
   the shell exits, which a crashed terminal never reaches. Two options
   exist: `PROMPT_COMMAND='history -a; history -n; '"$PROMPT_COMMAND"`
   appends each new entry and re-reads others' entries at every prompt,
   keeping concurrent terminals roughly in sync; or bind it explicitly
   if you need ordering guarantees. This one line is what makes
   "history from the other window" actually findable.
6. **Make the configuration extendable.** Keep the block in its own
   sourced file (`~/.config/bash/history.sh`) invoked from the rc, with
   a comment header per variable. New machines get the whole block by
   symlink or dotfile manager, and the team can add project-scoped
   `HISTIGNORE` entries without touching the core. Guard interactive
  -only settings with `case $- in *i*) ;; *) return ;; esac` so
   sourcing from scripts is harmless.
7. **Learn the retrieval side.** `Ctrl+R` incremental search is the
   daily interface; press it repeatedly to cycle matches, and use
   `!$` (last argument), `!!` (last command), and
   `history | grep <fragment>` for the rest. `shopt -s histverify`
   makes expanded commands editable before execution — recommended
   before anyone gets confident with `!!`.

## Controls

- **Interactive-only scope.** History variables belong in the
  interactive rc chain (`~/.bashrc` sourced from `~/.bash_profile`),
  never in files sourced by CI or scripts; non-interactive shells
  should keep default behavior.
- **Secret hygiene.** `ignorespace` plus a written team habit — space
  prefix for anything containing a credential — is the minimum;
  add `HISTIGNORE` entries for your credential-wrapping commands. Never
  treat history configuration as a secrets control on its own.
- **File permissions.** `chmod 600` the history file; it is a
  transcript of everything an engineer has run, including hostnames and
  occasionally a pasted token that slipped past the filters.
- **Size review.** Hundred-thousand-entry histories are a few
  megabytes; if the file grows past tens of megabytes, something is
  logging a loop — investigate rather than raise the cap.

## Validation evidence

1. Open two terminals; run distinct commands in each, then run `history
   -n` (or just wait for the next prompt if using the PROMPT_COMMAND
   sync) and confirm both terminals can see the other's commands.
2. Run `echo one`, run it again, and check `history | tail`: with
   `erasedups` active only the latest occurrence appears at the end.
3. Type a space-prefixed command such as ` export SECRET=demo`, then
   inspect the history file with `tail ~/.bash_history`; the entry must
   be absent.
4. Run `history 3` and confirm timestamps print in the
   `HISTTIMEFORMAT` layout, and that the raw file now contains
   `#<epoch>` separator lines.
5. `kill -9` a shell after running a command; with the prompt-command
   flush in place the command still appears in the surviving file,
   proving crash-resilient capture.

## Failure modes and correction

- **History still overwrites across terminals.** `histappend` was set
   in a non-interactive context or after the file was written; confirm
   with `shopt histappend` inside the live shell, and check that the
   setting is not being reset by a later sourced file.
- **erasedups seems to do nothing.** It removes duplicates when the
   entry is recorded, not retroactively; existing duplicates in the
   file remain until re-entered. Clean the file once with `awk '!
   seen[$0]++'` on a backup copy if it matters.
- **Ctrl+R finds nothing recent.** The other shell has not flushed
   (`history -a` not yet run), or `HISTFILESIZE` is smaller than the
   file and truncation happened at load. Compare `wc -l` of the file
   with `HISTSIZE`.
- **Timestamps show as `#` lines only.** The file predates
   `HISTTIMEFORMAT`; entries without a preceding epoch comment are
   treated as belonging to the current session time. Normal going
   forward, unfixable for old entries.
- **Startup slows on huge histories.** Very large `HISTSIZE` with
   `erasedups` makes each prompt do linear work; if prompt latency
   appears, cap size or drop `erasedups` in favor of periodic cleanup.

## Limitations

- Plain bash history has no exit status, duration, directory, or host
  metadata, and no structured search; teams needing those should adopt
  a history database tool rather than extend bash further.
- Ordering across concurrent shells is approximate even with
  prompt-command syncing; interleaving is not a guarantee.
- `erasedups` and `histappend` interact imperfectly: appends can
  reintroduce duplicates that were erased in memory, which is a known
  long-standing behavior of the facility.

## Canonical sources

- Free Software Foundation, GNU Bash Reference Manual, Bash History
  Facilities (HISTSIZE, HISTFILESIZE, HISTCONTROL, histappend):
  https://www.gnu.org/software/bash/manual/html_node/Bash-History-Facilities.html
- Free Software Foundation, GNU Bash Reference Manual, Bash History
  Variables: https://www.gnu.org/software/bash/manual/html_node/Bash-Variables.html
- GNU Readline library, the engine behind interactive history search:
  https://tiswww.case.edu/php/chet/readline/rltop.html
