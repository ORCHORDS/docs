# ai-energy-consumption-2026

**Issue:** A team deploys an LLM-powered chatbot. The team is proud of its accuracy. The CFO asks "what's the energy cost?" The team has no answer. The procurement team asks for the carbon footprint. The team has no answer. The board asks for the water cost. The team has no answer.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

AI energy and water consumption became a board-level question in 2024-2026. EU AI Act Article 51, EU Energy Efficiency Directive recast, and US executive orders on federal sustainability all require AI energy disclosure. Teams without measurement can't answer.

## Root cause

Three numbers matter for AI sustainability.

1. **Energy** — kWh per inference or per training run
2. **Carbon** — kg CO2e per inference or per training run (energy × grid carbon intensity)
3. **Water** — liters per inference or per training run (for data center cooling)

All three need measurement. The 2026 production stack is a measurement layer + reporting layer.

## The 5 published 2024-2026 numbers

The reference numbers for LLM inference.

| Source | What | Number |
|---|---|---|
| Google (2024) | Gemini Pro text prompt (median) | 0.24 Wh / query; 0.03 g CO2e |
| Google (2024) | Gemini Pro text response (median) | 0.70 kWh / response; 0.90 g CO2e |
| OpenAI (2023) | GPT-3 175B inference | ~0.0003 kWh / response |
| OpenAI (2023) | ChatGPT daily energy | ~564 MWh/day (April 2023 estimate) |
| Microsoft (2024) | US data centers water for AI | 2.2 billion gallons / year (1.3% of US data center total) |
| IEA (2024) | Global data center electricity demand 2026 | ~460 TWh (~2% of global demand) |
| IEA (2024) | Data center demand growth 2024-2030 | ~15% CAGR |

The Google numbers are the most rigorous 2026 public benchmark: a Gemini text prompt is roughly equivalent to 9 seconds of a 9W LED bulb.

## The 4 measurement patterns

| Pattern | Tool | Use case |
|---|---|---|
| Cloud provider dashboard | AWS / GCP / Azure carbon footprint | per-region, per-service |
| Specialized tool | CodeCarbon, Eco2AI, Green Software Foundation SCI | per-inference, per-experiment |
| Self-instrumentation | wattmeter at GPU; custom telemetry | per-job, per-workload |
| Vendor disclosure | Microsoft, Google, OpenAI sustainability reports | aggregate, not per-customer |

The 2026 production stack: cloud provider dashboard for the floor + CodeCarbon / Eco2AI for the per-inference layer.

## The 6-step code instrumentation pattern

```python
# Using CodeCarbon
from codecarbon import OfflineEmissionsTracker

tracker = OfflineEmissionsTracker(
    country_iso_code="USA",
    cloud_provider="aws",
    cloud_region="us-east-1"
)
tracker.start()

# Your LLM inference
response = openai.chat.completions.create(...)

emissions = tracker.stop()
# emissions: float kg CO2e for this inference
```

The CodeCarbon output gives kg CO2e, energy, duration, region. Combined with token counts, you can report per-1K-tokens and per-inference.

## The 5 best practices

1. **Measure per-inference, not per-month.** The aggregate hides spikes; the per-inference number is what the CFO asks.
2. **Track grid carbon intensity by region.** A query in Norway (98% hydro) is 50x cleaner than in West Virginia (70% coal).
3. **Include water in the report.** EU AI Act Article 53 requires water reporting for large models.
4. **Use renewable regions for batch jobs.** Schedule training in low-carbon regions during low-demand hours.
5. **Report per-feature, not just per-product.** The "summarization feature" consumes X; the "translation feature" consumes Y; the team can decide.

## The EU AI Act Article 51

The EU AI Act requires energy and resource reporting for general-purpose AI (GPAI) models.

- **Scope:** GPAI providers (Article 51) and GPAI with systemic risk (Article 55)
- **Required disclosure:** training compute, training energy, estimated inference energy, data center location
- **Format:** technical documentation + public summary
- **Effective:** August 2, 2025 (GPAI), August 2, 2027 (systemic risk)

A 10^25 FLOP model must report training compute and energy. Inference reporting is recommended but not always mandatory.

## The 4 anti-patterns

1. **"AI energy is too small to matter."** Per-inference is small; aggregate is large. Google's data center consumption grew 50%+ in 2024-2025 due to AI.
2. **Reporting only kWh.** The CFO cares about cost and carbon; the board cares about carbon and water. Report all three.
3. **Using one number for the whole company.** Grid carbon intensity varies 10x by region. Report by region.
4. **No baseline measurement.** Without a 2024 baseline, "we reduced by 30%" is unfalsifiable. Measure first.

## The 5-step optimization pattern

After measuring, optimize.

1. **Choose smaller models** for simple tasks (classification, extraction)
2. **Use the right model per region** — match the latency requirement to the model size
3. **Cache LLM responses** for repeated queries (semantic caching)
4. **Batch inference** where latency allows
5. **Move to low-carbon regions** for non-latency-critical workloads

Each lever typically gives 30-50% energy reduction. Stacking levers: 2-5x.

## The 2026 regulatory landscape

| Jurisdiction | Energy / carbon reporting required? |
|---|---|
| EU AI Act Article 51 | yes, for GPAI; August 2025 effective |
| EU Energy Efficiency Directive (recast 2023) | data center reporting (PUE, energy reuse factor) |
| US executive order 14110 (Biden) | federal AI sustainability reporting |
| US SEC climate disclosure rule | scope 1/2/3 emissions, including AI |
| UK SECR (Streamlined Energy and Carbon Reporting) | mandatory for large UK companies |
| California SB 253 | scope 1/2/3 for companies >$1B revenue |
| Japan GX-ETS | emissions trading, includes data centers |

The 2026 default for any AI deployment serving EU users or US listed companies: full scope 1/2/3 reporting including AI workloads.

## The Green Software Foundation SCI

The Software Carbon Intensity (SCI) is the ISO 21031-equivalent for software.

SCI = (E × I) / R

Where:
- E = energy consumed by the software
- I = carbon intensity of the electricity
- R = a functional unit (e.g., one user, one request, one transaction)

SCI is a ratio, not a total. "10 g CO2e per 1k requests" is more useful than "10 tonnes CO2e per month." The ratio lets you compare across products and over time.

## The carbon-aware computing pattern

The 2026 production pattern: shift compute to low-carbon regions / low-carbon hours.

- **Carbon-aware load shifting** (WattTime, Electricity Maps API) — schedule non-urgent jobs in low-carbon hours
- **Carbon-aware routing** — direct inference to the lowest-carbon region with acceptable latency
- **Renewable energy matching** — provider-level (Google matches 100% renewable; AWS offers renewable regions)

The 2026 carbon-aware scheduler can cut the carbon intensity of a batch job by 30-70% with no performance cost.

## Verification

The tell that AI energy measurement is real:

- Per-inference energy, carbon, and water are reported
- Region-specific reporting (different grid intensity per region)
- A baseline from 2024 or earlier is documented
- Optimization levers (model size, caching, batching, region) are tracked over time
- The EU AI Act Article 51 disclosure is on file for GPAI

The tell it isn't:

- "AI energy is small" without measurement
- Aggregate monthly report only
- No water reporting
- No baseline
- No optimization tracked

## Gotchas

- **The Google numbers are optimistic.** A median Gemini text prompt at 0.24 Wh is much less than typical LLM API queries. Real workloads are higher.
- **The OpenAI 2023 numbers are pre-2024 model wave.** GPT-4 / GPT-4o consume more; new numbers needed.
- **Scope 3 emissions** (data center electricity, hardware manufacturing) are where most AI carbon hides. Track them.
- **Water is regional.** A model served from a Phoenix data center in summer uses 2x the water of a model served from a Nordic data center.
- **The IEA 460 TWh figure is for 2026.** Projected to 945 TWh by 2030 in the IEA base case. Plan for growth.

## Related

- `issues/eu-ai-act-article-5-prohibited-2026.md` — EU compliance
- `lessons/ai-cost-finops-2026.md` — cost optimization
- `lessons/structured-output-2026.md` — small model efficiency
- `compliance/` — sustainability reporting

## Source URLs (verified 2026-08-10)

- https://blog.google/technology/ai/google-gemini-environment-impact/ — Google Gemini energy (2024)
- https://openai.com/index/the-cost-of-chatgpt/ — OpenAI early numbers
- https://www.iea.org/reports/electricity-2024 — IEA Electricity 2024
- https://www.iea.org/reports/data-centres-and-data-transmission-networks — IEA data centers
- https://www.whitehouse.gov/wp-content/uploads/2023/11/AI-Executive-Order-14110.pdf — EO 14110
- https://codecarbon.io/ — CodeCarbon tool
- https://greensoftware.foundation/ — Green Software Foundation SCI
- https://www.watttime.org/ — WattTime carbon-aware API
- https://www.electricitymaps.com/ — Electricity Maps
- https://eur-lex.europa.eu/legal-content/ENG/TXT/?uri=CELEX:32023R1791 — EU Energy Efficiency Directive recast
