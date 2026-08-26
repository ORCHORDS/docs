# llm-for-classification

**Issue:** Using LLMs for text classification is powerful but expensive and slow compared to fine-tuned models
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You need to classify support tickets into 20 categories. Zero-shot LLM classification is accurate but costs $0.10 per ticket at scale. A fine-tuned BERT is fast and cheap but requires labeled data you do not have.

## Pattern / Solution
Start with LLM few-shot classification to generate labeled data quickly. Use that data to fine-tune a small model (DistilBERT, SetFit). Keep the LLM as a fallback for low-confidence edge cases only. For 10+ classes, enumerate all labels in the prompt and ask for JSON output with confidence.

```
Classify the following ticket into exactly one of: [billing, technical, shipping, returns, other].
Respond with JSON: {"category": "...", "confidence": 0.0-1.0}

Ticket: {text}
```

## Gotchas
- LLMs drift on rare classes — include at least one example of each class in few-shot examples
- Classification tasks with 50+ classes benefit from hierarchical prompting (coarse then fine)
- Confidence scores from LLMs are not calibrated — use them for routing to human review, not as true probabilities

## Related
- llm-for-extraction
- llm-structured-output
- fine-tuning-when-to-use
