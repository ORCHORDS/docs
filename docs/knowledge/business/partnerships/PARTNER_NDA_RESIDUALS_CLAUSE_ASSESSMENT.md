# Partner NDA Residuals Clause Assessment

A residuals clause lets one party keep using information retained in the unaided memory of its personnel after a confidentiality agreement ends. The clause is common in technology partnerships and is the single most asymmetrical term in a typical partner NDA. This article explains how to assess a residuals clause before signing, how to bound its scope in drafting, and how to keep it auditable afterwards, focusing on retained know-how, general-skills carve-outs, and the practical impossibility of auditing memory.

## Scope

Covers mutual and one-way NDAs between commercial partners where either side proposes residual-knowledge treatment for technical information exchanged during evaluation, joint development, or services work. The accountable role is the **NDA risk assessor**, supported by an engineering lead who can estimate how exposed the organisation is on each side of the clause. Not covered here: marking and return mechanics, non-solicitation terms, or the antitrust limits on exchanging competitively sensitive information, each of which belongs to its own review.

## Workflow or implementation guidance

Start by identifying which party actually benefits. Residuals clauses protect the receiver of information. In a lopsided partnership where one side discloses core technology and the other discloses mostly business context, a mutual residuals clause is effectively one-way in effect even if reciprocal on paper. State this asymmetry in the assessment record before arguing wording.

Second, read the definition of "residuals" itself. The narrow form covers information retained in the unaided memory of individuals who had authorised access — no notes, no copies, no documents. Broad forms sweep in anything "remembered in general terms," or worse, anything "retained" without a memory limitation, which converts a memory carve-out into a licence. Reject any definition that omits the unaided-memory limitation or that covers information retained in systems, repositories, or models rather than minds.

Third, examine what the residuals clause is subject to. Acceptable drafting keeps residuals subject to the confidentiality obligations for tangible materials, to any separately agreed licence restrictions on foreground IP, and to restrictions on using residuals to reverse engineer or to clone the disclosing party's products. A residuals clause that is not expressly subject to the licence terms of a linked development agreement can quietly override them.

Fourth, assess the general-skills carve-out interaction. NDAs also normally exclude from protection information that becomes public, was already known, is independently developed, or is rightly received from a third party, plus general skills and knowledge acquired in the course of work. Two carve-outs operating on the same information create ambiguity: assess whether the agreement states which prevails and whether the combination leaves any meaningful protection on the exchanged technical material.

Fifth, apply a memory-plausibility test with engineering. For the categories of information to be exchanged, estimate whether personnel could realistically retain usable knowledge unaided. Architecture-level insight, debugging heuristics, and performance tuning intuition survive in memory; parameter tables, protocol constants, and full specifications do not. This determines the real economic value at stake and therefore how hard to negotiate.

Sixth, when the organisation is the discloser and must accept residuals, narrow the exposure: limit residuals to named personnel on the project, require a written list of individuals with authorised access, exclude residuals use for competing products for a defined period, and preserve the right to seek injunction for tangible misuse regardless of the clause.

Seventh, document the assessment decision: clause accepted or rejected, scope as signed, exposure categories identified, and the compensating controls chosen.

## Controls

- Residuals definition gate: no acceptance without "unaided memory of individuals," a tangible-materials exclusion, and subordination to foreground-IP licence terms.
- Named-personnel list for any partnership where residuals are permitted, maintained by the project lead and retained with the agreement.
- Exposure register recording which technical categories were exchanged and which plausibly persist as memory-based know-how.
- Compensating-control set for accepted residuals: access logging on disclosed repositories, retrieval of materials at exit, and post-termination personnel-briefing records.
- Sunset review: re-assess the clause at renewal, because personnel movement and product evolution change both sides of the asymmetry.
- Prohibition on using shared model training or automated summarisation pipelines on disclosed materials without an explicit contractual position, since such pipelines convert memory-type exposure into persistent system-type exposure.

## Validation evidence

The assessment produces the signed NDA with the residuals wording as executed, the exposure register, the named-personnel list, engineering's memory-plausibility note, exit retrieval confirmations for tangible materials, and briefing acknowledgements from listed personnel. Validate by tracing one exchanged category end to end: it appears in the exposure register, its tangible carriers were returned or destroyed with a certificate, and the individuals with memory-level exposure appear on the personnel list. Reconcile the personnel list against actual project staffing; unlisted staff who had access indicate the register is stale. Retain the assessment decision itself, including rejections, because the reason a clause was refused is the fastest evidence of what the organisation believed it was protecting.

## Failure modes and correction

Typical failures: accepting a mutual residuals clause in a relationship where disclosure is structurally one-way; treating residuals as the only issue while the general-skills carve-out independently erodes protection; failing to obtain the personnel list that made the risk acceptable; and assuming residuals language was standardised across affiliates when regional templates differ. Correct by amending at renewal or by side letter, re-issuing the personnel list, and running a targeted briefing when staffing changed materially. If a dispute arises over suspected misuse, recognise early that residuals defences are fact-intensive and memory-based; correction should focus on tangible-evidence trails — repositories, commit histories, document access logs — which remain fully subject to the agreement regardless of the clause.

## Limitations

Residuals enforceability varies by jurisdiction and is settled law in few places; the assessment here is commercial-risk analysis, not legal advice. Memory-plausibility estimates are judgements, not measurements, and both parties' personnel behaviour is only partially observable. The clause cannot be audited directly; only its tangible boundaries can. Counsel should review any residuals clause involving trade-secret programmes whose value rests on compilations of small facts rather than architectural ideas.

## Canonical sources

- WIPO — About intellectual property: https://www.wipo.int/about-ip/en/
- OECD — Guidelines governing the protection of confidentiality of data: https://www.oecd.org/en/publications/
- ICC — Model confidentiality contract guidance: https://iccwbo.org/business-solutions/model-contracts/
