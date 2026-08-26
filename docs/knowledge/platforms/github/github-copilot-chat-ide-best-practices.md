# GitHub Copilot Chat in-IDE Best Practices

Copilot Chat (the inline chat / sidebar chat inside VS Code, JetBrains, Neovim,
and the GitHub.com web editor) is the most-used Copilot surface, yet most teams
treat it as a magic answer box and miss the context, instruction, and guardrail
features that dramatically improve answer quality and safety. This article
covers practical setup for dev teams in 2025–2026.

## Symptom

- Copilot Chat suggests outdated APIs, hallucinates library methods, or produces
  code that does not compile — and the team blames "Copilot being dumb."
- Developers paste large files into chat and get generic answers because
  Copilot has no project context (no `.github/copilot-instructions.md`, no
  workspace symbols).
- A junior dev accepted a chat suggestion that introduced a known-vulnerable
  dependency or leaked a secret into a suggested snippet.
- Enterprise admin sees low Copilot adoption or high "ignore rate" (suggestions
  rejected) and wants to improve ROI.
- Chat answers ignore your team's conventions (e.g., you use Vitest, but it
  keeps generating Jest examples).

## Fix

1. **Add a `.github/copilot-instructions.md` file** to the repo root. Copilot
   Chat automatically loads this as system context for every chat in that
   workspace:
   ```markdown
   # Copilot Instructions
   - This repo uses pnpm (never npm/yarn).
   - Tests run via `pnpm test` (Vitest). Do not generate Jest code.
   - We use TypeScript strict mode. All new code must be typed.
   - Prefer named exports. Default exports are forbidden.
   - Error handling: use the `Result<T,E>` pattern from src/lib/result.ts.
   ```
   Keep it under ~500 lines; overly long instructions dilute focus.

2. **Use chat participants for scoped context:**
   - `@workspace` — answers using your entire codebase as context (file search,
     symbol lookup). Use this for "where is X defined" or "how does feature Y
     work."
   - `@terminal` — explains the last terminal command or error output.
   - `@vscode` — answers about editor settings/commands.

3. **Use slash commands instead of freeform prompts for repeatable tasks:**
   - `/explain` — explain selected code
   - `/tests` — generate unit tests for the selection
   - `/fix` — propose a fix for a selected error
   - `/doc` — write doc comments
   - `/new` — scaffold a new file from a description

4. **Enable `github.copilot.chat.codeGeneration.instructions` in VS Code
   settings** for per-language conventions that don't belong in the shared
   repo file:
   ```json
   "github.copilot.chat.codeGeneration.instructions": [
     "When generating React, use function components with hooks.",
     "When generating SQL, prefer CTEs over subqueries."
   ]
   ```

5. **Review enterprise content exclusions** if your org has sensitive code.
   Admins can exclude certain repos from Copilot Chat's data collection via
   the enterprise policy "Content Exclusions."

## Gotchas

- Copilot Chat **does not see uncommitted/unstaged changes** unless you
  explicitly `@workspace` or select the text — it indexes the saved file state.
- `.github/copilot-instructions.md` is **per-repo**, not per-user. A developer
  who opens the repo in Codespaces or a fresh clone gets the same instructions
  automatically; there is no per-developer override file.
- The `/tests` slash command generates tests against the **public API of the
  selection** — if you select a private helper with no exports, it generates
  tests that cannot run without refactoring.
- Chat history is retained per-editor session and **synced across devices** if
  Settings Sync is on — sensitive prompts (pasting error logs with tokens) will
  propagate to other machines.
- Copilot Chat in JetBrains has **fewer participants** than VS Code
  (`@workspace` support landed later); cross-IDE teams should not assume
  feature parity.
- The "Inline Chat" (Cmd/Ctrl+I in the editor) uses a **shorter context window**
  than the sidebar chat — complex multi-file refactor prompts work better in the
  sidebar with `@workspace`.
- Copilot Chat can read **`.env` files** if they are open and selected — never
  paste secrets into chat, and consider adding `.env*` to content exclusions.
- Generated code may reference **packages that don't exist** (hallucinated
  imports) — always run the generated code through your linter/type-checker.
- The `@github` participant (for asking about issues/PRs/repos) requires the
  GitHub Copilot Enterprise tier; Pro/Business tiers will return an auth error.

## Sources

- [Best practices for using GitHub Copilot Chat (GitHub Docs)](https://docs.github.com/en/copilot/using-github-copilot/best-practices-for-using-github-copilot-chat)
- [Adding custom instructions for GitHub Copilot (GitHub Docs)](https://docs.github.com/en/copilot/customizing-copilot/adding-custom-instructions)
- [GitHub Copilot Chat documentation (GitHub Docs)](https://docs.github.com/en/copilot/github-copilot-chat)
- [Configuring content exclusions for GitHub Copilot (GitHub Docs)](https://docs.github.com/en/copilot/managing-copilot/managing-github-copilot-in-your-organization/managing-policies-for-copilot-in-your-organization#excluding-content-from-copilot)
