# YARA Rule Authoring and Triage Playbook

## Purpose
This playbook defines the standard workflow used to author, test, and tune YARA rules for malware hunting and detection engineering. It integrates with MISP for threat intelligence context and with EDR telemetry for production validation. The objective is to produce rules that are precise, attributable, and tunable, while minimizing false positives and supporting rapid rollback when rules misfire.

## Audience
Detection engineers, SOC analysts, malware analysts, and threat intelligence engineers who own or contribute to the detection rule pipeline.

## Pre-conditions
- YARA installed (4.x line) or YARA-X available on the analyst workstation and CI runner
- A test corpus containing EICAR samples and benign binaries representative of the production environment
- A CI runner configured to execute rule tests on every pull request
- A MISP instance containing malware sample metadata, indicators, and ATT&CK tagging
- EDR endpoint telemetry available for retrospective and live validation
- A version-controlled rule repository with branch protection and required reviewer sign-off

## Procedure
1. Define a hunting hypothesis tied to a MISP event or ATT&CK technique. Capture the indicator, the adversary behavior, and the expected detection surface before any rule is written.
2. Author the rule with explicit `meta`, `strings` (text, hex, and regex as appropriate), and a precise `condition`. Anchor strings where possible to reduce incidental matches.
3. Use YARA modules such as `pe`, `elf`, and `hash` to constrain matches against structured file attributes rather than relying solely on byte sequences.
4. Tag every rule with ATT&CK technique IDs in the `meta` block so downstream reporting maps cleanly to the Navigator.
5. Add the rule to the repository with required metadata: author, date, MISP event reference, external references, and known sample hashes. Record the rule PR in the change log for governance traceability.
6. Run unit tests against the benign corpus and a curated positive sample set. Fail the build on any benign hit.
7. Validate the false-positive rate against a representative production binary corpus, ideally covering 100,000 or more unique files.
8. Pre-compile rules with `yarac` to produce compiled artifacts for the runtime scanner, reducing per-host parse cost.
9. Stage the rule through DEV, STAGING, and PROD environments with promotion gates at each level. Gate criteria include test pass, sample review, and reviewer approval recorded in the change log.
10. Promote the rule to EDR sensors and to the Zeek intel framework feed. Confirm sensor ingestion and intel framework freshness after promotion.
11. Capture alert outcomes and false-positive telemetry for at least 14 days after PROD promotion. Triage every hit using the standard alert playbook.
12. Tune rules based on observed telemetry and update the originating MISP event with validated indicators, false-positive notes, and ATT&CK refinements.

## Rollback
Revert the rule promotion across EDR and Zeek feeds, quarantine any open alerts attributed to the rule, document the false-positive in the rule ticket, and update the MISP warninglist to suppress the indicator. Notify the rule author and detection engineering lead before reopening the rule for rework.

## References

- [MISP Threat Intelligence Platform Version Governance](../reference/MISP_VERSION_GOVERNANCE.md)
- [YARA Pattern Matching Engine Version Governance](../reference/YARA_VERSION_GOVERNANCE.md)
- [Zeek Network Security Monitor Version Governance](../reference/ZEEK_VERSION_GOVERNANCE.md)
- ATT&CK Navigator: https://mitre-attack.github.io/attack-navigator/
