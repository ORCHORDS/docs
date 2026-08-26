# ocr-with-llm

**Issue:** Traditional OCR fails on handwriting, complex layouts, and poor-quality scans that vision LLMs handle better
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A document processing pipeline uses Tesseract for OCR but accuracy on invoices with mixed fonts, rotated text, and low-contrast backgrounds is only 70%. Users need 95%+ accuracy with structure preservation.

## Pattern / Solution
Use vision LLMs (GPT-4o, Gemini Vision) for OCR on complex documents. Prompt for structured extraction rather than raw text dump. For PDFs, render each page as high-DPI image (300 DPI minimum) before sending. For tables, ask for markdown table format to preserve structure.

For high-volume workloads, use traditional OCR as a first pass and vision LLM only for low-confidence pages (Tesseract confidence < 80%).

## Gotchas
- Vision LLM OCR is 10-50x more expensive than Tesseract — use selectively on complex documents
- Models may silently correct OCR errors (e.g., misread dates get plausible replacements) — for verbatim extraction, instruct explicitly
- Multi-column layouts can cause reading order errors — specify expected reading order in the prompt

## Related
- image-analysis-patterns
- multimodal-vision-patterns
- llm-for-extraction
