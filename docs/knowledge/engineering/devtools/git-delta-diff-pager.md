# git-delta-diff-pager

**Issue:** Code review in the terminal defaults to wall-of-text diffs: no syntax highlighting, line numbers you count by hand, hunks that are hard to jump between, and merge conflicts rendered as an unreadable triple-striped mess. Tools like lazygit and lazydocker (already documented in this knowledge base) shell out to git's pager, so the pager determines the readability of everything you review. delta (dandavison/delta) is the 2025-2026 standard answer: a Rust-based, syntax-highlighting pager for git diff, grep, and side-by-side output that drops in as `core.pager`, styles deletions/additions line-by-line, adds file/hunk navigation, and renders `diff3` conflict markers readably. This article covers setting it up on Windows Git Bash, the configuration that pays for itself daily, and integrating it with the rest of a terminal-centric workflow.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Installation and basic wiring

1. **Install the binary.** On Windows use `winget install dandavison.delta` or scoop (`scoop install delta`); on macOS `brew install git-delta`; on Linux use the distro package or the prebuilt release binary. Verify with `delta --version` — a single static binary, no runtime, so it works identically inside Git Bash, WSL, and CI-less laptops.
2. **Wire it as git's pager.** The canonical gitconfig block: set `core.pager = delta`, set `interactive.diffFilter = delta --color-only` so interactive rebase output stays machine-parseable while still colored, and set `merge.conflictstyle = diff3` so conflicts carry the original text (see the conflicts section below). Everything else is delta-side options.
3. **Terminal color support is a prerequisite.** delta emits 24-bit color; Windows Terminal, WezTerm, and iTerm2 handle it natively. The legacy `conhost` console renders colors poorly — if diffs look muted or wrong in Git Bash, check the terminal app first, not delta's theme.
4. **One pager, many callers.** Beyond `git diff/log/show`, delta highlights `grep` output piped through it (`rg pattern | delta --grep`) and works as the blame/diff renderer inside lazygit — a June 2025 writeup on lazygit+delta integration documents wiring `pager` in lazygit's config so its diff pane gets full delta styling.

## The configuration that matters daily

1. **navigate = true.** Adds n/N-style bindings to jump between file and hunk headers in the pager; hunk headers become hyperlinked jump targets. This single option converts diff scrolling from linear reading to targeted navigation.
2. **side-by-side = true (with a caveat).** Renders old/new columns adjacently — excellent for wide terminals, unusable at 80 columns. Pair with `line-numbers = true` (with `line-numbers-left-style`/`right-style` tuned) and `max-line-distance` for better hunk grouping; toggle per-session with delta's pager commands when the terminal is narrow.
3. **Themes are file-based and composable.** `delta --list-syntax-themes` shows bat-powered themes (Nord, GitHub, Monokai Extended...); set one in gitconfig (`[delta] theme = Monokai Extended`) or use `dark`/`light` with `syntax-theme` per terminal background. Custom `.tmTheme` files work since delta reuses bat's syntax engine — any Sublime theme is drop-in.
4. **Hunk headers carry function context.** Default hunk headers show the enclosing function/regex context; customize with `hunk-header-style` (e.g. `file line-number`) to keep file + line visible even when jumping, and `file-style` options control the commit-line decoration above each file. The DEV writeup on running delta without headings covers stripping them entirely for minimalists.
5. **Keep raw modes raw.** When scripting diffs, delta must be out of the pipe: use `git --no-pager diff` or `git diff | cat` in scripts — a colored, line-numbered pager breaks parsers. This matters for this repo's commit-message generator and any automation reading diff text.

## Merge conflicts and difftastic mode

1. **diff3 conflict style is the unlock.** With `merge.conflictstyle = diff3`, conflicts include the base version, and delta renders the three sections with distinct styling so you can see what each side changed relative to the original — dramatically faster conflict resolution than the default two-way markers.
2. **delta handles merge output too.** During `git mergetool`-less resolution, `git diff --cc` and conflict hunks get syntax highlighting; combined with `side-by-side` you can read a conflict like a review instead of archaeology.
3. **Experimental difftastic-style rendering.** Recent delta versions integrate difftastic's syntax-aware diffing (`features = difftastic` behind the appropriate side-by-side settings), which aligns moved code and ignores whitespace-level churn. Worth evaluating, but keep it feature-flagged — some teams prefer classic diffs for review parity.

## Craft and maintenance notes

1. **Share the config through dotfiles.** The delta block lives in `.gitconfig`, which belongs in the chezmoi/stow-managed dotfiles (see this repo's dotfiles article) — pager configuration is a team-experience item even though it is per-user.
2. **Performance is a non-issue but be aware of huge diffs.** delta is Rust and fast; the only lag case is coloring multi-thousand-line generated-file diffs. `git diff --stat` first, then diff specific paths; `file-modified-label` decorations help confirm you are reading what you think you are.
3. **Verify colors survive pipelines.** `git -c core.pager=cat diff | less -R` style escape hatches exist when delta mangles a specific tool's output; conversely remember `--color-only` when delta must not reformat (rebase todo lists, diffs consumed by other tools).
4. **Prefer delta over per-tool theming.** lazygit, tig, and gh CLI all get consistent highlighting by delegating to delta instead of each maintaining its own diff theme — one theming decision everywhere.

## Related

1. **Adjacent repo articles.** `lazygit-patterns.md` and `lazydocker-patterns.md` for the TUI tools that delegate to delta; `git-interactive-rebase.md` for why `interactive.diffFilter` matters; `dotfiles-management-chezmoi-stow.md` for shipping the gitconfig block.
2. **Primary sources.** The dandavison/delta README (canonical gitconfig block, options tables), the delta man page (delta.1), and the June 2025 lazygit integration post on lorenzobettini.it ground the specifics above.
