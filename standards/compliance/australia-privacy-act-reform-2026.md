# australia-privacy-act-reform-2026

**Issue:** Australia's Privacy and Other Legislation Amendment Act 2024 switched on in stages through 2025-2026, and the pieces now live or imminent change engineering calculus: a statutory tort for serious invasions of privacy (in force since 10 June 2025) that makes individuals — not just the OAIC — a direct enforcement channel and adds vicarious liability for employee misuse of personal data; criminal doxxing offences; and, from 10 December 2026, a requirement to disclose automated decision-making in privacy policies, with the OAIC consulting on guidance now. Combined with a children's online privacy code due the same month and the under-16 social media minimum-age law taking effect 10 December 2025, Australian-facing products need a 2026 readiness track distinct from GDPR work.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Statutory Tort And Vicarious Liability

1. **Direct individual claims from June 2025.** Since 10 June 2025 individuals can sue for serious invasions of privacy arising from intrusion upon seclusion or misuse of personal information, where a reasonable expectation of privacy existed and the invasion was serious — meaning access logs, insider-browsing controls, and data-handling practices become litigation evidence, not just regulator matters.
2. **Vicarious liability for employee acts.** Employers are vicariously liable for serious invasions committed by employees in the course of employment, which converts every support-agent peeking incident and every exported customer list into company liability; enforce least-privilege, just-in-time access grants, and anomaly alerts on record access volumes.
3. **Defences to build toward.** The tort carries defences including public interest and reasonably believed necessity to protect another person's vital interests, but the defence lives or dies on contemporaneous documentation — capture purpose at collection and log the justification for unusual access.
4. **Damages discovery exposure.** Civil discovery in tort suits will probe retention: the longer you hoard personal information that staff could misuse, the larger the attack surface for both the tort and equitable damages; cut retention schedules before the first claim letter, not after.
5. **Interaction with OAIC enforcement.** The tort stacks with OAIC determinations and the expanded civil penalty regime (up to AUD 50 million or 30 percent of adjusted turnover for serious interferences), so a single incident can be litigated on two fronts.

## Doxxing Offences And Data Minimization

1. **Criminal doxxing offences.** The 2024 amendments added Criminal Code offences for malicious release of personal information with intent to cause harm, in force since 2025; while aimed at vigilante publishing, the offences focus attention on pipelines that expose personal data in aggregable form — public profile APIs, directory endpoints, and CSV exports.
2. **Enumerate publication surfaces.** Inventory every endpoint that discloses personal information to parties other than the subject (search, embeds, share links, integrations) and rate-limit plus aggregate-proof them; scraping-assembled dumps are the usual doxxing fuel.
3. **Govern bulk export.** Bulk customer-data exports need dual approval, encryption at rest, expiry, and download watermarking; the tort and doxxing regimes both punish downstream misuse of data an employee legitimately could access.
4. **Training and attestations.** Because vicarious liability attaches to course-of-employment conduct, run periodic data-handling training with records — cheap mitigation evidence in both criminal-referral and civil contexts.

## Automated Decision-Making Transparency 2026

1. **APP 1.7-1.9 disclosure from 10 December 2026.** From 10 December 2026, APP entities' privacy policies must include the kinds of decisions made using solely automated processing that could significantly affect an individual's rights, and information about how those automated decisions work — a policy-content duty backed by enforcement powers.
2. **Build an ADM inventory now.** The disclosure is only as accurate as the inventory behind it: catalogue every automated or partly automated decision system (credit, eligibility, pricing, fraud, moderation, matching), its data inputs, logic in plain language, and human-review availability, with owner and review date per entry.
3. **Publishing machinery.** Treat the privacy policy as generated output: the ADM section should render from the inventory so policy and practice cannot drift; the OAIC's draft transparency guidance indicates the expected level of specificity about decision factors and logic.
4. **Alignment with global ADM rules.** Australia's disclosure duty lands alongside the UK DUAA ADM safeguards and EU AI Act transparency duties — capture per-decision metadata (automated or not, significance, safeguards) once in the register, and render jurisdiction-specific disclosures from it.

## Children's Online Privacy Code And Minimum Age

1. **Children's online privacy code.** A registrable code for services likely to be accessed by children (social media, online games, and adjacent services) must be in place by 10 December 2026, with the OAIC driving development in 2026; expect GDPR-style children's defaults (privacy by default, no targeted advertising to children, data minimization) to become binding practice.
2. **Under-16 social media ban.** Separately, the Online Safety Amendment (Social Media Minimum Age) Act 2024 requires covered social-media platforms to take reasonable steps to prevent under-16 accounts from 10 December 2025, with ACCC-enforced penalties — an age-assurance engineering mandate (age-estimation and ID verification flows) on a different clock from the privacy code.
3. **Age signals, dual use.** The same age-assurance infrastructure serves the minimum-age ban, the children's code, and targeted-advertising exclusions; procure one reusable, privacy-protective age-assurance capability rather than per-feature hacks.
4. **Best-interests framing.** Both regimes are framed around the best interests of the child, so document child-impact reasoning for design changes to profiles, messaging, and recommendation features — a child-impact assessment template is cheap now and mandatory-feeling later.

## Engineering Priorities And Program Sequencing

1. **Access governance as tort mitigation.** Rebaseline access reviews, just-in-time elevation, and record-access audit analytics before the tort caselaw matures; early suits will be built on access logs.
2. **December 2026 convergence.** The ADM disclosure and the children's code both land 10 December 2026 — put both on one program with a shared inventory of decisions, data uses, and child-facing features, and a go-live review in Q3 2026.
3. **OAIC powers uplift.** The amendments strengthened OAIC information-gathering and added infringement-notice powers with staged commencement; ensure regulator data requests route through a validated response process, since incomplete answers now carry direct penalty risk.
4. **Statutory review watch.** The Act requires a statutory review of the reform package, and further tranches (including the fate of the small-business exemption) remain open; keep Australian lawful-basis and scope flags configurable in the data-inventory system to absorb the next tranche without a rewrite.
