# lora-qlora-parameter-efficient-finetuning

**Issue:** Teams avoid fine-tuning because "we don't have the GPUs for it" — picturing the 140GB+ a 70B needs for full fine-tuning in bf16. Parameter-efficient fine-tuning (PEFT) changes that math: LoRA trains tiny adapter matrices instead of all weights, and QLoRA runs the frozen base in 4-bit so a 7B-14B tunes on a single consumer card. But PEFT is also full of silent-failure modes — wrong rank, unmerged adapters in prod, adapters attached to the wrong base model — that waste a training run or ship garbage. This article covers mechanics, memory math, hyperparameters, and the operational gotchas. It complements the existing fine-tuning-when-to-use / data-preparation / evaluation articles.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## LoRA mechanics worth knowing

1. **Low-rank adapters instead of full weight updates.** For each targeted weight matrix W (d×k), LoRA freezes W and learns two small matrices A (d×r) and B (r×k); the effective update is BA with rank r ≪ min(d,k). Trainable parameters drop to a fraction of a percent, gradients and optimizer states exist only for the adapters — that is where the memory saving actually comes from.
2. **Rank r is capacity, not magic.** r=8-16 suffices for style/format/task adaptation; r=32-64+ for harder shifts (new domain knowledge, multilingual). Rank alone is a weak lever compared to data quality — a better dataset at r=16 beats a mediocre one at r=64.
3. **Alpha sets the effective scaling** — the update is scaled by alpha/r, and the field-standard heuristic (Raschka) is alpha = 2r (e.g. r=16, alpha=32). Keep that ratio when sweeping rank, and tune learning rate around 1e-4 to 2e-4.
4. **Target modules determine what can change.** Adapters on attention projections only (q,v) is the classic cheap setup; adding MLP projections (gate, up, down) or "all-linear" costs more memory but materially improves hard adaptations. Untargeted layers stay frozen — fine for behavior change, useless for knowledge injection.
5. **Adapters are small files that swap at runtime.** A LoRA adapter is megabytes — you can hold many task/persona adapters per base model and hot-swap them (llama.cpp `--lora`, vLLM multi-LoRA serving, HF `peft`). This is the operational superpower PEFT has over full fine-tuning.

## QLoRA: the single-GPU enabler

1. **Three tricks stacked.** QLoRA = base weights in 4-bit NF4 (NormalFloat, matched to the normal distribution of weights) + double quantization (the quantization constants themselves quantized) + paged optimizers (optimizer state spills to CPU RAM on memory spikes).
2. **The memory math.** NF4 puts a 7B base at ~4GB and a 14B at ~8GB; with bf16 LoRA adapters and activations, a 7B tunes in roughly 6-10GB VRAM — a 12GB RTX 3060 class card. Full fine-tuning the same 7B in bf16 wants ~40GB+ (weights, gradients, Adam states); QLoRA is the difference between "possible" and "not."
3. **Quality of the 4-bit frozen base is not the adapter's bottleneck.** QLoRA training quality approaches 16-bit fine-tuning because gradients flow through adapters computed in bf16 while only the frozen weights are 4-bit. Fine-tuning capability survives; do not conflate this with serving quantization concerns.
4. **Use `paged_adamw_8bit`** (8-bit optimizer with paging) as the default — it halves optimizer memory and absorbs the long-sequence spikes that otherwise OOM mid-run.
5. **Sequence packing and gradient accumulation** to fit batch size on small cards; Unsloth-class optimized kernels give roughly 2x+ speed and lower memory on supported architectures if training time is the constraint.

## Operational gotchas

1. **An adapter is only valid with its exact base model** (and quantization of it, for GGUF adapters). Tag every adapter with base model ID + quant; loading Qwen-adapter-on-Llama fails loudly, but a near-miss base (different revision) fails silently as degraded output.
2. **Decide merge vs serve-attached.** Merging (BA folded into W, export one file) is simpler to deploy and slightly faster; serving adapters unmerged keeps one base + many small adapters, saving disk and enabling hot-swap — pick per deployment shape, and TEST after merging, since fp16 rounding on merge can shift outputs.
3. **Chat template consistency is the top silent killer.** Train with the exact template (and tool-call format) the serving stack uses; a template mismatch between training and inference produces "the fine-tune didn't work" symptoms that no hyperparameter sweep fixes.
4. **Overfitting shows up fast at these scales.** With 1-3 epochs typical, watch eval loss on held-out data; PEFT memorizes a small dataset quickly. The existing fine-tuning-data-preparation article's quality-over-quantity rule applies double here.
5. **Evaluate adapter against the base, not against hope.** Run the same golden set on base-with-prompt vs adapter; if a good prompt on the base matches the adapter, prefer the prompt (cheaper to maintain) — this is the fine-tune-vs-prompt/RAG decision, made with evidence.
6. **Version adapters like code.** Adapter + training data snapshot + hyperparameters + eval scores as one unit; "which adapter is in prod" must be answerable in seconds when quality drifts.

## Anti-patterns

1. **Assuming a GPU-cluster is required to start** — QLoRA puts 7B-14B adaptation on a single 12GB card; the barrier is data quality, not hardware.
2. **Sweeping rank to fix a data problem** — more capacity memorizes noise faster; fix the dataset first, then r=16/alpha=32.
3. **Training and serving with different chat templates** — the classic silent failure blamed on LoRA itself.
4. **Deploying adapters detached from their base-model identity** — near-miss base loads degrade quality with no error message.
5. **Skipping the base-model-with-good-prompt baseline** — sometimes the fine-tune only beats a mediocre prompt, which is not a reason to fine-tune.
