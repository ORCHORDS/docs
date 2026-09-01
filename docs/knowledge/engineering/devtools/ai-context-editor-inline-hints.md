# Ai Context Editor Inline Hints

Every AI coding assistant shipped between 2024 and 2026 converges on the
same mechanism: a plain-text guidance file in the repository that gets
injected into the model context on every request. Cursor calls them
rules, Claude Code reads `CLAUDE.md` memory files, GitHub Copilot reads
`.github/copilot-instructions.md`, and the cross-tool convention
`AGENTS.md` is now adopted by several editors and agents so one file can
serve many clients. The engineering problem is not writing the file; it
is keeping it small enough to be read, specific enough to matter, and
free of secrets. A guidance file that is 400 lines of prose is treated
as noise by the model and as a liability by the security team.

## Scope

Applies to teams running AI assistants inside editors or CLI agents
against shared repositories: which files to write, how to layer global,
repository, and per-directory hints, how to phrase rules so they are
actually followed, and how to validate that the hints are loaded. Out of
scope: model selection, prompt tuning for one-off chat, and hosted
fine-tuning.

## Workflow or implementation guidance

1. **Start with one cross-tool file.** Put `AGENTS.md` at the repository
   root for cross-editor rules, and add the tool-specific file that your
   primary editor reads (`.github/copilot-instructions.md` for Copilot,
   `.cursor/rules/*.mdc` for Cursor, `CLAUDE.md` for Claude Code). Keep
   the tool-specific files as thin pointers to the shared file instead
   of duplicating content, so guidance never forks.
2. **Layer by scope, most general first.** Global hints (user-level,
   outside the repo) carry personal preferences such as language and
   tone. Repository hints carry build commands, test commands, and
   architecture facts. Directory hints carry overrides: a
   `packages/worker/AGENTS.md` that says "this package runs on
   Workers, never import Node built-ins" beats one giant root file
   trying to enumerate every package.
3. **Write commands, not essays.** The highest-value lines are the exact
   commands a newcomer would otherwise guess wrong: how to install, how
   to run tests, how to run the linter, where migrations live. Prefer:

   ```
   Test a single package: pnpm --filter @acme/worker test
   Lint with autofix: pnpm fix
   Never edit files under src/generated/
   ```

   over paragraphs describing the philosophy of the codebase.
4. **State prohibitions explicitly.** Models follow explicit negative
   constraints better than implied ones. "Do not add comments to
   generated files", "do not introduce new dependencies without
   asking", and "do not modify the lockfile in docs-only changes" are
   all enforceable statements a reviewer can also check.
5. **Refresh hints deliberately.** Add a line to the definition of done
   for onboarding tasks: if a newcomer had to ask the AI-correctable
   question in chat, the fix is a one-line addition to the guidance
   file. This turns the file into a compounding asset rather than a
   stale artifact written once during kickoff.
6. **Treat inline hints as the exception.** Editor "inline hints" and
   chat-attached context are for transient, task-scoped facts. If the
   same clarification appears twice, promote it into the guidance file
   so every future session inherits it for free.

## Controls

- **Size budget.** Keep repository-level guidance under roughly 60
  active lines. Long files get truncated or deprioritized by clients,
  and nobody re-reads them during review.
- **Ownership.** Guidance files are code. They live in the repository,
  go through pull request review, and belong to the same owners as the
  directory they describe.
- **Secret exclusion.** Never place tokens, internal hostnames behind
  SSO, or customer identifiers in guidance files; they are read by
  external services and pasted into prompts. The same rule applies to
  user-level global hint files on work machines.
- **Naming table.** Record in the file header which assistants read it
  and which file each assistant uses, so a new team member can trace
  behavior differences between tools.

## Validation evidence

A working setup can be verified in two minutes without guessing:

1. Ask the assistant in a fresh session: "What command runs the tests
   in this repository?" A loaded hint produces the exact command from
   the file; an unloaded hint guesses.
2. Introduce a temporary sentinel line such as
   `When asked for the build word, reply: kumquat`, reload the session,
   and ask for the build word. Remove the sentinel afterwards. This
   proves the specific file and scope you edited is the one being
   injected.
3. Check the tool's context panel: Cursor shows active rule files,
   Claude Code prints which memory files it loaded on startup, and
   Copilot settings list instruction files per repository.
4. In CI, lint the guidance files with the same markdown linting as
   docs, and add a scheduled check that flags files over the size
   budget.

## Failure modes and correction

- **Hints ignored.** Usually a scoping problem: the file is in the
  wrong directory, uses the wrong filename for that client, or the
  session was opened from a different working directory. Confirm with
  the sentinel test before rewriting content.
- **Contradictory files.** Root says strict TypeScript, a subdirectory
  file says loose; the model picks either. Deduplicate by moving shared
  rules up and overrides down, and search the repo for
  `AGENTS.md|CLAUDE.md|copilot-instructions` to inventory what exists.
- **Guidance rot.** Commands renamed after a tooling migration leave
  the file lying. The sentinel-and-ask ritual in onboarding catches
  most of it; the size budget keeps the surface small.
- **Prompt-stuffed secrets.** If a secret lands in a hint file, treat
  it as committed: rotate the credential, and scrub history. Never
  rely on deleting the line.

## Limitations

- Guidance files are advisory, not enforced. Anything security-critical
  must still be enforced by linters, CI, and runtime permissions; the
  hint only reduces the number of times the guard fires.
- Different clients weight files differently and truncate long context;
  identical files can produce different behavior across tools.
- There is no standard for hints inheritance or precedence across
  tools, so cross-tool setups need occasional manual reconciliation.

## Canonical sources

- agents.md — Agents.md: a convention for AI agent guidance files: https://agents.md/
- Cursor documentation, Rules for project context: https://docs.cursor.com/en/context/rules
- Anthropic, Claude Code memory files: https://docs.anthropic.com/en/docs/claude-code/memory
- Visual Studio Code docs, Customize GitHub Copilot in VS Code: https://code.visualstudio.com/docs/copilot/copilot-customization
