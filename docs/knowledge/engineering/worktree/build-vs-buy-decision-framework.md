# build-vs-buy-decision-framework

**Issue:** Every quarter the same fight: a team asks to build an in-house notifications/search/billing system because "the SaaS is expensive and it's just a CRUD app," while finance asks why engineering keeps rebuilding commodity software. Decisions get made by whoever argues longest, there is no shared criteria, and nobody revisits the outcome. A poor build-vs-buy decision can inflate total cost 2–5x over 3–5 years, and the 2025 data makes it worse: SaaS spend per employee hit ~£6,110 (about 12.5% of organizational spend), so both directions of the mistake are expensive now.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The decision criteria

1. **Differentiation is the first question, not cost.** If the capability is core to how the product wins (the recommendation engine for a commerce platform), building keeps strategic control. If it is commodity plumbing (auth, email, payments, observability), buying frees the team for the differentiating work — opportunity cost is the real price of building.
2. **Score on five axes before comparing prices: strategic differentiation, time-to-market pressure, in-house expertise, integration surface, and compliance/data-residency constraints.** A written scorecard ends the loudest-voice-wins pattern; any component scoring "high differentiation" on the first axis skips straight to the build track regardless of cost.
3. **Time-to-market is a quantified input, not a feeling.** If shipping the capability this quarter is worth a specific revenue number (sales contract, regulatory deadline), that number goes in the analysis — a $2M deadline makes a $200K/year SaaS look cheap and a 6-month build look fatal.
4. **Expertise is a hard gate.** Building a search system without anyone who has operated a search system at scale means the first year is tuition, not delivery; buying is how you rent the expertise you lack. Budget for the learning curve explicitly if you proceed anyway.
5. **Default positions by category.** Auth, payments, observability, email/SMS: buy. Domain-specific data models and algorithms: build. Everything else: score it. Defaults exist so the debate is reserved for genuinely ambiguous cases.

## Total cost of ownership math

1. **Model 3–5 year TCO, never the sticker price.** First-year comparisons systematically favor building (no license fee yet) and hide the maintenance tail; five-year TCO is the standard lens across the 2025 frameworks because that is where build costs compound.
2. **Price the build honestly: the real benchmark is expensive.** Industry benchmarks put first-year build cost for a non-trivial system at roughly $750K–$1.5M (2–3 engineers plus infrastructure), against $100K–$250K/year to buy an equivalent — and internal estimates below these numbers usually forgot someone's salary.
3. **Add the hidden 150–200%.** Integration work, data migration, training, and vendor-management overhead commonly add 150–200% to initial estimates in both directions: bought tools need integration engineering too, and built systems need operational staffing, on-call, and security work forever.
4. **Count the maintenance perpetual annuity.** A built system is never "done" — bug fixes, dependency upgrades, scaling, and feature requests continue for its whole life. Rule of thumb: assume the building team's annual cost recurs indefinitely, because it does.
5. **Count switching costs on the buy side.** Data export capability, contract terms, and per-seat pricing growth are part of buy TCO; a cheap tool with no export path and 20%/year price escalation is not cheap.

## The 2025–2026 AI twist

1. **AI coding assistants lower build cost but do not eliminate maintenance.** Generative tooling compresses the initial build substantially — which makes TCO curves flatter at the start while the operations tail stays the same size. Re-run old build-vs-buy decisions with the new build economics; some former "buy" answers flip.
2. **AI adds variable inference costs that behave like SaaS fees.** A built AI feature carries per-token or per-compute cost forever, plus ongoing evaluation and quality work as models change — the "buy" cost structure now appears inside builds, so model it as a line item, not zero.
3. **Beware the demo-to-production gap.** An AI prototype built in a week is not evidence that a production AI system is a week of work; guardrails, evaluation harnesses, and failure handling are most of the cost. Treat AI demos as feasibility signals, not TCO estimates.
4. **Prefer hybrid: buy the platform, build the differentiating layer.** The emerging 2026 pattern is to buy the commodity substrate (vector store, model gateway, workflow engine) and build only the thin domain layer on top — capturing most of both advantages.
5. **Re-evaluate AI vendor lock-in harder than traditional SaaS.** Model APIs, prompt formats, and agent frameworks are churning fast; a vendor abstraction layer (or an exit clause in the decision record) is mandatory for anything touching the product's core AI behavior.

## Decision record and review

1. **Record every build-vs-buy decision as an ADR.** Context, scorecard, TCO model, decision, and the explicit revisit trigger — the decision log template applies directly, and the record is what turns a judgment call into an auditable choice.
2. **Write the sunset clause at signing or kickoff.** For buys: contract length, export path, renewal decision date. For builds: the operational owner and the cost threshold at which the build gets reconsidered. Decisions without named expiry dates become permanent by inertia.
3. **Review the portfolio annually, not the project once.** SaaS spend audits (the Zylo/Celigo 2025 consolidation pattern) and internal-system cost reviews catch the two slow leaks: unused licenses and orphaned internal tools nobody remembers approving.
4. **Score the decision one year later.** Did the build ship on estimate? Did the SaaS hit its projected adoption? A one-page retrospective per decision calibrates the next one — organizations that never look back keep making the same mistake in both directions.
5. **Escalate above the team when cost asymmetry is large.** Any decision whose 5-year TCO exceeds a set threshold (for example, $1M) goes to the platform lead or architecture review with the scorecard attached — not because teams cannot decide, but because budget-scale decisions are portfolio decisions.

## Exit criteria when buying

1. **Data export is a precondition, evaluated before purchase.** If the vendor holds your data with no complete export path, you have not bought a tool — you have made a donation; walk away or contractually guarantee export.
2. **Negotiate the renewal ramp.** Per-seat pricing that scales with success means growth is punished; cap increases or pre-agree bands at signing, when you have the most leverage.
3. **Keep an integration seam.** Wrap vendor APIs behind an internal interface so a future swap is a re-implementation behind one boundary, not a product-wide rewrite.
4. **Define the trigger conditions for leaving.** Price above X%, uptime below Y%, feature stagnation for Z quarters — written triggers make the future exit decision mechanical instead of another loudest-voice fight.

## Source URLs (verified 2026-08-15)

- https://saigontechnology.com/blog/build-vs-buy-software/
- https://zylo.com/blog/build-vs-buy-software-pros-and-cons
- https://neontri.com/blog/build-vs-buy-software/
- https://aakashgupta.medium.com/the-product-leaders-guide-to-buying-vs-building-software-a67a87bfca04
- https://hatchworks.com/blog/gen-ai/build-vs-buy-framework/
- https://helium42.com/blog/build-vs-buy-ai
- https://www.celigo.com/blog/buy-vs-build/
