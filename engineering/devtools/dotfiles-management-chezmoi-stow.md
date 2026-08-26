# dotfiles-management-chezmoi-stow

**Issue:** A new laptop means an afternoon of recreating `.gitconfig`, `.zshrc`, `tmux.conf`, and `.ssh/config` from memory or an old-machine scp, and the copies silently drift across three machines until each one is unique and none is correct. Configs also contain things a public repo must never hold (`.npmrc` tokens, `.netrc`, SSH keys). A dotfiles manager makes the setup reproducible and the differences explicit.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choose your weapon

1. **The bare git repo is the zero-dependency option.** `git clone --bare <url> $HOME/.cfg` plus an alias like `config='git --git-dir=$HOME/.cfg/ --work-tree=$HOME'` and `config checkout` with `status.showUntrackedFiles no` gives you version control with no new tools. Limits are real: no templating, no secret handling, and a `git add` typo can stage your entire home directory — but for one machine and one OS it is a legitimate 80% solution.
2. **GNU Stow is the symlink farm.** You keep real files in package directories (`dotfiles/zsh/.zshrc`) and `stow zsh` symlinks them into `$HOME`. It is a ~500-line Perl script with a five-minute learning curve, works with plain files and plain git, and needs no daemon. It has no answer for per-machine differences or secrets — the file is the file, on every machine.
3. **chezmoi is the full-featured manager.** A single Go binary that *materializes real files* (not symlinks) from a source state, with templates for per-machine differences, first-class secrets integration, and pre/post scripts. The cost is its own mental model: the source directory uses filename mangling (`dot_zshrc` for `.zshrc`) and you drive it through `chezmoi` subcommands rather than raw git (though it is a git repo underneath).
4. **yadm is "git with superpowers" for dotfiles.** It wraps git (same commands, same workflows) and adds per-class/hostname file alternates (`file##os.Darwin`, `file##class.work`) plus built-in encryption for sensitive files. Best fit for people who want everything to stay "just git" while still getting per-machine variance.
5. **The 2025 consensus split.** Stow for simple, mostly-single-machine setups; chezmoi for multi-machine/multi-OS fleets, teams, or anything needing secrets and bootstrap logic; yadm or bare-git for git-lovers with light needs. All four are actively maintained — the wrong choice is having *no* manager, not picking among these.

## chezmoi in practice

1. **Learn the four-command loop: `init`, `add`, `ed`, `diff`, `apply`.** `chezmoi add ~/.zshrc` imports a live file into source state; `chezmoi edit ~/.zshrc` edits the *managed* version; `chezmoi diff` shows what apply would change on disk; `chezmoi apply` writes it. The habit that makes chezmoi safe is running `diff` before `apply` — it converts "my config tool overwrote my edits" into a reviewable change.
2. **Use templates for per-machine differences.** A `.zshrc` stored as `dot_zshrc.tmpl` can branch on `{{ .cheat }}` values (hostname, OS, osRelease) or on data you define in `~/.config/chezmoi/chezmoi.toml` (itself created from a templated `chezmoi.toml.tmpl`). Machine-specific exports stop being three divergent files and become one file with named branches.
3. **Pull secrets at apply time, never store them.** chezmoi templates can interpolate from 1Password (`op://...` references), Bitwarden, pass, KeepassXC, LastPass, or age/gpg-encrypted files — the token reaches the target file only when `chezmoi apply` runs, so the repository (public or private) never contains the secret. `.npmrc` and cloud credential files are the canonical use.
4. **Automate setup with `run_once_` and `run_onchange_` scripts.** `run_once_install-packages.sh.tmpl` executes once per machine (guarded by chezmoi's state db); `run_onchange_` scripts keyed on a template hash (e.g. containing `{{ join .packages "\n" }}`) re-run whenever the package list in your config changes. Package installation stops being a wiki page and becomes part of apply.
5. **Bootstrap a fresh machine with one command.** `sh -c "$(curl -fsLS get.chezmoi.io/lb)" -- init --apply <user>` installs the binary, clones your repo, and applies everything — the demo for "new machine to fully configured" being a single paste.

## Stow in practice

1. **One package per tool.** `dotfiles/` contains `zsh/`, `git/`, `tmux/`, `ssh/`, `nvim/` — each holding exactly the files that belong to that tool (`.ssh` package: `config` and nothing key-shaped). `cd ~ && stow zsh` symlinks the package's contents into place; `stow -D zsh` removes exactly those links. Clean packages make commits reviewable and uninstall real.
2. **Adopt existing configs instead of deleting them.** On a machine with live (unmanaged) files, `stow --adopt zsh` moves the existing dotfiles into the package and symlinks back — no manual copy dance, no risk of clobbering the live version with the repo version.
3. **Ignore the junk.** `.stow-local-ignore` (or `--ignore=REGEX`) keeps OS droppings like `.DS_Store` out of the symlink set, so `stow` does not link garbage from the repo into `$HOME`.
4. **Do not fight the per-machine limit.** Stow has no templating: if two machines need different `.gitconfig` emails, the accepted patterns are a tiny include line (`[include] path = ~/.gitconfig-local`, left unmanaged) or host-conditional includes. If you need more than one or two such seams, that is the signal to graduate to chezmoi/yadm rather than to script around stow.
5. **Keep the repo itself boring.** Plain git, no build step, a README with the two-command install (`git clone` + `stow */`), and a single `install.sh` for the pieces stow cannot express (package manager calls). Boring survives laptop changes; clever does not.

## Hygiene that applies to every approach

1. **Secrets never enter the repo, public or private.** `.env`-style tokens belong in manager-encrypted storage (chezmoi templates, yadm encrypt, git-crypt) or in unmanaged local files that the managed config *includes*. Run a secret scanner over the repo in CI — dotfiles repos are the most commonly leaked-by-habit repositories because people treat them as "just settings".
2. **Version the bootstrap, not just the files.** The deliverable is "paste one command, get a working machine": a bootstrap script (or chezmoi's init/apply) covering binary installs, package managers, and first-run steps. Test it fully in a fresh VM/container quarterly; untested bootstrap scripts rot silently.
3. **Keep scripts idempotent and platform-honest.** Every setup script must be safe to re-run (guard with checks, not comments), and the repo must branch cleanly per-OS where needed (chezmoi templates, yadm alternates, or separate packages) — a repo that works on macOS and bricks WSL is half a solution.
4. **Windows specifics deserve their own plan.** Real symlinks on Windows need Developer Mode or admin rights, which makes stow awkward; the pragmatic options are managing only the cross-platform files (`~/.gitconfig`, `.ssh/config`, editor configs) or running the whole stack inside WSL2 where the Linux tools behave. Decide once, document it in the README, and stop half-managing `Documents/PowerShell`.
5. **Tag known-good states.** Periodic tags (`laptop-2026-08-working`) turn "the update broke my terminal" into `git checkout <tag>` instead of archaeology — the same reasoning as release tags, applied to the machine you work on.

## Related

- ssh-config-mastery (the highest-value file most repos manage)
- bash-aliases-functions (content that outgrows a single machine)
