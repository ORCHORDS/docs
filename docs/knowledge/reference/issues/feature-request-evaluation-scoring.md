# feature-request-evaluation-scoring

**Issue:** Feature requests accumulate faster than any team can build them, and without a defensible evaluation method the queue resolves by volume of asks, seniority of the asker, or the PM's morning mood. That failure mode has two costs: strategic work loses to squeaky wheels, and stakeholders lose trust in the roadmap because they cannot see why "their" request ranked where it did. A scoring framework turns the request backlog from an argument into a computation: every candidate gets a comparable number, the number is derived from stated assumptions rather than advocacy, and disagreements surface as disputes about inputs (is reach really 500 users?) instead of disputes about outcomes. This article covers choosing a framework, scoring honestly, and using scores as decision support rather than decision replacement.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing a scoring framework

1. **RICE as the default for data-rich queues.** Score = (Reach x Impact x Confidence) divided by Effort. Reach is people affected per quarter, Impact a fixed scale (3 = massive, 0.25 = minimal), Confidence a percentage discounting shaky estimates, Effort in person-months. Intercom, who created RICE, built it precisely to force prioritization debates onto measurable inputs; it remains the most widely recommended framework in 2025 roundups because it balances rigor against speed — roughly two minutes per item when inputs are prepared.
2. **ICE when speed beats precision.** Impact, Confidence, Ease, each 1-10, no reach estimate. Right for small teams, short horizons, or early products where reach numbers are guesses dressed as data. The cost is comparability; the benefit is that scoring actually happens.
3. **MoSCoW when the decision is binary and time-boxed.** Must/Should/Could/Won't fits release-planning against a fixed date better than ranking an open queue, and it is honest about the Won'ts — which per the wontfix-policy discipline is where communication matters most.
4. **Match the framework to the decision, not the fashion.** Comparisons of frameworks (RICE versus ICE versus weighted scoring) converge on the same advice: the framework earns its keep by making assumptions explicit; switching frameworks every quarter discards the calibration and restarts the arguments.

## Scoring without lying to yourself

1. **Base Reach on evidence, with a written source.** Requests backed by telemetry (X percent of sessions hit this gap) or clustered customer reports (per the customer-reported-bug-intake duplicate counts) score differently from one forwarded email. Record the source next to the number — an unsourced reach is an opinion.
2. **Cap Confidence and mean it.** Confidence exists to discount enthusiasm: a bold estimate with no data gets 50 percent, not 80. The classic RICE failure is everything scoring 100 percent confidence, which collapses the framework into Impact x Reach with extra steps.
3. **Score Effort in person-time, not story points.** Practitioner guidance is consistent: points estimate complexity relative to a team's sprint, but a priority score needs denominator units that survive cross-team comparison — person-days or person-months. Include the hidden costs: migrations, experiments, docs, and the ongoing maintenance tail of the feature, not just first ship.
4. **Time-box the scoring itself.** Two to five minutes per item, batched. Scoring is a filter that decides which items deserve deep diligence, not the deep diligence itself; the top handful after scoring get the real investigation.
5. **Score alternatives against each other, including the do-nothing option.** A request that scores 8 means nothing in isolation; it means something against the other candidates for the same slot on the roadmap.

## From scores to decisions

1. **Treat the ranking as the start of the conversation.** Current product-management practice is explicit that RICE output is decision support: strategic bets, technical dependencies, and contractual obligations legitimately override the number. What the score buys is that an override is visible and justified ("this scores lower but unlocks the enterprise tier") rather than silent.
2. **Re-score periodically, not continuously.** Inputs decay: reach grows with the user base, effort drops when a dependency ships, confidence rises after customer conversations. A quarterly re-scoring pass on the top of the queue keeps the ranking honest without turning prioritization into a weekly re-litigation.
3. **Publish the method, not just the ranking.** Stakeholders who can see the inputs and the formula stop relitigating the output and start correcting the inputs — which is the productive argument. This is the same transparency logic as the labeling taxonomy: shared vocabulary, fewer private standards.
4. **Close the loop with requesters.** Every scored request gets a disposition — planned (with which quarter), parked (with what would raise the score), or declined (with the honest reason). Requests that disappear into silence generate repeat requests and escalation, the request-side equivalent of zombie issues.

## Failure modes to watch

1. **Estimation theater.** Reach precision to three significant figures from a sample of four. Round aggressively, band the estimates, and let Confidence carry the uncertainty instead of fake precision in Reach.
2. **The framework as shield.** "It scored 4.2" used to end discussion of something obviously important. If leadership routinely overrides the ranking, either the inputs are wrong or the framework is measuring the wrong things — fix the model, do not hide behind it.
3. **Scoring only features, never maintenance.** A queue that only ranks new capability systematically starves reliability and debt work, because those items have diffuse reach and no advocate. Either score debt-reduction work in the same framework (reach = everyone touching the code) or reserve explicit capacity outside it.
4. **Never deleting requests.** A request backlog of 2,000 items is not a strategy, it is a guilt pile. Staleness rules apply here too: requests un-re-scored and un-referenced for a year graduate to closed-with-explanation, which keeps the scored queue short enough to re-score honestly.
