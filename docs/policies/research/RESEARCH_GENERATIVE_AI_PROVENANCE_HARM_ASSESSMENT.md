---
title: "Generative AI Provenance Harm Assessment"
owner: "Research Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Generative AI Provenance Harm Assessment

Source: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf

NIST AI 600-1 recommends identifying potential content-provenance harms such as misinformation, disinformation, deepfakes, non-consensual intimate imagery, and tampered content, then ranking risks by likelihood and impact and evaluating whether provenance measures address them.

## Governance

- Define the provenance threat being evaluated before selecting a technical control.
- Distinguish origin metadata, authenticity evidence, watermarking, detection, and user disclosure; they solve different problems.
- Evaluate false positives, false negatives, stripping/tampering, and unsupported media paths.
- Avoid representing provenance tooling as proof that content is true.
- Escalate high-impact misuse findings to the applicable safety/security process.

## Evidence

Document the threat model, tested content types, limitations, observed bypasses, and residual risk. Public reporting must not expose victim content or operationally sensitive abuse detail.