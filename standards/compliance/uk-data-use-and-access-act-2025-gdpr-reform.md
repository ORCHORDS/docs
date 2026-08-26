# uk-data-use-and-access-act-2025-gdpr-reform

**Issue:** The Data (Use and Access) Act 2025 (DUAA), which received Royal Assent on 19 June 2025, is the largest reworking of UK data protection law since Brexit: it replaces the UK GDPR's balancing-test machinery with "recognised legitimate interests," lets controllers stop the DSAR clock by asking clarifying questions, rewrites the solely automated decision-making rules, imposes a mandatory complaint-handling duty, and reorganizes the ICO into a new Information Commission. Each change lands on a different engineering surface — processing records, request ticketing, ADM registers, complaint SLAs — and teams that treat the DUAA as "GDPR unchanged" will ship systems that misstate their lawful basis or miss statutory response windows.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Recognised Legitimate Interests

1. **Annex 1 purposes skip the balancing test.** Processing for listed purposes — including national security, public security, defence, immigration, safeguarding vulnerable individuals, and certain fraud, tax and record-keeping purposes — can rely on recognised legitimate interests with no legitimate interests assessment (LIA) and no right to object, though transparency duties still apply.
2. **Reasonable expectations still bind.** Even for listed purposes, the processing must be within the reasonable expectations of the data subject, so profiling that surprises users can still fall outside the basis; document expectation evidence (notice copy, UX flows) next to the purpose tag.
3. **Purpose tagging in ROPA.** Update the record of processing activities and the lawful-basis enum in code so every processing stream carries whether it uses GDPR Article 6(1)(f) with an LIA reference, or an Annex 1 recognised interest with its clause number — auditors will ask for exactly this split.
4. **Fraud-prevention scope is narrow.** The fraud and financial-crime purposes cover detection and prevention but not wide commercial scoring; mislabeling marketing analytics as "fraud prevention" is the predictable misuse to design against with policy-as-code checks.

## Subject Access And Stop-The-Clock

1. **Clarification can pause the one-month deadline.** A controller may extend the one-month response window by asking for reasonable and necessary clarification of the request, but only where it asks promptly and the clarification is genuinely needed; vexatious clarification is treated as non-response.
2. **Ticket-state machine.** DSAR tooling needs explicit states for received, clarification-pending (clock stopped), clarified (clock restarts), searching, third-party consultation, and delivered, with deadline calculation storing both stopped and running timers and an audit log of when clarification was requested and why.
3. **Reasonable and proportionate search.** The DUAA codifies that searches must be reasonable and proportionate to the request's scope, so document search methodology (systems queried, identity verification applied, exclusions for legal privilege) per request as evidence.
4. **Promptness requirement.** Build a detection rule that forces the clarification question out within the first few days; a clarification asked on day 28 will not stop enforcement where a regulator views it as dilatory.

## Automated Decision-Making Rework

1. **All solely automated significant decisions regulated.** The DUAA replaces the GDPR's special-category-only ADM carve-in: solely automated decisions with legal or similarly significant effects may proceed where necessary for contract, authorized-by-law, or legitimate interests (with safeguards), and special-category data ADM is allowed with explicit consent or substantial public interest plus safeguards.
2. **Safeguards as product features.** Required safeguards include providing meaningful information about the decision, the ability to express a view, the ability to contest, and human intervention on request — implement these as API surfaces and UI flows, not just policy text, so the register entry for each ADM system links to its implemented safeguard endpoints.
3. **ADM register.** Maintain an inventory of solely automated significant decisions (credit, pricing, moderation, hiring-adjacent scoring) with model version, human-review path, and contest SLA; the register is the artifact both DPOs and the Information Commission will inspect.
4. **Contest routing.** Contest requests need a human reviewer queue with model-context tooltips (feature attributions, thresholds) so the human reviewer can genuinely change the outcome rather than rubber-stamp it, which is the regulatory test of "human intervention."

## Complaints, Enforcement And Regulator Change

1. **Mandatory complaint-handling procedure.** Controllers must operate a documented procedure for data-subject complaints, acknowledge complaints, and respond within a defined timeframe; complaint records become an enforcement surface, so integrate complaint intake with the privacy-rights portal rather than a mailbox.
2. **ICO becomes the Information Commission.** The ICO is restructured into a corporate Information Commission with a board and CEO, with new duties to have regard to growth and innovation — the cultural signal is fewer maximalist fines, but powers are retained, and complaint-handling failures are a new low-friction enforcement lane.
3. **International obligations acknowledgment.** The Act requires the regulator to have regard to international data-protection standards, reflecting the sensitivity of the pending EU adequacy review; keep EU-GDPR-grade practices in place for EU-facing data to avoid being the test case that unravels adequacy.
4. **Commencement staggering.** Provisions commenced in phases through 2025-2026; track the commencement regulations for each Schedule (especially ADM and complaint-handling) so system go-live dates match the law actually in force on that date.

## Smart Data, Verification Services And Next Steps

1. **Smart data schemes.** The DUAA creates a framework for mandated data-sharing schemes in the style of open banking (energy, telecoms, health flagged), with obligations on data holders to expose customer data to authorized intermediaries on request — architect an API surface and consent ledger now if you operate in a scheme-designated sector.
2. **Digital verification services.** A trust-framework route for identity verification providers creates reusable verified-identity signals that can serve age assurance and DSAR identity checks; watch for the register of certified providers before wiring one in.
3. **Subsequent reforms.** A further Data Bill cycle is planned covering creative industries and research uses; keep the lawful-basis and purpose-tag architecture configurable rather than hard-coded, because the enumerations will change again.
