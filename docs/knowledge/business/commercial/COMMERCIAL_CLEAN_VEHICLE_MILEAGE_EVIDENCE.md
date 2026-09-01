# Commercial Clean-Vehicle Mileage Evidence

Every clean-vehicle mileage credit claim implies an evidence file: the telematics source behind the distance figures, the method that converted raw data into eligible mileage, the retention arrangements that keep the file intact, and the audit access terms under which a third party may inspect it. This article covers that evidence file — what belongs in it, how source reliability is documented, how long records are kept, and how audit access is granted without surrendering control of the underlying fleet data.

## Scope

This article covers the evidence file supporting clean-vehicle mileage credit claims in commercial operations: telematics source documentation, method records, retention rules, and audit access governance. It complements the traceability article, which covers the calculation chain itself; this article covers the file that proves the chain. It does not cover the substantive eligibility rules, tax return mechanics, or jurisdiction-specific recordkeeping mandates, which must be confirmed against the claiming authority's current published requirements.

## Workflow or implementation guidance

1. **Document the telematics source per vehicle.** For each vehicle contributing mileage to a claim, record: the telematics device or platform, its installation date, the distance metric it reports (GPS-derived versus odometer-bus derived), the reporting interval, and any known accuracy characteristics or calibration notes. Where the platform produces raw trip exports, record the export format and field meanings once in a source dictionary, so every later reader of the file interprets fields identically. If a vehicle lacks telematics and uses manual odometer logs, the source record states that plainly — mixed-source fleets are acceptable; undocumented mixed sources are not.
2. **Freeze the source extract for each claim period.** At period close, export and preserve the raw distance data for the period as an immutable artifact (for example, the platform's trip report in its native export plus checksum). Later platform migrations, account changes, or vendor data-retention purges must not be able to erase the basis of a filed claim.
3. **Record the method with its version.** The conversion method — how raw distance became eligible mileage, including personal-use exclusion rules, rounding conventions, and handling of partial days — is documented as a versioned method note. Each claim references the method version in force, and method changes take effect prospectively with a dated change note.
4. **Chain the calculation outputs to the source extract.** Each calculated mileage figure carries a reference to the exact source extract it was computed from (extract identifier plus checksum). A figure that cannot be traced to a preserved extract is marked unverified and excluded or flagged.
5. **Apply retention rules deliberately.** Set retention from the longest applicable clock: authority recordkeeping periods for the claim type, contractual audit rights, and internal policy. Retention is enforced on the preserved extracts, method notes, calculation records, and period summaries together — a file that keeps the totals but purges the raw data proves nothing.
6. **Govern audit access.** Define in advance who may inspect the file: internal audit, the claiming authority, a customer asserting a green-performance clause, or an independent verifier. Prepare an access pack per audience: the extracts and method notes for technical reviewers; summaries with vehicle-level detail for customer audits; and a documented process for authority requests. Access is logged, granted read-only, and scoped to the requesting party's entitlement; fleet-wide raw data (routes, locations, driver behavior) is not handed over when the claim verification only needs distance totals.
7. **Handle gaps and defects visibly.** Where data is missing (device offline, vehicle in service), the gap is recorded in the period file with its cause and the conservative treatment applied. A gap log converts a discovery-time embarrassment into a documented judgment.
8. **Test reconstructability annually.** Once a year, take one closed period and attempt full reconstruction from preserved artifacts alone: extract, method note, calculation, summary. Failures feed back into the source dictionary or retention configuration.

## Controls

Extracts are immutable after freeze; corrections occur through superseding extracts with a linkage note. The source dictionary and method notes are controlled documents with owners and change history. Retention holds are applied before any platform contract or telematics vendor change allows deletion. Access packs are pre-approved per audience, and access events are logged with requester, scope, and date. The gap log is a mandatory period artifact; a period closed without one is incomplete.

## Validation evidence

The evidence file per period contains: source records per vehicle, the frozen extracts with checksums, the source dictionary, method version notes with change history, calculation records chained to extract identifiers, the gap log, period summaries, retention markers with their basis, and the access log. Validation consists of the annual reconstructability test plus sampling: pick claimed figures at random and confirm the chained extract, method version, and calculation reproduce them exactly.

## Failure modes and correction

- **Platform data purged before freeze.** The telematics vendor's retention window closed. Correction: recover what remains (invoices, maintenance odometer records, prior exports), document the loss in the gap log, treat affected mileage conservatively, and schedule freezes earlier going forward.
- **Field meaning drift.** The platform renamed a distance field and later readers misread it. Correction: update the source dictionary with the change date, re-verify affected periods.
- **Method change applied backward.** A new exclusion rule was applied to closed periods. Correction: reopen per adjustment procedure with documented deltas; never overwrite closed figures.
- **Over-broad audit release.** A customer audit received full raw location data. Correction: invoke the breach process if contractual or privacy rules were engaged, tighten the access pack, and retrain approvers.
- **Reconstruction fails.** The annual test cannot reproduce a period. Correction: identify the broken link (missing extract, orphaned calculation), remediate, and check adjacent periods for the same defect.

## Limitations

A well-kept evidence file demonstrates the reliability of the mileage figures; it does not itself establish legal eligibility, correct rate application, or completeness of the claim, which depend on the claiming authority's current rules. Telematics accuracy varies by device and environment; documented calibration limits honesty about precision rather than undermining it. Privacy and employment-law constraints on location and driver data differ by jurisdiction and should be reviewed with qualified counsel before any release.

## Canonical sources

- United States Environmental Protection Agency, *Green vehicle guide*: https://www.epa.gov/greenvehicles
- United States Environmental Protection Agency, *SmartWay — evaluating fleet efficiency*: https://www.epa.gov/smartway
