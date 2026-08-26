# prompt-testing-evals

**Issue:** Systematically testing prompts with evaluation frameworks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Prompt changes break existing behavior without a regression testing framework.

## Pattern / Solution
```python
# Using promptfoo for prompt evals
# promptfoo.yaml
prompts:
  - "Summarize this in one sentence: {{text}}"
  - "TL;DR: {{text}}"
providers:
  - openai:gpt-4o
  - anthropic:claude-opus-4-5
tests:
  - vars:
      text: "The quick brown fox..."
    assert:
      - type: contains
        value: "fox"
      - type: llm-rubric
        value: "Is the summary accurate and concise?"

# Run: promptfoo eval
```

## Gotchas
- Use LLM-as-judge sparingly — it adds cost and has its own biases
- Always include adversarial test cases, not just happy path
- Track eval scores in CI to detect prompt regressions

## Related
- `prompt-versioning.md`
- `agent-evaluation-patterns.md`
