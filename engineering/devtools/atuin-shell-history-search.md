# atuin-shell-history-search

**Issue:** Default shell history is a flat, truncated, single-machine text file: it deduplicates badly, caps at a few thousand lines, loses all context about where a command ran and whether it succeeded, and vanishes the moment a laptop does. Engineers respond by re-deriving the same incantations from old tickets and Slack messages, which is pure waste. Atuin replaces shell history with a local SQLite database, a full-screen interactive search with structural filters, and end-to-end-encrypted sync across machines, turning history from a leaky append-only log into a queryable personal knowledge base of every command you have ever run and whether it worked.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Setup and shell integration

1. **Install and run setup.** Install with the official setup script or a package manager, then run `atuin setup`, which detects bash, zsh, or fish and appends the correct shell hook to the rc file. The shell keeps its own history file untouched, so rollback is trivial.
2. **Import existing history first.** Run the import command once during setup to pull the current shell history file into the database. Old faithful one-liners survive the migration instead of starting from zero.
3. **Learn the two modes of integration.** Atuin can fully take over the up-arrow, replacing directory history navigation, or run alongside the default history with only Ctrl+R rebound. Start with the conservative mode, then flip the up-arrow behavior once trust is established.
4. **Verify Windows and Git Bash behavior.** Atuin supports Windows and works in Git Bash-based setups, but the binding and hook behavior differs slightly per shell; confirm the keybinding fires in your exact terminal before assuming the install worked.
5. **Check the database location.** History lives in a SQLite file under the Atuin config directory. Knowing the path matters both for backups and for the occasional direct SQL investigation of your own habits.

## Search mastery

1. **Use the full-screen UI.** Ctrl+R opens an interactive list showing each command with its duration and time-ago, Tab edits the selected command before running, and Enter runs it. The edit-first habit alone prevents a quarter of re-run mistakes.
2. **Filter by exit code.** Prefixing a query with exit code filters, such as searching for failures, answers "what was that command that errored yesterday" instantly, which plain-text history cannot do at all.
3. **Filter by directory and host.** Queries can be scoped to the current directory or a specific machine, so the search for "that docker command from the services repo" returns the one you ran there, not every docker command ever typed.
4. **Filter by duration and session.** Long-running commands and per-session views narrow "that build that took nine minutes" or "everything I ran during the incident at 3am" into one search.
5. **Combine filters in one query.** Text, directory, exit status, and duration compose in a single search, which is the difference between a history tool and a database you happen to type into.

## Sync strategy

1. **Understand the encryption model.** History is encrypted client-side before sync; the server, whether hosted or self-hosted, stores ciphertext it cannot read, and keys never leave the client. This design is what makes cloud history acceptable for work machines.
2. **Self-host when policy requires.** The sync server is open source, and the current Rust-based server ships as a single binary usable with SQLite or Postgres. Setting `sync_address` to your own instance keeps even ciphertext inside infrastructure you control.
3. **Register machines deliberately.** Each machine registers against the same account and is granted its own key; document which machines are enrolled, because an unmanaged laptop with full history sync is a quiet exfiltration path.
4. **Set the sync cadence.** Configure sync frequency so a command typed on the desktop is findable from the laptop without manual syncs; the default interval is short enough for daily work but worth confirming.
5. **Plan for protocol migrations.** The move to the newer sync protocol required re-registering clients, and future protocol changes may follow the same path. Treat "my history stopped syncing" as a possible protocol-version issue, not data loss.

## Privacy and secrets handling

1. **Keep dangerous commands out of history.** Commands containing inline passwords or tokens should be excluded from recording, either via the history filter configuration or by prefixing where supported. Encrypted sync protects transport, not the mistake of recording a secret at all.
2. **Configure history filters up front.** Set filter patterns for known-bad patterns like export commands with credentials, curl calls with bearer tokens, and database URLs with passwords, on day one rather than after the first leak.
3. **Decide work versus personal boundaries.** Syncing work history to a personal account, or vice versa, is a policy decision best made consciously with separate accounts or a self-hosted work instance.
4. **Prune when needed.** Individual history entries can be deleted, and the database is yours; a periodic purge of one-off secrets buys peace of mind even with filters in place.

## Productivity extensions

1. **Review your stats.** The stats command summarizes most-used commands, which is a data-driven prompt to alias the top ten. Most people discover two or three aliases they should have made years ago.
2. **Try the AI assistant carefully.** Recent versions ship an optional AI mode opened with a question mark on an empty prompt, which uses shell context such as recent commands, output, and exit codes to suggest the next command, including flagging dangerous ones before they run. It is convenient, but verify any suggested destructive command, and check whether the feature's data handling fits your policy.
3. **Use history for documentation.** Because every command carries exit status and duration, the path to reproducing a setup is now "search the directory, copy what succeeded," which turns onboarding and runbook writing into a copy-paste exercise.
4. **Pair with directory jumping.** Combined with a directory jumper like zoxide, directory-scoped history plus fast navigation reconstructs an entire working context on a new machine in minutes, which is the entire point of syncing it.
5. **Back up the database anyway.** Sync is replication, not backup. A mistaken mass delete on one machine replicates everywhere, so include the local database in normal machine backups.
