# AI Agent Context & Prompt Debugging (Cursor, Claude Code, Copilot, ZCode)

> Diagnosing why an AI coding assistant produces wrong, lazy, or hallucinated
> output. The bug is rarely the model — it's almost always the context window,
> tool-results ordering, or instructions being silently overridden.

---

## When to use this

- The agent "knows" something (it's in the file) but ignores it when answering.
- Tool calls return correct data but the agent's reply doesn't use it.
- Output quality degrades mid-session despite identical prompts.
- Two agents with the "same" system prompt behave differently.
- The agent hallucinates an API that doesn't exist, or uses a deprecated one.

## Symptom

The agent produces confident but wrong output, or stalls / repeats itself, even
though the relevant information is in the codebase or earlier in the conversation.

```
User: "Fix the bug"
Agent: *edits the wrong file* / *invents a function that doesn't exist*
```

Root cause categories, in rough frequency order:
1. Context window starvation (most common)
2. Tool-result staleness or wrong ordering
3. Instruction precedence / shadowing
4. Stale cache of repo embeddings
5. Wrong model tier silently selected

## Diagnosis steps

### 1. Count tokens actually in context

Most agents expose this:
- Cursor: `Cmd+L` then hover the context chip; or check the bottom status bar.
- Claude Code: `/context` shows the current token count and budget.
- Copilot: hover the suggestions icon; full context isn't shown — use the
  "Related Files" panel to see what was attached.

If you're >80% of the context limit, the oldest tool results are being silently
truncated. The model will then answer from training data (which is months stale).

```bash
# Quick token estimate for what you're about to paste
echo "$PROMPT" | wc -c | awk '{print int($1/4), "approx tokens"}'
```

### 2. Verify what the agent actually received

Treat the agent like a black-box API. Ask it:

> "Without doing anything, list every file whose contents are currently in your
> context, and the token count each one occupies."

If a file you assumed was attached isn't listed, the attachment silently failed.
This is the #1 cause of "the agent ignored my types file".

### 3. Check tool-result ordering

LLMs exhibit strong **recency bias**. If the most recent tool result is an
unrelated file (e.g. the README), the agent will overweight it. Re-run the
relevant search last, right before asking the question.

### 4. Check instruction precedence

In ZCode and Claude Code, precedence is roughly:
1. Built-in safety / policy (highest, not visible to you)
2. `AGENTS.md` at workspace root
3. `CLAUDE.md` / `.cursorrules` / equivalent
4. Per-session system additions
5. The user's latest message (lowest)

If `AGENTS.md` says "always run tests before claiming done" and the agent skips
tests, check whether a more specific skill or sub-AGENTS.md is overriding it.
Nested `AGENTS.md` files in deeper directories win for tasks rooted there.

### 5. Force a clean reload of repo context

```bash
# RAG/embedding caches go stale after git operations
rm -rf .claude/cache .cursor/index   # agent-specific
# Then restart the agent and re-index
```

For semantic-code-search tools (Sourcegraph Cody, Cursor codebase index), a
stale index returns pre-rename symbols — leading the agent to old paths.

## Gotchas

- **"Lazy" output is usually a context cap, not laziness**: when the agent
  writes `// ... rest of the function ...` it hit an output-token cap. Raise
  `max_tokens` or split the task — don't beg the model to "be thorough".
- **Tool results don't refresh**: if you edited a file via the agent and then
  ask a follow-up, the agent may still "see" the pre-edit version from earlier
  in context. Re-read the file explicitly (`read the file again`).
- **`AGENTS.md` typos**: a single malformed frontmatter block can cause the
  whole file to be silently dropped. Validate YAML frontmatter separately.
- **Shadow skills**: a higher-precedence plugin skill with the same name as
  yours will intercept triggers. List active skills and check precedence.
- **Model tier drift**: "Pro" / "Max" plans silently downgrade under load to a
  smaller model. The agent's behaviour changes mid-session for no apparent
  reason. Check the model name in agent settings, not the marketing label.
- **Image attachments don't OCR uniformly**: screenshots with code are read by
  a vision model; small text and syntax are often wrong. Paste code as text.
- **Date injection**: many agents inject "today's date" into the system prompt
  to ground web search. If the system clock is wrong (WSL, Docker, CI), the
  agent will confidently state the wrong year and reject "future" APIs.
- **System prompts beat user prompts**: if an `AGENTS.md` rule contradicts
  your explicit instruction, the rule usually wins. Edit the file, don't argue.
- **`pnpm` vs `npm` confusion**: if the agent keeps using the wrong package
  manager, it's reading an out-of-date lockfile or `package.json` from context.
  Delete the wrong lockfile from disk, not just from the agent's attention.
- **Agent logs**: ZCode stores session transcripts under
  `~/.zcode/projects/<hash>/`; Claude Code under `~/.claude/projects/`. Reading
  the raw JSONL of the last session reveals exactly what was in context —
  invaluable for reproducibility.

## Quick fixes by failure mode

| Failure | Likely cause | Fix |
|---|---|---|
| Ignores a file | Not in context | `@file` or paste contents explicitly |
| Hallucinates API | Stale training data | Force web search / docs lookup first |
| Stops mid-output | Output token cap | Split task, raise `max_tokens` |
| Forgets earlier instruction | Context truncation | Repeat key constraint in latest msg |
| Wrong tool used | Tool description weak | Rewrite skill `description` field |
| Skips required step | Higher-precedence override | Check `AGENTS.md` / skill precedence |

## See also

- `mcp-inspector-debugging.md` — when the agent's tools themselves are broken
- `mcp-server-debugging.md` (if present) — MCP transport issues
- `vscode-extensions-essential.md` — agent extensions worth installing
