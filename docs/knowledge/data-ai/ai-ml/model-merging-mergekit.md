# model-merging-mergekit

**Issue:** Teams accumulate multiple fine-tunes of the same base model — one for code, one for chat style, one for a domain — and running, deploying, and updating them separately multiplies serving cost and operational surface. Model merging combines checkpoint weights directly, with no further training, to produce one model that carries several capabilities. mergekit (Arcee AI, with the MergeKit paper at arXiv 2403.13257) made SLERP, TIES, DARE, task arithmetic, passthrough, and model-soup merges reproducible YAML configs runnable on modest hardware. Merging is cheap to try, empirically unpredictable, and only sound between checkpoints sharing a base — so the engineering discipline lives in recipe selection, evaluation, and treating merges as versioned artifacts rather than alchemy.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Merging methods and when each applies

1. **SLERP.** Spherical interpolation of two models' weights along a geodesic. It is the classic two-model method — well-behaved, widely used, but not defined beyond two checkpoints; for three or more models it requires pairwise chaining or switching to linear-family methods.

2. **Linear and task arithmetic.** Weighted averaging of full checkpoints, or applying fine-tune deltas (task vectors) with positive or negative signs. Negative deltas (subtracting an unwanted behavior) are a distinctive capability, and linear methods scale naturally to many models — the basis of model soups.

3. **TIES.** Resolves two known failure modes of naive averaging: sign conflicts (deltas that pull opposite directions cancel destructively) and redundant parameter changes. It trims small deltas, elects an agreed sign per parameter, and merges only the consistent mass. TIES typically outperforms plain averaging on multi-model merges.

4. **DARE.** Drops the large majority of fine-tune delta parameters as insignificant (they approximate randomly perturbing a base model) and rescales the survivors. DARE composes with TIES as dare_ties — the most popular drop-in recipe for combining multiple fine-tunes with less interference.

5. **Passthrough and layer stacking.** Concatenating layers from different models to build a larger frankenmodel. Produces occasional community breakthroughs on odd configurations, but output is the least predictable of any method; treat as experimentation only.

## When merging makes sense

1. **Same base, sibling fine-tunes.** Merging works because fine-tunes stay in a shared loss basin of their common base. Merging unrelated models (different pretraining) produces garbage; this is the first and hardest gate.

2. **Capability bundling for deployment consolidation.** The highest-value production use is collapsing N served models into one: merge the code and chat fine-tunes, serve one artifact, halve the GPU footprint. Fine-tune cost for a "combined" model is avoided entirely.

3. **Behavior dialing.** Small-weight merges (0.2-0.3 of a style or safety fine-tune into an instruct base) act like a tunable knob for tone or refusal behavior without a new training run — cheap experiments while a proper fine-tune queue is full.

4. **Not a substitute for evaluation-covered training.** If you have the data and budget for a proper multi-task fine-tune, that path is more reliable. Merging shines when training is expensive and checkpoints already exist.

## Recipe guidelines

1. **Start dare_ties for multi-model, SLERP for pairs.** The accumulated community and NVIDIA guidance lands there: DARE-TIES handles interference best across several fine-tunes; SLERP remains the safe two-model default. Move to plain linear only when you have a reason (soups of same-task checkpoints, for example).

2. **Sweep weights like hyperparameters.** Merge coefficients (for example 0.5/0.5 versus 0.7/0.3) materially change output quality. Grid a few weightings, evaluate each merge, and keep the winner — merges are cheap enough that brute force is the honest strategy.

3. **Merge at a stable dtype and re-quantize last.** Do merges in bf16/fp16 on the full-precision checkpoints, then quantize the merged artifact (GGUF/AWQ/GPTQ) for serving. Quantize-before-merge stacks rounding error across every component.

4. **Keep YAML recipes as the artifact of record.** mergekit configs name models, method, and parameters in one reviewable file. Store the recipe next to the merged model (HuggingFace or local registry) so any merge is reproducible and diffable — an unexplained merged checkpoint is unauditable tech debt.

## Evaluation of merges

1. **Always run a capability matrix.** For each component fine-tune's domain (code benchmarks, chat arena-style judging, your domain suite), score the merge and both parents. Merges regularly win on the blended average while quietly regressing one component below its standalone parent — decide explicitly whether that trade is acceptable.

2. **Add generic-capability checks.** Merged models can degrade on general instruction following and reasoning even when domain scores look fine. Include a general benchmark (an LM-Eval-Harness suite or equivalent) as a regression gate for every merge.

3. **Subjective smoke testing is not optional.** Numeric benchmarks miss style incoherence — a model that answers code questions in one persona and chat in another. A short human review pass on mixed conversations catches what perplexity metrics cannot.

4. **Expect trial and error.** The r/LocalLLaMA experience and MergeKit paper agree outcomes are empirical; no theory predicts a specific merge's quality. Budget for several failed merges per success and make each attempt cheap (scripted merge, scripted eval, discard fast).

## Operational integration

1. **Version merges like models.** Tag merged artifacts with the parent checkpoints, recipe YAML, and eval scores. When a parent updates (new base patch release), the merge must be regenerated and re-evaluated — parent lineage belongs in the artifact metadata.

2. **Watch for tokenizer and config mismatches.** All parents must share tokenizer, architecture, and hidden size; mergekit validates this, but community uploads lie occasionally. A merged model producing garbage tokens usually means a mismatched tokenizer, not a bad merge recipe.

3. **Do not ship a merge your team cannot explain.** Production risk review for merged models should state what parents contributed, what evals cover each capability, and what the rollback is (serve the parent fine-tune). The ability to explain the artifact is the difference between an optimization and a liability.
