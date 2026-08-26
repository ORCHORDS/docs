# Treat Logits Processing and Renormalization as an Inference Contract

**Issue:** Logits processors and warpers can alter score normalization. Reordering processors or changing `renormalize_logits` may change beam ranking, sampling, and any downstream interpretation of returned scores.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Version the ordered processor/warper configuration with the model, tokenizer, generation configuration, and Transformers version.
- Set `renormalize_logits` deliberately; do not inherit a library default without recording it.
- Separate score-shaping policy from stopping criteria and document custom processor preconditions.
- Validate incompatible constraints at configuration load rather than during a live generation.
- Treat generation-policy changes as model-behavior changes requiring evaluation.

## Verification

- Use fixed seeds and prompts to snapshot processed scores and selected tokens at representative steps.
- Assert finite scores and, when normalization is required, an expected probability mass within tolerance.
- Exercise beam, greedy, and sampling paths separately because they interpret scores differently.
- Metamorphically test processor ordering and fail review if an unintended reorder changes output.

## Gotchas

A processor can make all candidate tokens invalid. Renormalization cannot repair an empty feasible set. Returned generation scores are not automatically calibrated probabilities, even if exponentiated scores sum to one.

## Official sources

- [Transformers text generation configuration](https://huggingface.co/docs/transformers/main/en/main_classes/text_generation)
- [Transformers generation utilities](https://huggingface.co/docs/transformers/main/en/internal/generation_utils)
