# ai-energy-consumption-deep-2026

**Issue:** A team runs GPT-4-class inference at 1M requests/day. The team sees a 6-figure cloud bill. The team reads about LLM energy, water, carbon. The team needs the 2026 reference for AI energy and environmental cost.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 energy components

1. **Training energy.** One-time cost per model. GPT-4 estimated 50+ GWh; Claude 3.5 Sonnet estimated 30+ GWh.
2. **Inference energy.** Per-request. 1M tokens ≈ 0.5-2 kWh depending on model.
3. **Data center overhead.** Cooling, networking, storage. PUE 1.1-1.6 typical.
4. **Water consumption.** ~1-2 L per kWh for cooling. LLM inference ≈ 0.5-2 mL per query.
5. **Embodied carbon.** Hardware manufacturing, data center construction.

## The 5 reduction strategies

1. **Model selection.** Use the smallest model that meets quality bar. Haiku-class for 80% of queries.
2. **Caching.** Prompt caching (Anthropic 90% off cached input). Semantic cache for repeated queries.
3. **Batching.** Group requests to share GPU utilization.
4. **Quantization.** INT8/INT4 weights. 4x memory, ~1.5x speedup, <1% quality loss.
5. **Speculative decoding.** Draft model proposes, target model verifies. 2-3x speedup on long outputs.

## The 5 measurement tools

1. **Code Carbon** (`codecarbon`) - Python library, estimates kWh and CO2eq.
2. **EcoLogits** - tracks LLM energy at the API level.
3. **LLM Carbon** - model-level energy estimates.
4. **ML CO2 Impact Calculator** - one-off training runs.
5. **Cloud provider dashboards** (AWS Customer Carbon Footprint Tool, GCP Carbon Sense).

## The 5-step adoption pattern

1. **Measure baseline.** Run `codecarbon` or `ecologits` on a representative workload.
2. **Profile** which queries consume the most. Big prompts, long outputs.
3. **Apply cheap wins first.** Caching, batching, model selection.
4. **Quantize** self-hosted models.
5. **Pick green regions** for inference (Iceland, Quebec, Pacific Northwest).

## The 5 anti-patterns

1. **"AI is too expensive" without measurement.** Often 80% reduction possible.
2. **Running max-quality model for every query.** Use tiered routing.
3. **No prompt caching.** Recurring system prompts re-billed every request.
4. **Self-hosting in non-green regions** with high PUE.
5. **Ignoring training cost** in "fine-tune for safety" decisions.

## The 5 best practices

1. **Set energy budgets per workload**, alert on exceed.
2. **Prefer green-region inference** (cloud provider carbon dashboards help).
3. **Use smallest viable model** for the task.
4. **Cache aggressively** for repeated queries.
5. **Track energy as a release metric**, not just accuracy.

## Gotchas

- PUE varies 1.1 (best hyperscaler regions) to 2.0 (older on-prem).
- Water consumption is regional (1 L/kWh in hydro regions, 2+ L/kWh in coal regions).
- Embodied carbon amortizes over 5-10 years of server use.
- Some cloud regions publish hourly carbon intensity; spot-instance green scheduling possible.
- Inference energy varies 10x across model sizes (Haiku vs Opus).

## Source URLs (verified 2026-08-10)

- https://codecarbon.io/
- https://ecologits.ai/
- https://mlco2.github.io/impact/
- https://www.greenwebfoundation.org/
- https://www.iea.org/reports/electricity-2024
