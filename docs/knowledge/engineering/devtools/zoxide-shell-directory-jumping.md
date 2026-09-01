# zoxide Directory Jumping for Shell Workflows

Time in a terminal is spent navigating: `cd` chains into deep paths, `history | grep`, tab completion through directory trees. zoxide is a smarter `cd`: it maintains a frequency-and-recency-weighted database of every directory you visit and jumps there by fuzzy prefix — `z orch docs` lands in the project you mean. It is one of the highest leverage-per-line tools in a developer's shell, and its value depends on habits that feed it good data and configuration that fits how you work. This article covers zoxide's ranking model, setup across shells, workflow patterns, database hygiene, and team-sharing practice.

## Scope

This article addresses zoxide usage: the weighted-match algorithm's inputs (frequency and recency), installation and shell hook setup (`zoxide init`), the `z`/`zi` commands, database management (`zoxide query`, `add`, prune semantics), integration with fzf interactive selection, and workflow patterns for multi-project engineers. It does not cover fzf generally, shell prompt frameworks, or alternative jumpers (autojump, z.sh) beyond contrast.

## Workflow or implementation guidance

zoxide works in two halves: a hook that records every directory you enter (`cd` into a dir = one `zoxide add`), and a query engine that ranks candidates when you type `z <fuzzy pattern>`. The ranking blends how often you visited and how recently — heavily-used recent directories win over briefly-visited stale ones, so the tool converges on your actual working set without manual curation.

Setup is one hook per shell. In zsh: `eval "$(zoxide init zsh)"`; bash: `eval "$(zoxide init bash)"`; fish: `zoxide init fish | source`; PowerShell and Nushell have their own init commands per the project README. The init defines `z` (jump) and optionally `zi` (interactive selection), plus a `cd` wrapper or hook that records visits. After init, behavior is transparent: every `cd` feeds the database, and `z` reads it.

The commands that matter:

- `z foo` — jump to the highest-ranked directory matching `foo`.
- `z foo bar` — matches directories whose path contains `foo` and `bar` (in order, as path components/segments — pattern is fuzzy over the path string), so `z orch docs` resolves `~/code/orchords/docs` ahead of `~/code/other/docs` if you visit the former more.
- `zi foo` — interactive mode: pipe candidates through fzf and pick; the right tool when the fuzzy pattern is ambiguous or you want to see the ranked list.
- `zoxide query foo` — print ranked matches without jumping (scriptable).
- `zoxide add <path>` — record a path manually (useful for bootstrapping a new machine: replay your project list).

Workflow patterns:

1. **Replace `cd` for known targets, keep `cd` for exploration.** `z` is for places you have been; `cd ../sibling` relative moves and `ls`-driven exploration still have their place. Engineers who force everything through `z` fight it; the tool complements relative navigation.
2. **Seed a new machine from your project list.** Keep a plain text list of canonical project paths in dotfiles (`~/.config/zoxide/seed.txt`); after `zoxide init`, run `zoxide add $(cat ~/.config/zoxide/seed.txt)` so rankings start warm instead of cold. Note the database is machine-local by design (it encodes *your* visiting behavior on *that* machine); sharing the raw database between machines is possible (it's a file) but usually wrong — two different working sets merged produce misleading ranks.
3. **Use `zi` for disambiguation.** When two projects share a prefix (`api` and `api-v2`), interactive selection beats typing more characters; muscle memory becomes `zi api` + one keystroke.
4. **Combine with repo-specific shell entry points.** Many engineers alias `z` targets further — a small `work` function that `z platform` then activates the environment (`direnv` handles per-directory envs automatically, pairing naturally: jump lands, direnv activates). The pairing of a jumper with per-directory environment loading is the modern answer to "project setup scripts".
5. **Prune stale entries by usage, not by age.** The database ages out rarely-visited dirs naturally through ranking decay; you rarely need explicit deletion. When a path was renamed or removed, `z` will fail to `cd` into it once and zoxide drops it (failed jump = pruned entry) — self-healing. For explicit cleanup, `zoxide query` lists ranks; delete entries by re-adding nonexistent paths is unnecessary — trust the model.
6. **Interactive exploration:** `zi` with no pattern lists top-ranked dirs — a serviceable "recent projects" menu for the start of a session.

Configuration flags worth knowing (set via environment variables at init): `--no-cmd` if you want only the hook (define your own alias), `--cmd j` to rename the command if `z` collides with an existing alias, and hook options that control whether the `cd` replacement is installed versus only a `precmd` hook. The defaults are right for most; the main deliberate choice is command name collisions in team-standard shell configs.

A worked example: an engineer across 15 repos daily. Before: `cd ~/work/acme/acme-platform/docs/knowledge/engineering` (or history grepping). After: `z eng know` (or `zi eng` when ambiguous), one command, ranked first because this is their most-visited tree. New junior engineers on the team adopt via the shared dotfiles PR: zoxide init in the standard shell config plus the seed list — day one, their `z` works for the team's canonical repos.

Contrast with the alternatives in one line each: `z.sh`/`autojump` are the lineage zoxide comes from (similar model, slower, less maintained); shell built-in `cd` with `CDPATH` handles a fixed set of roots but not ranking; fzf-over-`find` explores the filesystem but lacks the behavioral ranking that makes jump fast for *your* habits.

## Controls

- Standardize zoxide setup in team dotfiles (init line per shell, chosen command name, seed list of canonical repos); onboarding installs it before first use so rankings warm from day one.
- Keep the seed list (`zoxide add` inputs) in version control as the declarative statement of "our canonical project paths"; the runtime database stays machine-local and disposable.
- Review `zoxide query` top-20 quarterly as a working-set mirror: entries you never visit anymore indicate archived projects (and prompt cleanup of their local checkouts).
- Do not sync or commit the database file itself (`~/.local/share/zoxide/db.zo` by default) — it is behavioral state, not configuration; machines with different working sets corrupt each other's ranks.
- If shells-in-containers or remote sessions are part of the workflow, note that the database does not follow SSH sessions; per-host databases accumulate naturally and that is correct behavior, not a defect to fix.

## Validation evidence

- zoxide's commands (`z`, `zi`, `zoxide query/add/init`), the frequency-recency ranking model, shell setup, environment-variable configuration flags, and database location/aging behavior are documented in the official zoxide README at GitHub (ajeetdsouza/zoxide).
- The fzf integration for interactive selection follows the pipe-through-fzf pattern documented in both projects' READMEs.
- A reproducible demonstration: from a fresh shell with init active, `cd` into three nested project directories a few times each (one visited most recently), then `z <distinctive-substring>` — it resolves the most-visited recent target; `zoxide query <substring>` prints the ranked list showing the ordering — ranking behavior verified in two commands.

## Failure modes and correction

- **Ambiguous prefixes resolving wrong.** Symptom: `z api` lands in the wrong `api-*` repo. Correct by adding one more path segment to the pattern or switching to `zi` for that target.
- **Cold start on new machines.** Symptom: `z` useless in week one. Correct by the seed-list bootstrap from dotfiles.
- **Command-name collision.** Symptom: existing `z` alias (common in oh-my-zsh setups) shadows or is shadowed. Correct with the `--cmd` rename at init.
- **Stale entries after repo renames.** Symptom: jump fails once. Correct by nothing — the failed jump prunes; next `cd` re-adds under the new path.
- **Database syncing between machines.** Symptom: ranks nonsense after copying db files. Correct by not syncing; per-machine databases by design.

## Limitations

- Rankings encode past behavior; a deliberate switch of working set takes some visits to retrain.
- Only directories you `cd` into are known; a project cloned but never entered does not exist to `z` until seeded or visited.
- The database is plaintext-ish local state; on shared machines it reveals directory names you visited (a minor but real confidentiality consideration).
- Windows shell support (PowerShell) exists but integrations and hook reliability vary by shell version.

## Canonical sources

- zoxide project (ajeetdsouza), README — installation, ranking model, commands, configuration: https://github.com/ajeetdsouza/zoxide
- zoxide project (ajeetdsouza), README table of contents — hooks, flags, and shell integration reference: https://github.com/ajeetdsouza/zoxide#table-of-contents
