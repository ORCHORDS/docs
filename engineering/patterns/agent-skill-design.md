# agent-skill-design

**Issue:** Designing effective SKILL.md files (Claude Code / Mavis / Claude Desktop)
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)

## Symptom

You write a SKILL.md. It looks great. The body is 300
lines, the description is 50 words. You install it. Claude
never invokes it. You rewrite the description. Now Claude
invokes it on every request, including ones that have nothing
to do with the skill. You add "when NOT to use" text to the
body. It helps a little. You add examples. The skill is now
700 lines and barely fits. The team can't tell which skills
exist or when to use them. New skills get added but never
trigger. The whole skill system is dead weight.

## Root cause

**The description is a trigger, not documentation.** Claude
reads ~100 tokens per skill at session start and pattern-matches
against the user's prompt. A vague description means a skill
that never fires; a precise one means it fires exactly when
it should. Most skill authors treat the description like a
README header instead of a routing rule. The body is what
gets read after triggering — make the body lean and put the
load-bearing details in the description.

**Source:** Anthropic platform docs:
- Skill authoring best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Agent Skills overview: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Claude Code skills: https://code.claude.com/docs/en/skills
- Equipping agents for the real world: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- skill-creator: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md

**Source:** Industry analysis:
- Duet guide: https://duet.so/guides/claude-code-skills-complete-guide
- bleap finance: https://www.bleap.finance/en-us/blog/how-to-create-claude-skills
- Firecrawl: https://www.firecrawl.dev/blog/best-claude-code-skills
- developersdigest: https://www.developersdigest.tech/blog/best-claude-code-skills-2026
- SmartScope: https://smartscope.blog/en/generative-ai/claude/claude-code-best-practices-advanced-2026/

## The "skill" concept

A skill is a folder of instructions, scripts, and resources
that an agent (Claude Code, Mavis, Claude Desktop) loads
on-demand to perform a specialized task in a repeatable
way. At its minimum it's a `SKILL.md` with YAML frontmatter
(`name` + `description`) and Markdown body instructions.

**Three levels of progressive disclosure (Anthropic):**
- **L1 — Metadata:** `name` + `description` loaded into the system prompt at session start. ~100 tokens per skill.
- **L2 — Body:** the SKILL.md body. Loaded when Claude determines relevance. Should be < 500 lines.
- **L3 — Bundled resources:** reference files, scripts, templates in subfolders. Loaded as needed, scripts can execute without loading.

The win: many skills installed → small context cost. Only
the skills relevant to the current task pay the body cost.

## The "frontmatter" pattern

The `SKILL.md` frontmatter is the load-bearing metadata. The
body is just the second-level detail.

**`name` field:**
- Max 64 characters
- Lowercase letters, numbers, hyphens only
- No XML tags
- No reserved words: `"anthropic"`, `"claude"`
- Gerund form preferred: `pdf-processing`, `code-reviewing`, `distill-lesson` (verb + -ing)
- The directory name becomes the slash command

**`description` field (the trigger):**
- Max 1,024 characters
- Non-empty
- No XML tags
- **Always third person** (injected into system prompt; inconsistent POV causes discovery problems)
- Includes BOTH **what** the skill does AND **when** to use it
- Specific and includes key terms (not vague)
- "Pushy" — explicitly list the scenarios that should activate it, including implicit ones
- 100-200 words is the sweet spot

**Optional fields:**
- `disable-model-invocation: true` — require explicit `/skill-name` invocation; don't auto-trigger
- `allowed-tools: [...]` — restrict which tools the skill can use while active (principle of least privilege)
- `model: inherit` — for agent files; usually inherit session model
- `display_title` — human-readable title (managed agents only)

**Example (the shipped `distill-lesson` skill in this repo):**
```yaml
---
name: distill-lesson
description: Use when the user runs /reflect, when the Stop hook nudges about
captured failures, or when asked to "learn from this", "capture a lesson",
"remember this for next time", "what did this session teach". Reads the session
run-log, classifies each failure, and PROPOSES a memory/skill/AGENTS.md edit —
asking yes/no before writing anything. Never writes silently.
---
```

Note: 100+ words, "Use when..." prefix, third person, lists
trigger phrases explicitly ("when the user runs /reflect",
"when the Stop hook nudges", "asked to learn from this"),
includes the "what" (PROPOSES, never writes silently), and
includes the "when NOT" implicitly (it's a no-op for
non-distill requests).

## The "body" pattern

The body is what Claude reads after the description triggers
it. Constraints:
- **< 500 lines** ideal (Anthropic's hard cap is around 1MB but performance degrades fast)
- **State what to do, not how or why** — apply the same conciseness test as CLAUDE.md content
- **Every line is a recurring token cost** — skill content stays in context across turns while active
- **Reference external files explicitly** — "For unusual file types, see `reference/edge-cases.md`"

Good body structure (per the shipped skills):
1. **Title** + 1-line purpose
2. **When to use** / When NOT to use (separate sections)
3. **Inputs** — what the skill reads/expects
4. **Process / Steps** — numbered, no fluff
5. **Templates / Patterns** — concrete examples with code
6. **Hard rules** — explicit "never" / "always"
7. **Anti-patterns** — what not to do

The shipped `research-with-agents` skill is a good example:
~100 lines, three sections (When to use, The workflow, What
this prevents), concrete code, anti-patterns section at the end.

## The "description is the trigger" pattern

This is the #1 design rule. The description is what Claude
pattern-matches against at every turn. Vague = undertrigger;
too broad = overtrigger; specific = fires exactly when it should.

**Anti-pattern: vague description**
```yaml
description: Helps with documents.
```
**Why bad:** Will fire on any document-related request, including ones outside the skill's scope.

**Anti-pattern: keyword stuffing**
```yaml
description: PDF, document, file, form, text, extract, parse, table, merge, split
```
**Why bad:** No semantic meaning; Claude can't tell when a "PDF" mention is about the file format vs. a specific tool.

**Good: what + when + trigger phrases**
```yaml
description: Extract text and tables from PDF files, fill forms, merge documents.
Use when working with PDF files or when the user mentions PDFs, forms, or
document extraction. Triggers on "read this PDF", "fill out this form", "merge
these documents".
```
**Why good:** Tells Claude what the skill does (extract/fill/merge), when to use it (PDFs, forms, document extraction), and gives concrete trigger phrases to pattern-match against.

**Pushy for undertriggering (Anthropic's specific guidance):**
"Claude has a tendency to 'undertrigger' skills — to not use
them when they'd be useful." To combat this, the description
should explicitly list the implicit triggers:
```yaml
description: Make sure to use this skill whenever the user mentions
dashboards, data visualization, internal metrics, or wants to display any
kind of company data, even if they don't explicitly ask for a 'dashboard.'
```

## The "one skill, one job" pattern

Split anything you describe with "and." If your description
has "Use when X, Y, and Z," that's three skills.

**The 3-bucket rule of thumb:**
- **Read-only analysis:** `read-only-analysis` (Read, Grep, Glob only)
- **Write operation:** `code-writing` (Edit, Write)
- **Delegation / orchestration:** `task-coordinator` (Agent)

The shipped `distill-lesson` is one job: propose lessons from
failures. The shipped `retrieve-lessons` is one job: recall
relevant lessons. Different skills, not one mega-skill.

The 6-tool pattern: a single skill should have ~3-6 well-defined
tools, sections, or behaviors. More than that = split.

## The "vs CLAUDE.md / hooks / subagents" pattern

Different surfaces solve different problems. Pick the right one:

| Need | Use | Why |
|---|---|---|
| **Always-on project guidance** | `CLAUDE.md` (short) | Loaded every session; can't bloat |
| **Contextual reusable knowledge** | **Skill** | Loads on demand; pays only for relevance |
| **Enforced rule** | **Hook** or **permission** | Runs deterministically; can block |
| **Delegation boundary** | **Subagent** | Isolates context; can run in parallel |
| **A fact about user/project** | **Memory** | Persisted; retrieved by similarity |
| **User-invoked workflow** | **Slash command** | Explicit; doesn't auto-trigger |

A common mistake: putting a "code review checklist" in
CLAUDE.md. Wrong — it bloats every session. Right: a
`code-reviewing` skill, triggered when the user asks for a
review.

## The "when to create a skill" pattern

Create a skill when:
- You paste the same 3+ paragraphs of context into a session more than twice a week
- A workflow is repeatable across projects
- You want specialized output (style, format, domain knowledge)
- An existing skill description can't capture the scope

Don't create a skill when:
- One-off task (use a slash command)
- Always-on (use CLAUDE.md)
- Enforced rule (use a hook)
- Pure delegation (use a subagent)

## The "progressive disclosure" pattern

For skills with > 500 lines of content, split into a directory:

```
my-skill/
  SKILL.md            # the procedure, ~300 lines, always loaded when triggered
  reference/
    edge-cases.md     # loaded only when needed
    api-reference.md  # loaded only when needed
    full-style-guide.md
  scripts/
    validate.sh       # executed, not loaded
  templates/
    report.md         # copied + filled
```

In `SKILL.md`, link to the references explicitly:
> "For unusual file types, see `reference/edge-cases.md`."

**Why this matters:** the body is a recurring token cost.
A 1000-line skill that loads 1000 lines on every trigger
kills context budget. Splitting into 300-line body +
references on demand keeps the cost proportionate to actual
need.

## The "trigger test" pattern

Before shipping any skill, run the trigger test:

1. Write down 5 prompts a real user would type to invoke this skill (should-trigger)
2. Write down 3 prompts a real user would type that should NOT invoke this skill (should-not-trigger)
3. Run all 8 in fresh sessions
4. Check whether the skill loaded in each case

If a should-trigger prompt didn't fire → description is too vague. Rewrite with concrete trigger phrases.

If a should-not-trigger prompt fired → description is too broad. Add "NOT" clauses or scope the trigger phrases.

The Anthropic `skill-creator` skill automates this with 20
trigger eval queries (mix of should-trigger and should-not-trigger)
and runs an optimization loop to find the best description.

## The "shipped skills in this repo" pattern

This repo's `packages/zcode-plugin/skills/` ships 4 skills
that demonstrate these patterns:

| Skill | Trigger phrase | Body size | Pattern notes |
|---|---|---|---|
| `retrieve-lessons` | "remember", "recall lessons", "what did I learn here" | ~50 lines | Single job; SessionStart hook also runs it |
| `distill-lesson` | "/reflect", "capture a lesson", "what did this session teach" | ~100 lines | Suggest-only mode; never writes silently |
| `research-with-agents` | "implement", "build", "add feature", "integrate", "set up" | ~100 lines | Anti-pattern section; "When to use" list |
| `route-task` | "before you start", "can the local model do this", "should I use Claude" | ~60 lines | Decision framework; parallelization pattern |

All four are < 120 lines body, all have `Use when...`
descriptions, all have trigger phrases listed explicitly. They
are the working examples of the patterns in this entry.

## The "skill creation loop" pattern

The Anthropic `skill-creator` workflow (a skill that creates
skills):

1. **Decide intent** — what should this skill enable? When should it trigger? What's the expected output? Set up test cases?
2. **Draft** — write a first version of the SKILL.md
3. **Create trigger eval** — 20 realistic queries: should-trigger vs should-not-trigger, mix of lengths, focus on edge cases
4. **Run with skill** — `claude-with-access-to-the-skill` on the test prompts
5. **Evaluate** — qualitative review + quantitative metrics
6. **Iterate** — rewrite the skill, especially the description, based on results
7. **Scale** — expand the test set; re-run

Optimize the **description** separately and last — it's
the single highest-leverage change. Anthropic's
`skill-creator` includes a `python -m scripts.run_loop` that
runs an optimization loop over the description against the
trigger eval, returning `best_description` to apply.

## The "anti-patterns" anti-patterns

### 1. Vague description
- **Issue:** Skill never fires
- **Fix:** Specific trigger phrases; "Use when..." prefix

### 2. Over-broad description
- **Issue:** Skill fires on every request
- **Fix:** Negative triggers; scope to a domain

### 3. Big body
- **Issue:** Wastes context; skill is slow to load
- **Fix:** < 500 lines; reference files for depth

### 4. Keyword-stuffed description
- **Issue:** Semantic match fails
- **Fix:** Natural language description of situations, not keyword lists

### 5. No "when NOT to use" section
- **Issue:** Skill misfires on borderline cases
- **Fix:** Explicit anti-trigger examples in body

### 6. Using CLAUDE.md for a workflow
- **Issue:** Bloats every session, not just relevant ones
- **Fix:** Make it a skill with a clear trigger

### 7. Using a hook for a recommendation
- **Issue:** Hooks can't conditionally recommend; they can only enforce
- **Fix:** Use a skill (the agent decides when to invoke) or a hook (always enforced)

### 8. Skill that depends on specific code in the repo
- **Issue:** Skill breaks when refactored
- **Fix:** Skill is workflow + context, not implementation

### 9. No trigger test
- **Issue:** You don't know if the description works
- **Fix:** 5 should-trigger + 3 should-not-trigger, run in fresh sessions

### 10. Description in first or second person
- **Issue:** POV inconsistency with system prompt
- **Fix:** Third person only

## The "skill checklist" pattern

For a production skill:
- [ ] `name` is gerund form (verb + -ing), max 64 chars, kebab-case
- [ ] `name` doesn't contain "anthropic" or "claude" (reserved)
- [ ] `description` is 100-200 words, third person
- [ ] `description` starts with "Use when..."
- [ ] `description` includes 3+ concrete trigger phrases
- [ ] `description` includes both what and when
- [ ] `description` lists implicit triggers ("even when user doesn't explicitly ask")
- [ ] Body is < 500 lines
- [ ] Body has "When to use" and "When NOT to use" sections
- [ ] Body has a numbered Process / Steps section
- [ ] Body has a Templates / Examples section
- [ ] Body has an Anti-patterns section
- [ ] Big content is in `reference/*.md`, linked from body
- [ ] Deterministic logic is in `scripts/*`, called from body
- [ ] 5 should-trigger eval prompts defined
- [ ] 3 should-not-trigger eval prompts defined
- [ ] All 8 run in fresh sessions; skill fires correctly
- [ ] Description optimized (separately) for triggering accuracy
- [ ] If the skill does writes, requires explicit user confirmation (suggest-only)

## Verification
- **Test:** 5 should-trigger prompts all fire the skill
- **Test:** 3 should-not-trigger prompts don't fire the skill
- **Test:** Body is < 500 lines; total skill + references is well-bounded
- **Test:** Skill content stays in context across turns while active
- **Live:** Run the skill in a real session; observe whether it triggers on natural-language requests
- **Audit:** Re-test quarterly; descriptions drift

## Gotchas
- **The "vague description" anti-pattern.** Most common cause of skills that never fire.
- **The "big body" anti-pattern.** Skill content is a recurring cost.
- **The "first person" anti-pattern.** POV mismatch with system prompt.
- **The "CLAUDE.md workflow" anti-pattern.** Bloat every session for a niche need.
- **The "keyword stuffing" anti-pattern.** Semantic match beats keyword match.
- **The "no trigger test" anti-pattern.** You don't know it works.
- **The "implicit triggers omitted" anti-pattern.** "Even when user doesn't explicitly ask" matters.

## Related
- The shipped `packages/zcode-plugin/skills/` — 4 working examples
- `packages/zcode-plugin/README.md` — the "Suggest only" mode contract
- `packages/zcode-plugin/skills/distill-lesson/SKILL.md` — the canonical example
- `packages/zcode-plugin/skills/research-with-agents/SKILL.md` — the parallel-subagents pattern
- `patterns/mcp-server-patterns.md` — sibling pattern: tools descriptions vs skill descriptions
- `lessons/scope-discipline.md` — applies to skills too: one skill = one concern
- `lessons/lazy-fail-evidence-discipline.md` — test your skills with real prompts
- `fleet/LESSONS.md` — the same lessons apply to skills as to fleet code

**Source URLs (verified 2026-08-09):**
- Anthropic — Skill authoring best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic — Agent Skills overview: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Anthropic — Engineering: Equipping agents: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Anthropic — skill-creator: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
- Claude Code — Skills: https://code.claude.com/docs/en/skills
- Duet — Claude Code Skills Complete Guide: https://duet.so/guides/claude-code-skills-complete-guide
- bleap — How to Create Claude Skills: https://www.bleap.finance/en-us/blog/how-to-create-claude-skills
- Firecrawl — Best Claude Code Skills: https://www.firecrawl.dev/blog/best-claude-code-skills
- developersdigest — Best Claude Code Skills 2026: https://www.developersdigest.tech/blog/best-claude-code-skills-2026
- SmartScope — Claude Code Best Practices 2026: https://smartscope.blog/en/generative-ai/claude/claude-code-best-practices-advanced-2026/
- The shipped skills in this repo: `packages/zcode-plugin/skills/`
