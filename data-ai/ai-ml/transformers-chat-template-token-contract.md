# Transformers Chat-Template Token Contract

**Issue:** Chat models trained with different control-token layouts can silently lose quality when a generic message formatter adds the wrong assistant prefix or duplicates BOS/EOS tokens.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use the tokenizer’s model-specific chat_template and version it with the model artifact.
- Use add_generation_prompt for inference only when the template/model expects an assistant-start marker.
- Use continue_final_message for prefilling and never combine it with add_generation_prompt.
- When rendering text before tokenization, disable automatic special-token addition if the template already emits them.

## Verification

- Snapshot rendered token IDs for representative system, user, assistant, tool, and prefill conversations.
- Compare training preprocessing and inference formatting.
- Run a behavioral regression that detects user-message continuation instead of assistant response.

## Gotchas

- Templates are executable formatting logic, not cosmetic strings.
- A template that parses successfully can still be incompatible with model training.

## Official sources

- https://huggingface.co/docs/transformers/chat_templating
