# Partner Escrow Agreement Release Conditions Evidence

An escrow release clause is only as strong as the evidence that proves its conditions were, or were not, met. This article defines the evidence-file discipline for release conditions in partner source-code escrow: how to make each condition objective, how to bound it in time, how to assemble the proof file when a condition arguably occurs, and how to defend that file later. It addresses the evidentiary layer that sits on top of the agreement terms themselves.

## Scope

In scope: drafting release conditions so they are objectively determinable, building the standing evidence file that monitors those conditions continuously, assembling a trigger-event proof package, and preserving the record through disputes. Out of scope: choosing the escrow agent, deposit content standards, and verification regimes, which are covered by the deposit-mechanics article. The controlling role is the **release-conditions custodian**, accountable in the beneficiary organisation; the depositor's counterpart is the **trigger-response owner**, who must produce or contest evidence within contractual clocks.

## Workflow or implementation guidance

1. Rewrite every proposed release condition into a three-part form: an observable event, a defined evidence artefact that demonstrates it, and a time bound for both occurrence and proof. "Supplier ceases business" becomes "a liquidator, trustee, or equivalent officer is appointed, evidenced by a filed notice or public register entry, with a 30-day period to assemble the certified copy."
2. Build a conditions register as a controlled document. One row per condition, with fields for trigger event, evidence artefact, authoritative source of that artefact, who certifies, objection window, and the standing instruction to the escrow agent. Version the register and bind it contractually as a schedule so later amendments follow contract-change control.
3. Assign each evidence artefact to a named authoritative source: a court docket, a companies register, an insolvency practitioner's notice, a ticketing system of record for support-abandonment conditions, or a bank record for non-payment conditions. Where the source is the counterparty's own system, add an independent corroboration requirement, because self-reported evidence fails exactly when the counterparty is failing.
4. Define the proof package standard: a cover index, certified or hash-verified copies of each artefact, a statement of the conditions satisfied, timestamps in a single time convention, and the identity and authority of each certifier. Prepare the index template in advance so assembly under pressure is a fill-in exercise, not a design exercise.
5. Run continuous monitoring rather than event-driven collection. Conditions such as support-response failures accumulate slowly; a monthly sweep of the conditions register against live sources produces a dated trail showing diligence and prevents a claim that the trigger was manufactured after a dispute arose.
6. Rehearse assembly. Once a year, build a proof package against a hypothetical trigger and time it. Record gaps — sources that no longer exist, registers that changed format, contacts who left — and correct the register.
7. Serve the package per the agreement's notice clause: named recipient, channel, deemed-receipt rules, and the objection clock start. Log service itself as an artefact; disputes often turn on when the clock began.
8. Maintain the defensive file on the other side of the table: if the organization is the depositor, keep the same register with exculpatory artefacts — evidence of continuing support, of solvency, of cure — so a contested release can be met with an equally dated record.

## Controls

- Conditions register, contractually incorporated, one row per trigger, no condition without a named evidence artefact and authoritative source.
- Corroboration rule: any artefact originating solely from the counterparty requires a second independent source.
- Monthly monitoring sweep with a dated output retained even when nothing is found; negative findings are evidence of diligence.
- Annual rehearsal of proof-package assembly with a measured completion time and corrective actions.
- Hash verification of every artefact at capture, with hashes recorded in the package index.
- Objection-clock tracker with escalation at 50%, 80%, and 100% of the window.
- Access control on the evidence file: least privilege, because premature or strategic disclosure can waive protections or tip negotiation position.

## Validation evidence

The discipline produces the conditions register with change history, monthly sweep outputs, capture logs with hashes, rehearsal reports with timings and findings, proof packages with indexes, service records, objection notices, and resolutions. Validate by sampling one condition and confirming the register row names an artefact that actually exists at its authoritative source today; then sample one monthly sweep and confirm it was executed on schedule and archived. Test hash reproducibility across a sample of captured artefacts. A register whose artefacts have dead sources is a latent failure, not a historical curiosity, and must be corrected at the next review. Reviewers should be able to reconstruct, from the file alone, what condition was asserted, on what proof, served when, and objected to or not.

## Failure modes and correction

Frequent defects: conditions defined by adjectives ("material failure to support") with no measurement rule; evidence sources that were single points of failure, such as one official's mailbox; proof packages assembled post hoc with recreated timestamps, which destroys credibility; monitoring that stopped during the very instability that constituted the trigger; and objection windows that expired unwatched. Correct by amending the register to add measurement rules, adding corroborating sources, and re-baselining the monitoring schedule. Where a package was assembled irregularly, disclose the defect and rebuild the chain from original sources rather than papering over gaps; a corrected record with a documented discontinuity is defensible, a silently rewritten one is not. If monitoring lapsed for a period, reconstruct coverage from third-party sources where possible and record the blind spot explicitly.

## Limitations

Evidence discipline cannot rescue an ambiguous underlying condition; drafting fixes belong in the agreement. Insolvency proceedings may stay contract enforcement regardless of proof quality, and foreign registers vary in accessibility and certification practice. Monitoring implies no right to surveil beyond contractual information rights. This is operational guidance on evidence management, not legal advice on the enforceability of any particular release condition.

## Canonical sources

- WIPO — Arbitration and Mediation Center, evidence and expert determination procedures: https://www.wipo.int/amc/en/
- ICC — Rules on expert and evidence services: https://iccwbo.org/dispute-resolution/dispute-resolution-services/
- NIST — SP 800-86, Guide to Integrating Forensic Techniques into Incident Response: https://csrc.nist.gov/pubs/sp/800/86/final
