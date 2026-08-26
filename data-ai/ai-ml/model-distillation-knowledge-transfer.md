# Model Distillation — Knowledge Transfer and Compression for Production

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your production LLM costs $0.15 per request and takes 2 seconds to
respond. You need sub-200ms latency for real-time features. Your edge
devices cannot run a 70B parameter model. Fine-tuning a smaller model
from scratch on your dataset produces worse results than prompting the
large model. You need the large model's accuracy at the small model's
cost and speed.

## Context

Knowledge distillation is a model compression technique where a compact
"student" model learns to replicate the behavior of a larger "teacher"
model. Instead of training on hard labels (correct/incorrect), the
student learns from the teacher's soft probability distributions, which
contain richer information about inter-class relationships and
uncertainty. In 2026, distillation has evolved from an academic
technique to a critical production strategy: organizations achieve
5-30x cost reduction, 4x faster inference, and maintain 95-97% of
original performance. DeepSeek-R1's distillation demonstrated that
smaller distilled models can outperform directly-trained models of the
same size. The EU AI Act's full applicability in 2026 requires
documenting training data provenance, driving adoption of data-free
and synthetic-data distillation approaches.

## Distillation approaches

```
Logit-based (response distillation):
  → Student learns from teacher's output probabilities
  → Soft targets preserve inter-class relationships
  → Temperature parameter controls softness (T=1-20)
  → Simplest approach, works well for classification

Feature-based (representation distillation):
  → Student aligns intermediate layer activations
  → Transfers learned representations, not just outputs
  → Requires architecture-aware mapping between layers
  → Better for complex tasks (NLP, vision)

Relation-based:
  → Student copies structural relationships between outputs
  → Preserves geometric structure of embedding space
  → Used for metric learning and retrieval tasks

LLM-specific distillation:
  → Chain-of-thought distillation (reasoning traces)
  → Instruction-following distillation
  → Synthetic data generation from teacher
  → API-based distillation (teacher as black box)
```

## Implementation

```python
import torch
import torch.nn.functional as F

def distillation_loss(
    student_logits,
    teacher_logits,
    labels,
    temperature=4.0,
    alpha=0.7,
):
    """
    Combined distillation loss.
    alpha: weight for soft target loss vs hard target loss
    temperature: softens probability distribution
    """
    soft_loss = F.kl_div(
        F.log_softmax(student_logits / temperature, dim=-1),
        F.softmax(teacher_logits / temperature, dim=-1),
        reduction='batchmean',
    ) * (temperature ** 2)

    hard_loss = F.cross_entropy(student_logits, labels)

    return alpha * soft_loss + (1 - alpha) * hard_loss


# LLM distillation via synthetic data
from openai import OpenAI

def generate_training_data(teacher_client, prompts, num_samples=10000):
    """Generate synthetic training data from teacher model."""
    training_pairs = []
    for prompt in prompts:
        response = teacher_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        training_pairs.append({
            "input": prompt,
            "output": response.choices[0].message.content,
        })
    return training_pairs

# Fine-tune student on teacher's outputs
# student = fine_tune(base_model="llama-3-8b", data=training_pairs)
```

## Compression pipeline

```
Recommended order (P-KD-Q):
  1. Pruning     → remove redundant weights/neurons
  2. Distillation → transfer knowledge to smaller architecture
  3. Quantization → reduce precision (FP32 → INT8/INT4)

Each step compounds compression:
  Pruning:       70B → 40B parameters (structured pruning)
  Distillation:  40B teacher → 8B student
  Quantization:  8B FP16 → 8B INT4 (4x memory reduction)

  Result: 70B FP32 model → 8B INT4 model
  Size:   ~140 GB → ~4 GB
  Speed:  ~2s → ~200ms
  Quality: ~95-97% of original
```

## Evaluation framework

```
Distillation quality metrics:
  → Task accuracy retention (target: >95% of teacher)
  → Latency reduction (target: 3-10x faster)
  → Cost reduction (target: 5-30x cheaper)
  → Agreement rate (student vs teacher on same inputs)
  → Edge case performance (test on hard examples)

Evaluation protocol:
  1. Benchmark teacher on held-out test set
  2. Benchmark student on same test set
  3. Compare on distribution-shift examples
  4. A/B test in production (shadow mode first)
  5. Monitor quality degradation over time
```

## Anti-patterns

- **Distilling without evaluation rigor** — assuming the student
  matches the teacher because training loss converged. Always
  evaluate on a held-out test set and edge cases. Training loss
  convergence does not guarantee task performance parity.
- **Using too low a temperature** — temperature 1.0 produces hard
  probabilities that carry little information beyond the top
  prediction. Higher temperatures (4-20) soften the distribution,
  revealing the teacher's uncertainty and inter-class relationships.
- **Ignoring teacher errors** — the student faithfully learns
  the teacher's mistakes. If the teacher has systematic biases,
  the student inherits them. Evaluate and filter teacher outputs
  before distillation.
- **One-shot distillation for complex tasks** — distilling a
  multi-capability model in a single pass. For complex tasks,
  use progressive or multi-stage distillation: distill each
  capability separately, then combine.

## Gotchas

- **API terms of service** — many LLM providers (OpenAI, Anthropic)
  restrict using model outputs to train competing models. Review
  the provider's terms before using API outputs as distillation
  training data. Some providers offer explicit distillation APIs.
- **Capacity gap** — if the student is too small relative to the
  teacher, it cannot absorb the teacher's knowledge. A 1B student
  cannot faithfully reproduce a 70B teacher. Use intermediate
  "teacher assistant" models to bridge large capacity gaps.
- **Data distribution shift** — a student distilled on one data
  distribution may fail on shifted distributions. Include diverse
  examples in the distillation dataset and evaluate on
  out-of-distribution benchmarks.
- **Reasoning distillation loss** — chain-of-thought reasoning
  is harder to distill than classification. The student may learn
  to mimic reasoning format without acquiring actual reasoning
  capability. Evaluate on novel reasoning tasks, not just format.

## Verification

- Student achieves >95% of teacher accuracy on held-out test set.
- Inference latency meets production SLA requirements.
- Cost per request is within budget targets.
- Edge case and adversarial performance is evaluated.
- API terms of service compliance is verified.
- Production A/B test shows acceptable quality.

## Related

- `documentation/categories/ai-ml/llm-prompt-engineering-patterns.md`
- `documentation/categories/ai-ml/ai-evaluation-benchmarking.md`
- `documentation/categories/performance/edge-computing-serverless-cdn-patterns.md`

## Source URLs (verified 2026-08-16)

- Model Distillation: Teacher-Student Training Guide 2026 — https://labelyourdata.com/articles/machine-learning/model-distillation
- Model Distillation for LLMs: Cut Costs & Boost Speed — https://redis.io/blog/model-distillation-llm-guide/
- Model Distillation and Knowledge Transfer in AI 2026 — https://zylos.ai/research/2026-02-08-model-distillation/
- What Is Knowledge Distillation? The 2026 Guide — https://www.articsledge.com/post/knowledge-distillation
