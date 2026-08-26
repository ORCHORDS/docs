# prompt-versioning

**Issue:** Managing prompt versions across environments and models
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Untracked prompt changes cause production regressions that are hard to debug.

## Pattern / Solution
```python
# Store prompts in version-controlled files
# prompts/summarize_v2.txt

# Load with version tag
import hashlib

class PromptRegistry:
    def __init__(self, prompt_dir: str):
        self.dir = Path(prompt_dir)

    def get(self, name: str, version: str = "latest") -> str:
        path = self.dir / f"{name}_{version}.txt"
        text = path.read_text()
        return text

    def hash(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()[:8]

# Log prompt hash with every LLM call
logger.info({"prompt_hash": registry.hash(prompt), "model": model, "tokens": usage})
```

## Gotchas
- Never edit prompts in place — create new version files
- Store prompt hash alongside model outputs for debugging
- Use semantic versioning: v1.0, v1.1 for minor, v2.0 for breaking

## Related
- `prompt-testing-evals.md`
- `llm-ab-testing.md`
