# multimodal-vision-patterns

**Issue:** Integrating vision capabilities into LLM applications requires different prompting and data handling patterns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A vision-enabled LLM fails to answer specific questions about images — either describing the image generically rather than answering the question, or hallucinating details not visible in the image.

## Pattern / Solution
Always pair images with specific, directed questions rather than open-ended prompts. For multi-image tasks, label images explicitly (Image 1, Image 2). Pre-process images: resize to model-optimal resolution, convert to supported format (JPEG/PNG/WebP), and compress to stay within token budgets. Use base64 for API calls; use URLs only if the image is publicly accessible.

Request structured output alongside images for consistent downstream processing.

## Gotchas
- Image tokens are expensive (hundreds of tokens per image depending on resolution) — resize before sending
- Models refuse to identify real people's faces — design around this for user-facing identity features
- Text in images (small print, handwriting) may be misread — combine with dedicated OCR for critical text extraction

## Related
- image-analysis-patterns
- ocr-with-llm
- llm-token-counting
