# git-delta and difftastic — Syntax-Highlighted Visual Diffs

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

`git diff` renders deletions and additions as identical-width walls
of red and green text with no syntax highlighting, no line numbers
in the output, and no sense of where one logical change ends and
another begins. On a 200-line TypeScript function that had three
words renamed, the terminal shows 200 red lines and 200 green lines.
Merge conflicts in `diff3` mode are six-stripe walls of chevrons
that require careful manual annotation before they can be resolved.

## Context

The platform team works heavily in the terminal via lazygit and the
`gh` CLI for PR review. Every diff view — `git show`, `git log -p`,
`git diff HEAD`, lazygit's diff pane — delegates to whatever is
configured as `core.pager`. Two tools address the readability gap:
`delta` (dandavison/delta) is the daily driver for syntax-highlighted
paging and side-by-side view; `difftastic` (Wilfred/difftastic) is
the complement for semantic, AST-level diffing on files where
character-level diffs obscure the real change.

## delta — Installation and gitconfig Wiring

```bash
# macOS
brew install git-delta

# Windows (winget)
winget install dandavison.delta

# Linux (Debian/Ubuntu)
apt install git-delta        # or download from GitHub Releases
```

Minimal `~/.gitconfig` block:

```ini
[core]
    pager = delta

[interactive]
    diffFilter = delta --color-only

[merge]
    conflictstyle = diff3

[delta]
    navigate = true
    line-numbers = true
    side-by-side = true
    syntax-theme = Monokai Extended
    file-style = bold yellow ul
    hunk-header-style = file line-number
```

`interactive.diffFilter = delta --color-only` keeps `git add -p`
machine-parseable while still colorizing the hunk display. Without
it, `--color-only` is absent and interactive staging breaks.

## delta — Key Configuration Options

| Option              | Effect                                       |
|---------------------|----------------------------------------------|
| `navigate = true`   | n/N jumps between file and hunk headers      |
| `side-by-side`      | two-column view (requires wide terminal)     |
| `line-numbers`      | absolute line numbers in each column         |
| `syntax-theme`      | any bat theme; `delta --list-syntax-themes`  |
| `hyperlinks`        | terminal hyperlinks to file:// paths         |

```bash
# Toggle per-session for narrow terminals
git diff | delta --side-by-side=false
```

## difftastic — AST-Level Semantic Diffing

difftastic parses source files into an AST using Tree-sitter
grammars, then diffs the tree rather than the text. A variable
rename that touches 30 lines shows as one structural change. A
whitespace-only reformat shows as empty diff.

```bash
# macOS
brew install difftastic

# Linux
cargo install difftastic   # or grab the GitHub release binary
```

Wire as `diff.external` to use on demand without replacing delta:

```ini
[diff]
    tool = difftastic
[difftool "difftastic"]
    cmd = difft "$LOCAL" "$REMOTE"
[alias]
    dft = difftool --tool=difftastic --no-prompt
```

```bash
git dft HEAD~1
# or per-command: GIT_EXTERNAL_DIFF=difft git show abc1234
```

difftastic replaces the diff computation rather than paging output,
so it cannot be layered with delta. Choose per-session by change type.

## lazygit Integration

lazygit delegates its diff pane to `core.pager`. With delta wired
in `~/.gitconfig`, the diff pane inherits full syntax highlighting
and line numbers with no extra config. For difftastic on demand,
add a lazygit custom command:

```yaml
# ~/.config/lazygit/config.yml
customCommands:
  - key: "D"
    command: >
      GIT_EXTERNAL_DIFF=difft
      git diff {{.SelectedLocalCommit.Sha}}^!
    context: commits
    subprocess: true
```

## Performance on Large Repos

delta is Rust and has no perceptible lag on typical diffs. Exclude
generated paths to avoid coloring thousands of minified tokens:

```bash
git diff -- ':!*.lock' ':!dist/**'
```

difftastic is 5–10x slower — Tree-sitter parsing is O(n) per file.
Falls back to character-level diff for unsupported languages (shown
as "Text"). Check coverage: `difft --list-languages`.

## Anti-patterns

- Running `delta` inside scripts that parse diff output — use
  `git --no-pager diff` or pipe through `cat` to get raw text.
- Setting `GIT_EXTERNAL_DIFF=difft` globally in `.bashrc` — every
  `git diff` becomes an AST diff; merge conflict resolution tools
  that call `git diff` internally will break.
- Using `side-by-side = true` in delta on terminals narrower than
  160 columns — output wraps mid-line and is harder to read than
  the default unified view.
- Replacing lazygit's built-in conflict resolution with difftastic;
  difftastic is read-only output, not an editor.

## Gotchas

- `LESS=-F` causes short diffs to exit before paging. Add
  `--pager 'less -RFX'` to the delta gitconfig block or unset it.
- difftastic requires 256-color support; use `--color=never` for
  CI log capture where colors are absent.
- `merge.conflictstyle = diff3` must be set before conflicts are
  generated — it has no effect on already-written conflict markers.
- delta and bat share the same syntax engine; `$BAT_THEME` can
  silently override the `syntax-theme` in gitconfig.

## Verification

```bash
git config core.pager           # expect: delta
difft --list-languages | grep -i typescript
# Open lazygit → press d on a file → diff pane should be highlighted
```

## Related

- `devtools/lazygit-patterns.md`
- `devtools/git-config-global.md`
- `devtools/dotfiles-management-chezmoi-stow.md`
- `devtools/git-interactive-rebase.md`
- `devtools/bat-cat-replacement.md`

## Source URLs (verified 2026-08-17)

- https://github.com/dandavison/delta
- https://github.com/Wilfred/difftastic
- https://difftastic.wilfred.me.uk/
- https://dandavison.github.io/delta/configuration.html
- https://github.com/jesseduffield/lazygit/wiki/Custom-Commands-Compendium
