# shellcheck-shfmt-bash-toolchain

**Issue:** This repo, like most infrastructure code, is full of shell: install scripts, adb test harnesses, Docker entrypoints, Git Bash helpers, CI steps. Shell is a language where quoting a variable wrong is a security hole (`rm -rf "$DIR/"*` versus `$DIR/*`), word-splitting breaks paths with spaces, and `shellcheck`-class bugs ship for years because the script "worked in testing." Yet bash rarely gets the lint/format/test treatment TypeScript does. The 2025 consensus toolchain — validated by Microsoft's engineering playbook, which mandates shellcheck in CI — is dead simple: shellcheck for static analysis, shfmt for deterministic formatting, both editor-integrated and CI-enforced. This article covers that toolchain and the specific checks that matter for scripts written on Windows Git Bash and run on Linux CI.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two tools and their split of labor

1. **shellcheck finds bugs, shfmt fixes style.** They are deliberately complementary: shellcheck is a static analyzer that reasons about quoting, expansion, and control flow (SC-numbered rules), while shfmt is a formatter that enforces indentation, spacing, and case-statement layout the way prettier does for TS. Formatting is not linting — use both, and do not fight shfmt output in review.
2. **Both are static binaries with no runtime.** Each is a single Go/static binary that runs on Windows, macOS, and Linux — critical for this repo where scripts are authored in Git Bash on Windows but executed in CI on Linux. Install via scoop/winget on Windows, brew on macOS, or the prebuilt releases; no Python/Node runtime coupling like pre-commit's hook environments.
3. **Editor integration comes through LSP or none-ls.** bash-language-server provides shellcheck diagnostics natively in VS Code and Neovim (2025 posts document wiring shfmt through none-ls/conform for format-on-save), so feedback arrives while typing instead of in CI. VS Code's shellcheck extension is the zero-config path.
4. **CI enforcement is one line.** `shellcheck $(git ls-files '*.sh')` or the action `ludeeus/action-shellcheck` gates every push; add `shfmt -d $(git ls-files '*.sh')` (diff mode) or `shfmt -w` as a fix step. Microsoft's code-with-engineering-playbook bash recipe treats shellcheck-in-CI as a MUST, not a nice-to-have.

## The shellcheck rules that actually bite

1. **SC2086 (double-quote expansions).** The highest-signal check: unquoted variables word-split on whitespace. On Windows-authored scripts this is extra insidious because paths like `C:/path/to/project contain no spaces in testing but CI paths or filenames with spaces break later. Quote every expansion; use arrays for argument lists.
2. **SC2155 (masking exit codes in local assignment).** `local out=$(cmd)` discards the command's exit status, so error handling silently never fires — the root cause of a whole class of "script continued after failure" incidents. Split declaration and assignment.
3. **SC2034/SC2116 (dead assignments and useless cat).** Not bugs but noise that hides real ones; keeping the codebase warning-clean is what makes new SC warnings visible in review instead of drowned out.
4. **set -euo pipefail as a baseline.** shellcheck's SC2312-class guidance plus the `strict` mode preamble (`set -euo pipefail`, `IFS=$'\n\t'`) converts silent failures into loud ones. Every new script in this repo should start strict; shellcheck flags several patterns that only fail under `-e`.
5. **Directives for the rare false positive.** `# shellcheck disable=SC2312` with an explanation comment is the sanctioned escape hatch; audit directives in review like you would `eslint-disable` or `ts-ignore`.

## shfmt in practice

1. **Pick a config once and encode it.** `shfmt -i 2 -ci -sr -bn` (2-space indent, switch-case indent, keep function braces on the name line) covers most team tastes; since shfmt 3.x the canonical place is `.editorconfig` — shfmt reads `indent_size`, `switch_case_indent`, and friends from it, which pairs with this repo's editorconfig-team-consistency article: one file drives both editor and formatter.
2. **Language variants matter on Windows.** `-ln bash` versus `-ln posix` changes accepted syntax; Git Bash scripts can use bashisms safely, but anything that might run under `sh` (alpine containers, dash on Debian) must be checked as posix or rewritten portably — shfmt will reject bash-only syntax when told posix.
3. **Binary/operator placement kills diffs.** `shfmt -bn -fn` decisions (braces/functions) are exactly the kind reviewers bikeshed; formatting-once-by-machine ends the argument permanently.
4. **Fix scripts, then forget them.** Running `shfmt -w` and `shellcheck -f diff | patch` once over the legacy script corpus converts it to clean in a single mechanical commit; afterwards CI diff-mode keeps it clean with zero human effort.

## Shell toolchain on Windows Git Bash specifically

1. **Line endings are a lint failure.** CRLF shebangs (`#!/usr/bin/env bash\r`) break on Linux with "bad interpreter" errors. Enforce `*.sh text eol=lf` in `.gitattributes` and let shfmt's parser reject stray CRs — this is the single most common Windows-to-Linux script bug in this repo's history.
2. **Test under the interpreter that will run it.** Git Bash provides a real bash, but CI runs a different version; for high-stakes scripts, run them in WSL2 or a container (`docker run --rm -v "$PWD:/w" -w /w koalaman/shellcheck-alpine`) to catch behavior differences, not just syntax.
3. **Use the Docker images when pinning matters.** `koalaman/shellcheck` and `mvdan/shfmt` published images give bit-identical versions on every machine — the same reproducibility argument as the nix-devenv article, without adopting Nix.
4. **Beware command grep aliasing in harness scripts.** In Git Bash interactive shells, `grep` may be a function/alias with color flags that break `--flag` parsing when scripts source profiles; invoke `command grep` inside scripts (this repo's tooling convention) and shellcheck's SC2230-family checks hint at similar command-shadowing issues.

## Related

1. **Adjacent repo articles.** `msys-gitbash-windows-quirks.md` for the shell environment itself; `pre-commit-framework.md` and `git-hooks-husky.md` for wiring shellcheck/shfmt as commit-time hooks; `editorconfig-team-consistency.md` for the shared config file shfmt consumes.
2. **Primary sources.** shellcheck.net (rule wiki), mvdan/sh README, and Microsoft's code-with-engineering-playbook bash review recipe are the canonical references.
