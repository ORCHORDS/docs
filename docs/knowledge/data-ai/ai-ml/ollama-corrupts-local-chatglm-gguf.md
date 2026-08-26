# ollama-corrupts-local-chatglm-gguf

**Issue:** ollama-drops-quotes / chatglm-gguf-import-corruption
**Date:** 2026-08-14
**Status:** verified-live (workaround)

## Symptom
A locally fine-tuned chatglm-family GGUF (e.g. a GLM-4-9B QLoRA) served through
**Ollama 0.32.6** drops single quote characters in generated code —
`['(','),'[','{']` instead of `['(', ')', '[', '{']` — and breaks regex/escape
precision. The **same Q4 file served through llama.cpp's `llama-server`**
emits pixel-perfect code. Registry models (e.g. `ollama pull glm4:9b`) are fine;
only models created locally via a `Modelfile` (`FROM <local.gguf>`) corrupt.

## Root cause
Ollama's GGUF importer mangles chatglm-family tokenizers when it re-derives
them from the locally-created manifest. Registry models bypass that path (they
ship pre-validated), so they load clean — locally-created chatglm models do not.

A separate contributing factor: `convert_hf_to_gguf.py` (old llama.cpp builds)
emits chatglm GGUFs **without `tokenizer.ggml.merges`**, so the unpatched file
won't load at all ("cannot find tokenizer merges in model file"). The standard
workaround has been to transplant the tokenizer from a registry glm4 GGUF
(`patch_tokenizer`-style script). That makes the file load, but when Ollama
then re-imports it, the quote-dropping appears.

## Fix
Serve locally-created chatglm models via `llama-server`, never Ollama:
```
llama-server -m model.gguf -ngl 99 -c 8192 --jinja --chat-template-file template.jinja --alias <name>
```
Keep Ollama for: (a) registry models that load via `ollama pull`, and (b) the
unavoidable `ollama create` when you need a model registered under a name (but
serve through `llama-server` behind it).

## Verification
- Same `example project-v3-q4_k_m.gguf` through Ollama: benchmark 0/4, all syntax
  errors are dropped quotes.
- Same file through `llama-server` raw `/completion`: `["(", ")", "[", "]"]`
  pixel-perfect.

## Gotchas
- The error is silent on natural-language answers (identity, summaries look
  fine) — only surfaces in code, where a dropped `"` or `'` is fatal. Audit
  generated code, not chitchat, when suspecting this.
- `ollama rm` + `ollama create` does not help; the corruption is in the import
  path, not the artifact.
- Test the serving path, not just the weights, after any GGUF rebuild.

## Related
- `llamacpp-streaming-fetch-undici-timeout` (companion gotcha on the llama-server path)
- `star-loop-dataset-hygiene`
