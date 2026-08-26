# nix-devenv-reproducible-environments

**Issue:** Every onboarding doc in a polyglot repo starts the same way: install Node 20, install pnpm, install ripgrep, install shellcheck, install Ollama... and every machine drifts. Version managers (nvm, asdf, mise) pin language runtimes but not the surrounding CLI tools, system libraries, or daemon versions, so "works on my machine" survives even strict lint setups. Nix — and specifically devenv.sh, the friendliest 2025-era layer over it — solves this by declaring the entire development environment (languages, tools, environment variables, processes, even git hooks) in one `devenv.nix` file that builds bit-identically from the Nix store on any machine. This article covers when to reach for Nix versus devcontainers, how devenv structures an environment, and the practical gotchas (Windows/WSL, garbage collection, CI caching) learned running it alongside this repo's pnpm toolchain.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why Nix versus the alternatives

1. **Reproducibility scope.** A devcontainer gives you isolation and onboarding but its reproducibility is only as good as the pinned base image digest; apt installs inside it drift. Nix environments hash every input (compiler, CLI tool, library) into store paths, so the same flake input yields the same `ripgrep` and the same `nodejs` binary everywhere, including CI.
2. **Speed after the first build.** Nix store paths are content-addressed and shared across projects; once `nodejs_20` is built or downloaded, every project reuses it instantly with no re-download. devenv adds Cachix-backed binary caches so most environments materialize in seconds even fresh.
3. **No container overhead.** devenv shells run directly on the host (Linux/macOS), so editors, GPU access for local Ollama models, and USB/network device access just work — no volume-mount performance tax and no file-watcher event loss across the VM boundary.
4. **They compose rather than compete.** The 2025 consensus for teams: use Nix/devenv for toolchain-level reproducibility and devcontainers only when you need hostile isolation or a different OS. You can run devenv inside a devcontainer for both properties.
5. **Windows requires WSL2.** Nix does not run natively on Windows. On this repo's Windows machines the pattern is: develop in Git Bash for everyday work, and keep a WSL2 Ubuntu distro with Nix installed for devenv-driven environments and CI parity.

## Structure of a devenv project

1. **devenv.nix holds the environment.** One file declares `languages.javascript.enable`, `packages` (ripgrep, jq, shellcheck), `env` variables, `processes`, and `scripts`. It is normal Nix, so anything expressible in nixpkgs (thousands of tools) is one line away.
2. **devenv.yaml pins the flake inputs.** The `inputs` block locks nixpkgs to a specific revision, which is what makes the environment reproducible across machines and across time; committing `.devenv` lockfiles pins it exactly.
3. **devenv shell versus direnv integration.** `devenv shell` enters the environment manually; wiring `devenv direnv allow` makes every cd into the project load the environment automatically and cache it so re-entry is instant. This replaces hand-maintained `.envrc` files and most of the dotfiles-level PATH juggling.
4. **Processes replace ad-hoc daemon scripts.** `processes.router.exec = "node packages/router/dist/index.js"` declares long-running services; `devenv up` starts all of them with a process manager (and can use `process.managers.process-compose` for logs/restart control). For this repo that means router, web-research, and SearXNG health checks start with one command.
5. **Scripts are typed, documented commands.** `scripts."run-fleet".exec` becomes a real command with help text inside the shell — a more discoverable alternative to scattering scripts across package.json and Makefile.

## Git hooks and quality gates

1. **First-class pre-commit integration.** devenv embeds cachix/git-hooks.nix: declare `pre-commit.hooks.prettier`, `pre-commit.hooks.shellcheck`, `pre-commit.hooks.nixfmt` in devenv.nix and the hook binaries come from the Nix store — every contributor lints with the identical tool version without installing anything.
2. **Hooks run from store paths, so protect them from GC.** devenv exposes an option to add the generated pre-commit configuration to GC roots; without it, an aggressive `nix-collect-garbage` can delete the very tools your hooks call and commits start failing mysteriously.
3. **You can opt out per machine.** The git-hooks integration writes into `.git/hooks` on shell entry, which can surprise contributors who already manage hooks with husky or pre-commit framework. Team reports on NixOS Discourse cover conflicts; the escape hatch is disabling the integration in a local, uncommitted devenv.local.nix.
4. **Watch for the hang regression.** devenv issue #<number> documents `devenv shell` hanging with "Failed to realize shell derivation" when hooks are enabled on some setups — worth knowing when a teammate's shell freezes on first run; updating devenv and clearing `.devenv` usually resolves it.

## Gotchas and operations

1. **Garbage collection is real.** `nix-collect-garbage -d` removes old generations including environments referenced only by lockfiles you deleted. Keep GC roots (`devenv gcroots`) or re-enter the shell to rebuild.
2. **Disk usage grows before it shrinks.** Each distinct nixpkgs revision materializes new store paths; pin inputs deliberately and bump them on a schedule (Renovate can automate flake input updates too) rather than floating.
3. **CI needs the cache or it is slow.** Without Cachix (or GitHub Actions' magical Nix caching), a cold CI runner rebuilds or downloads the full environment per job. devenv's native GitHub Actions support plus a Cachix cache is the standard pairing.
4. **Learning curve is front-loaded.** Nix the language takes days; devenv deliberately hides most of it. The practical rule for this repo: devenv.nix is editable by anyone after one afternoon; raw flakes (flake.dev/flox territory) are only worth it when devenv options run out.
5. **macOS Apple Silicon notes.** Most nixpkgs are cached for aarch64-darwin now, but occasional packages build from source; budget a one-time compile and check the Cachix hit rate before assuming breakage.

## Related

1. **Adjacent repo articles.** `mise-version-manager.md` and `asdf-version-manager.md` cover the lighter runtime-only alternative; `devcontainer-json.md` covers the container isolation path; `direnv-env-setup.md` covers the auto-loading mechanism devenv builds on.
2. **Primary sources.** devenv.sh official docs (options reference, git-hooks, processes pages) and the cachix/git-hooks.nix repository are the canonical references for everything above.
