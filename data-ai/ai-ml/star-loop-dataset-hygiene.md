# star-loop-dataset-hygiene

**Issue:** self-improvement-loop-noise / memorization-fake-progress
**Date:** 2026-08-14
**Status:** verified-live

## Symptom
A STaR-style loop (sample → verify → keep verified pairs → fine-tune) reports a
dramatic solve rate (e.g. 53/54, "98%") that looks like real generalization —
but the next fine-tune either (a) regresses on the eval suite or (b) only
"passes" because the eval set was contaminated by training data.

## Root cause
Two silent failure modes recur:

1. **Dataset duplication.** A generator run with a fixed seed emits identical
   tasks on every round; the loader keeps both copies; 3 epochs × duplicates
   become effectively 6 epochs on the unique subset → overfitting. A 111-row
   dataset contained 52 exact duplicate pairs.
2. **Seed-variance noise on small suites.** Two fine-tunes with the *identical*
   data recipe (only the shuffle/init seed differs) scored 7/9 and 5/9 on the
   same 9-task suite — a ±2-3 swing is pure run-to-run variance, not signal.
   A 9-task eval cannot tell a real improvement from noise.

## Fix
- **Cross-round dedup registry.** Every generated task's text is hashed
  (`sha1(task)`) into a persistent registry; the generator re-rolls until it
  produces a hash never seen in *any* round. The seed no longer matters.
- **Dedupe before training.** JSON-hash exact-match on each example. Keep the
  raw duplicate-bearing dataset on disk if you want to study the effect, but
  train on the deduped set.
- **Hold out enough fresh tasks for honest eval.** A 9-task suite is noise at
  ±2-3; use ≥32 registry-deduplicated tasks per eval round, and evaluate the
  fine-tune on a *different* set than it was trained on.

## Verification
- 52/111 duplicates removed → unique set; verify with a hash counter.
- Same-recipe two-seed runs differ by ≤3 tasks on the small suite, ≥10 on the
  32-task fresh set — the latter is the only trustworthy score.

## Gotchas
- A solve-rate reported on a *generated-variation* set is meaningless until you
  check answer-overlap with prior training data (compare assistant contents,
  not just prompts).
- "Fresh-family variety matters more than volume": 32 genuinely-fresh tasks beat
  54 near-duplicates for both training signal and eval honesty.
- Fewer fine-tune epochs on a *duplicates-included* set can empirically match
  more epochs on a deduped set — the effective-epoch count is what matters.
  Don't assume dedup is always strictly better; measure both.

## Related
- `ollama-corrupts-local-chatglm-gguf`
