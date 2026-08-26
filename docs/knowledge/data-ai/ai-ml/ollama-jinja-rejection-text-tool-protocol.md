# ollama-jinja-rejection-text-tool-protocol

**Issue:** Custom fine-tuned weights need a tool-calling chat template, but `ollama create` REJECTS Jinja2 templates with a Go validator error (observed on Ollama 0.32.6) — no amount of template fixing satisfies it. Meanwhile the model's tool calling must work today. Found while shipping example project-1 weights with native tool support.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two-path resolution

1. **`ollama create` with Jinja: blocked by design.** The Go-side template validator rejects most non-trivial Jinja2 chat templates; this is a host limitation, not a template bug — stop iterating on the template.
2. **`llama-server --jinja` accepts the same templates.** Running llama.cpp's server directly (with the Jinja flag) renders the Modelfile template fine — the validator lives in Ollama's Go layer, not llama.cpp.
3. **The escape hatch is a text protocol.** Define a plain-text TOOL_CALL convention in the system prompt (e.g. the model emits `TOOL_CALL: {"name": ..., "args": ...}` and parses tool results fed back as plain text) — zero template dependency, works on any server.
4. **Text protocols can be zero-shot** — the example project weights followed the printed convention immediately with no fine-tuning for it, because instruction-following transfers.
5. **Wrap it once:** a thin client layer that renders TOOL_CALL text into OpenAI-style `tool_calls` objects keeps downstream code template-agnostic.

## Decision rules

1. **Need Ollama's model management (pulls, aliases)?** → accept a minimal/no-Jinja template, use the text protocol for tools.
2. **Need exact template rendering?** → bypass Ollama, run `llama-server --jinja` and talk to its OpenAI-compatible endpoint.
3. **Need both eventually?** → ship the text protocol now (it works everywhere), keep the proper template as a backlog item — don't block tool-calling on host validators.
4. **Test the path before building on it:** one curl round-trip proving a tool call round-trips end-to-end beats an afternoon of template archaeology.
5. **Pin versions in docs** — validator behavior differs across Ollama releases; what 0.32.6 rejects may change, so re-test on upgrade.

## Broader lesson

1. **Host-side validators are walls, not puzzles** — when the error comes from the runtime's validation layer, the fix is a different runtime, not a better template.
2. **Plain-text protocols are the portability layer** of last resort and often first resort for custom weights.
3. **Distinguish "my artifact is wrong" from "my host refuses the artifact class"** — the debugging path diverges completely at that fork.
4. **Keep an OpenAI-shaped facade** over whatever backend actually runs; everything downstream (fleets, routers, clients) speaks that dialect.
5. **Document the workaround with the version numbers** so the next session doesn't re-diagnose the rejection from scratch.

## Related

- `llm-fallback-provider-rotation.md`
- `vram-budget-model-selection-math.md`
