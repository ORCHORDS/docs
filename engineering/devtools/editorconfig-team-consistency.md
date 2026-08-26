# editorconfig-team-consistency

**Issue:** A team mixes VS Code, JetBrains, Neovim, and Zed; every editor defaults differently (tabs vs spaces, final newline, line endings, charset), so PRs drown in whitespace-only diffs, shell scripts break from space indentation, and `.gitattributes` alone cannot fix what editors write in the first place. A committed `.editorconfig` is the portable, editor-agnostic contract that fixes this at the source. This article covers the properties that matter, layering strategy for monorepos, per-language patterns, and verification in CI.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core properties that matter

1. **`root = true`.** The first line of the repo-root `.editorconfig`; it stops EditorConfig's upward directory search so files inside the repo are never affected by a stray `~/.editorconfig` or a parent directory's rules. Forgetting it is the number one "why is this file still wrong" cause.
2. **`indent_style` and `indent_size`.** `indent_style = space|tab` and `indent_size = n` (or `tab` to follow tab width) set the basic indentation contract; `tab_width` separately controls how wide a tab renders. This pair eliminates the classic tab/space mangling when two editors touch the same file.
3. **`end_of_line = lf`.** Enforces LF line endings at the editor layer on every OS, complementing (not replacing) `* text=auto eol=lf` in `.gitattributes` — EditorConfig governs what the editor writes, git attributes govern what the repo stores.
4. **`charset = utf-8`.** Prevents Windows editors from writing UTF-16 or codepage-encoded files that silently break builds, grep, and diffs on other platforms; `utf-8-bom` and `utf-16le/be` exist as escape hatches for legacy formats that genuinely need them.
5. **`trim_trailing_whitespace` and `insert_final_newline`.** Two booleans that kill trailing-whitespace diff noise and the "no newline at end of file" `\ No newline at end of file` markers — set both `true` globally and disable per-section only where trailing whitespace is significant (Markdown).

## Layering strategy

1. **One root file with language sections beats many scattered files.** The standard shape is `[*]` defaults at the top of the root `.editorconfig`, followed by narrower globs (`[*.{ts,tsx}]`, `[*.py]`) that override — everything is visible in one reviewable file, and precedence is simply "most specific section wins."
2. **Nested `.editorconfig` files work in monorepos.** Each nested file needs its own `root = true` to stop upward merging at that package; properties then combine from outer to inner, letting a Python-heavy package flip to 4-space indentation without touching the JS packages' 2-space rule.
3. **Keep it minimal — encode editor behavior, not style opinion.** The dotnet runtime team famously keeps theirs intentionally minimal; whitespace properties (indentation, newline, charset) are universal, but resist using EditorConfig's extended analyzer properties (.NET style rules) outside .NET repos where they actually run.
4. **Divide responsibility with your formatter.** Let `.editorconfig` define the irreducible basics (what any editor does on save), and let Prettier/Biome/oxfmt own nuanced formatting (quotes, wrapping, semicolons) — Prettier and Biome both read `.editorconfig` values like `indent_style` and `max_line_length` where applicable, so the two layers stay consistent instead of competing.
5. **Order sections from broad to specific.** EditorConfig applies the *last matching section* for a property, so `[*]` first, then `[*.js]`, then `[packages/legacy/**.js]` last — a file read top-to-bottom reads as "defaults, then exceptions," which is exactly how reviewers scan it.

## Per-language patterns

1. **YAML: spaces, never tabs, 2-wide.** `indent_style = space` under `[*.ya?ml]` — the YAML spec forbids tabs for indentation, and a tab-indented YAML file fails every parser, not just some editors.
2. **Makefiles: tabs, unconditionally.** `[Makefile]` with `indent_style = tab` because `make` requires literal tab recipe prefixes; this section is what saves builds after someone's editor "helpfully" converts everything to spaces.
3. **Markdown: preserve trailing spaces.** `[*.md]` with `trim_trailing_whitespace = false` — two trailing spaces are hard line breaks in Markdown, and a global trimmer silently reflows paragraphs.
4. **Windows scripts: CRLF.** `[*.{cmd,bat,ps1}]` with `end_of_line = crlf` — `.cmd`/`.bat` are safest CRLF and some PowerShell tooling expects it, isolating the one place CRLF is correct in an otherwise-LF repo.
5. **Generated and vendored code: leave it alone.** Sections like `[minified/**]` or `[{dist,build,vendor}/**]` can neutralize rules (e.g. `insert_final_newline = false`) so generated blobs do not fight the generators or produce endless CI diffs.

## Integration and enforcement

1. **Know your editor's support level.** JetBrains IDEs and recent Neovim (0.9+) support EditorConfig natively; VS Code needs the EditorConfig extension and must be configured to make it the authority over the editor's own settings; Zed and Helix honor it built-in — verify once per team machine instead of assuming.
2. **Make it the base layer of format-on-save.** EditorConfig properties feed the formatter's defaults (Prettier respects `.editorconfig`; Biome reads `indent_style`/`line_width` context), so the file is enforced even in editors where no extension is installed and by every CLI formatter run.
3. **Enforce in CI with a checker.** `editorconfig-checker` or `eclint check` in CI fails the build when committed files violate the declared properties, catching the one contributor whose editor ignored the file — the properties then become a contract, not a suggestion.
4. **Test globs when adding sections.** `editorconfig-checker` and EditorConfig's own tooling let you ask "which rules apply to path X"; run it after adding a tricky glob (e.g. `[*.{js,mjs,cjs}]` forgetting `.jsx`) before the team discovers the gap in review.
5. **Commit it first, migrate whitespace separately.** Land `.editorconfig` in its own commit, then apply the one-time reformat (editor "apply .editorconfig" or `eclint fix`) in a dedicated mechanical commit — mixing the contract with ten thousand whitespace changes makes both unreviewable and un-bisectable.
