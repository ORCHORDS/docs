# Grounding Source Ranked Probabilities Under MITRE ATLAS Evidence Weighting

## Scope

Grounding claims the model output is supported by evidence from external sources. In practice, agents produce output as a weighted combination of retrieved passages, tool results, memory entries, and the model's own priors. The combination is rarely presented with its weights, and operators usually see a confident answer whose provenance is opaque. MITRE ATLAS catalogs adversarial tactics against machine learning systems, and the ATLAS view of evidence is useful for thinking about how to rank grounding sources by reliability, recency, and provenance rather than by surface similarity.

This article covers grounding governance grounded in ATLAS-style evidence weighting. The aim is to make the weighting explicit, auditable, and adjustable, rather than to claim that weighted grounding eliminates hallucination. Grounding is a probabilistic discipline; treating it as a deterministic check produces false confidence.

## Workflow or implementation guidance

1. Assign every grounding source a trust profile at registration, not at retrieval. The profile should encode origin authority, recency policy, sensitivity classification, and known weakness under ATLAS tactics such as data poisoning or indirect prompt injection. Sources without a profile are excluded from grounding, not accepted under a default.
2. Score retrieved passages on top of the trust profile. Combine document-level trust with retrieval relevance, but do not let high relevance overcome low trust. A retrieved fragment from an untrusted source ranked highly by similarity should not contribute as if it were equivalent to a trusted source.
3. Weight grounding by recency. An older source may still be correct, but its relative weight should reflect the policy the source profile declares. Where sources disagree, the weighting must surface the disagreement explicitly rather than collapse to a single answer with hidden composition.
4. Compose the answer with the weights visible to downstream reasoning. The agent's reasoning chain should be able to refer to which sources contributed to which claim, at what weight, and with what recency. Visibility is what makes the weighting auditable.
5. Treat tool outputs as sources with their own profile. A tool returning an answer is no different from a retrieved document for grounding purposes: it has provenance, it has trust, and its weight in the composition should reflect that profile. ATLAS adversarial tactics on tools are as relevant as tactics on data.
6. Maintain a ranked shortlist of source weights per output, not a single score. The shortlist is what makes post-hoc review possible and what enables the operator to challenge the composition when an answer is contested.
7. Run ATLAS-style adversarial testing against the grounding pipeline. Attempt poisoning, retrieval manipulation, and indirect injection through documents and tools. The result of testing should be a measured resistance profile and a clear record of where the pipeline fails.
8. Reject composition that relies on a single low-trust source for a high-impact claim. Composition should require multiple sources from independent trust profiles when the claim is consequential. Independence is a property the operator should specify rather than assume.

## Controls

Trust profiles must be reviewable on change. A document entering the trust store should have an approval record, and changes to the profile should be tracked with a reason. Trust profile drift is a quiet failure: documents that were once trustworthy are reclassified without review, and the composition inherits the change without inspection.

Source weighting should be parameterized, not coded into prompts. When the parameter changes, the change should be logged, the change should be reviewable, and the change should be effective in a defined scope. Hard-coded weights obscure the parameterization and prevent the operator from adapting to new threat intelligence.

Capture the composition output as evidence. Each grounding event should produce a record listing the sources consulted, the weights applied, the recency used, and the final composition. The record is what allows review of contested outputs and what supports the kind of after-action analysis ATLAS recommendations imply.

## Validation evidence

Demonstrate a known-correct query against a configured source set and confirm the composition uses the expected sources at the expected weights. Demonstrate a query with disagreement between sources: confirm the disagreement is reflected in the shortlist and is not silently resolved by selection. Demonstrate that a high-trust source outranks a low-trust source when both are relevant, and confirm this is true under deliberate perturbation of the relevance signal.

Show adversarial evidence. An ATLAS-style poisoning attempt at the document level does not pass the trust profile check. An injection attempt embedded in a tool output is reflected as low weight for that output's claim. An attempt to manipulate relevance scoring does not elevate a low-trust source past the trust-profile floor.

Show operational evidence. Composition records are retained, retrievable, and reviewable for contested outputs. Profile changes are tracked and linked to events. The trust floor for consequential claims is enforced by code, not by convention.

## Failure modes and correction

A common failure is single-source grounding that appears multi-source because multiple documents came from the same underlying corpus. Correct by specifying independence requirements for consequential claims and enforcing them at composition time, not by checking similarity after the fact.

A subtler failure is trust profile inflation, where everything is rated medium-high because the operator finds it easier than making distinctions. Correct by enforcing a calibration sample: a periodic review of profile assignments against ground truth, with adjustments recorded and used to recalibrate the assignment process.

Another failure is treating the model's own output as a grounding source for subsequent reasoning. Recursive grounding turns priors into evidence and is hard to reason about under ATLAS-style threat models. Correct by separating the model's prior from external sources and refusing to treat the prior as grounding.

## Limitations

ATLAS provides adversarial taxonomy, not prescriptive evidence-weighting algorithms; this article borrows the framework without claiming to be its normative implementation. Probabilistic grounding remains uncertain, and weighted composition does not eliminate hallucination. Trust profiles require ongoing maintenance, and adversaries adapt to whatever profile definitions are published. Composition records are evidence, not guarantees, and their value depends on operator attention.

## Canonical sources

- **MITRE ATLAS, Adversarial Threat Landscape for AI Systems:** https://atlas.mitre.org/
- **MITRE ATLAS, Tactics and Techniques index:** https://atlas.mitre.org/tactics
- **OWASP, Top 10 for Large Language Model Applications (LLM05 and LLM06 grounding-relevant categories):** https://owasp.org/www-project-top-10-for-large-language-model-applications/
