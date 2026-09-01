# Direnv Per Project Environment Loading

direnv is a per-directory environment switcher for the shell. When you
`cd` into a project, it loads the variables declared in that project's
`.envrc`; when you leave, it unloads them. This kills the two failure
modes of ad hoc environment management: the stale exported variable
from a previous project silently redirecting today's build, and the
50-line `source ./env.sh` ritual every README demands. Each project's
environment becomes an artifact in the repository, applied and removed
automatically, with an explicit trust step that prevents a cloned
repository from executing hooks without consent.

## Scope

Using direnv to load per-project environment variables for development:
installation and shell hooking, authoring `.envrc` files, the trust
model, secrets handling, integration with version managers and editors,
and team conventions. Not covered: secret management systems or CI
environment configuration.

## Workflow or implementation guidance

1. **Install and hook the shell.** Install direnv from the package
   manager (`brew install direnv`, `apt install direnv`,
   `scoop install direnv`), then add the hook to the shell rc — for
   bash `eval "$(direnv hook bash)"`, with equivalent one-liners for
   zsh and fish. The hook must come late enough in the rc that the
   prompt command chain is final; in bash, placing it after the
   PROMPT_COMMAND setup avoids the hook being overwritten.
2. **Author the project `.envrc` minimally.** The file is shell code
   evaluated in a restricted-ish context. The canonical shape loads a
   git-ignored secrets file and declares only project facts:

   ```bash
   # .envrc (committed)
   dotenv_if_exists .env.local      # secrets live in the ignored file
   export PROJECT_ROOT=$PWD
   export DATABASE_URL="postgres://localhost:5432/app_dev"
   PATH_add ./bin                   # project-local tool scripts
   layout python                    # or: layout node, layout poetry
   ```

   direnv provides helpers like `PATH_add`, `dotenv`, and `layout`
   directives that prepare language-specific environments without
   activating anything globally.
3. **Approve the file once with `direnv allow`.** direnv refuses to
   load `.envrc` files it has not been told to trust. After any edit it
   re-blocks until `direnv allow` runs again. This is the security
   model: cloning a repository never executes its environment hooks
   until a human explicitly consents, and any later modification
   re-triggers that consent.
4. **Keep secrets out of the committed file.** `.envrc` is committed
   and reviewed; values that must not be public belong in an ignored
   `.env.local` (or similar) loaded via `dotenv_if_exists`, distributed
   through the team's secret channel. direnv's export diff shown on
   load makes accidental secret exposure visible in the terminal
   immediately.
5. **Compose with per-project version managers.** A line like
   `use fnm` or invoking the version manager's env command inside
   `.envrc` ties the toolchain to the directory as well, so entering a
   project selects the pinned language runtime and leaving restores
   the shell default. This composes cleanly with tools that expose an
   env-printing command, and is the reason direnv pairs so well with
   per-project toolchains.
6. **Make the editor agree with the terminal.** Editors launched from
   the dock inherit no hook. Either launch the editor from a hooked
   shell, or configure the editor extension that evaluates `.envrc`
   for language-server processes, so the IDE's typecheck and the
   terminal's build see the same variables.
7. **Standardize the team layout.** Agree on one structure — committed
   `.envrc` with structure only, ignored `.env.local` with values, a
   committed `.envrc.example` documenting required variables — and put
   a check in CI that fails when `.envrc` is committed but
   `.envrc.example` is missing or out of date.

## Controls

- **Trust discipline.** `direnv allow` is a code-review event: the
   `.envrc` diff appears in pull requests like any other code, and
   reviewers treat new exports as configuration changes.
- **Secret exclusion.** Add `.env.local` and any dotenv-style value
   files to `.gitignore` by default; grep hooks or pre-commit secret
   scanners should include `.envrc` in their scan path because people
   do paste real values into it.
- **Diff visibility.** direnv prints the exact environment diff on
   load and unload; teach the team to read it, since it is the audit
   log of what a directory just did to the shell.
- **Standard helpers only.** Restrict `.envrc` to exported variables,
   `PATH_add`, `dotenv`, and `layout` directives. Anything more complex
   (curl calls, code generation) belongs in a task runner invoked
   explicitly, not in an implicit directory hook.

## Validation evidence

1. From the project root with an allowed `.envrc`, run
   `direnv status` and confirm the loaded state; `echo $DATABASE_URL`
   (or a project-specific variable) returns the declared value.
2. `cd` out of the project and confirm the variable is unset in the
   same shell — this asymmetry is the core behavior; a variable that
   persists after leaving indicates a hook problem or an export made
   in the rc instead of the `.envrc`.
3. Edit the `.envrc` with a trivial comment; direnv must block until
   `direnv allow` is rerun, demonstrating the re-consent on change.
4. `git status` shows `.envrc` tracked and `.env.local` ignored;
   cloning the repository fresh into a temp directory shows direnv
   refusing to load until explicitly allowed.
5. In CI, a lint job validates the committed `.envrc`: shellcheck-style
   parsing plus an assertion that every variable documented in
   `.envrc.example` is referenced.

## Failure modes and correction

- **Variables not loading.** The hook is missing from the rc, the rc
   exports `PROMPT_COMMAND` after the hook (overwriting it), or the
   file was never allowed. `direnv status` distinguishes all three.
- **Stale environment after edits.** direnv caches; `direnv reload`
   forces re-evaluation. Also confirm the edit was to the file direnv
   actually loads (not a sibling directory's file).
- **`cd` into a directory is suddenly slow.** A heavy `.envrc` (network
   calls, language version downloads) runs on every entry; move that
   work to an explicit task and keep the hook to instant operations.
- **Secrets committed.** Treat as an incident: rotate the credential,
   scrub history, and move the value into the ignored file. The export
   diff printed on load usually exposes the mistake in time, but only
   if someone reads it.
- **Editor disagrees with terminal.** The editor process never ran the
   hook; launch from the hooked shell or enable the editor integration
   rather than re-exporting variables in the editor settings, which
   forks the source of truth.

## Limitations

- direnv manages the shell environment only; it does not provision
  containers, system packages, or multi-service orchestration — those
  belong to dev containers or compose files, with direnv as a thin
  wrapper.
- The trust model is consent-based, not sandboxed: an allowed `.envrc`
  executes shell code; the protection is the explicit allow step and
  re-consent on change, not isolation.
- Windows support exists but the ecosystem (layouts, helper snippets)
  is Unix-centric; Git Bash users should verify layout helpers before
  relying on them.

## Canonical sources

- direnv official site and documentation: https://direnv.net/
- direnv GitHub repository: https://github.com/direnv/direnv
- direnv configuration reference, direnv.toml: https://direnv.net/man/direnv.toml.1.html
