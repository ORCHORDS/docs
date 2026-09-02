# NCSC-UK Cyber Assessment Exercise Governance

## Purpose

Govern the studio's use of NCSC-UK (National Cyber Security Centre) assessment and exercise guidance so that security posture is tested through structured exercises: NCSC's exercise guidance (Exercise in a Box and related tooling) provides scenario-based assessment that surfaces readiness gaps in a controlled, low-cost format.

## Scope

Applies to the studio's security exercise program where NCSC-UK guidance is the methodology source. Covers exercise selection, scenario adaptation, execution, and finding handling. Does not cover full ISO 22398-scale exercise programmes (covered separately) or incident response execution.

## Workflow

1. Select exercises against current risk priorities: NCSC's Exercise in a Box scenarios (threat response, ransomware, data breach, supply chain) chosen where they exercise the studio's current top risks, not uniformly.
2. Adapt scenarios to studio context: exercise injects and questions tailored to actual systems, third parties, and decision-makers — generic scenarios produce generic lessons.
3. Run exercises with the real decision-makers: the participants who would respond in an actual event; deputies exercising in place of principals exercises the wrong muscle.
4. Record performance against objectives: decisions made, information flows used, gaps surfaced — scribed during the exercise, not reconstructed.
5. Debrief honestly: the debrief surfaces what failed without blame attribution; exercises that end without uncomfortable findings were theater.
6. Convert findings to actions: every gap enters the improvement register with owner and date; recurring findings across exercises escalate as systemic.
7. Advance exercise complexity over time: discussion-based to simulation to technical exercises as maturity grows; repeating comfortable scenarios inflates confidence without capability.

## Controls and evidence

- Exercise selection rationale tied to risk priorities.
- Adapted scenario materials with studio context.
- Participant lists confirming decision-maker attendance.
- Scribed performance records.
- Debrief records with surfaced gaps.
- Improvement register entries with owners and dates.

## Validation

- Confirm the last two exercises each produced findings that entered the improvement register.
- Sample five register items from exercise findings: confirm closure or documented acceptance.
- Confirm participant lists included the actual responders for the exercised scenarios.

## Failure correction

- **Exercise without findings** → reassess scenario difficulty and honesty of debrief; zero-finding exercises are measurement failures.
- **Findings not entering the register** → fix the intake path; untracked exercise findings are lessons prepaid and wasted.
- **Recurring finding across exercises** → escalate as systemic: the fix attempted did not address root cause.

## Limitations

- Exercise in a Box targets UK organizations primarily; the methodology generalizes, and scenarios need local adaptation elsewhere.
- Discussion-based exercises surface decision gaps, not technical capability; technical exercises test separately.
- Exercise findings are sampled capability; passing an exercise does not certify incident response.

## Scope note

This article is part of the security leaf. Cross-reference: `ISO_22398_2019_EXERCISE_PROGRAMME_GOVERNANCE.md` (business leaf), `NIST_SP_800_61_R3_INCIDENT_RESPONSE_TIMELINE_GOVERNANCE.md` (operations leaf), and `ENISA_THREAT_LANDSCAPE_ANNUAL_ASSESSMENT_GOVERNANCE.md`.

## Canonical sources

- NCSC-UK — Exercise in a Box: https://www.ncsc.gov.uk/collection/exercise-in-a-box
- NCSC-UK — Guidance on cyber exercises: https://www.ncsc.gov.uk/section/advice-guidance/all-topics
- CISA — Tabletop Exercise Packages: https://www.cisa.gov/topics/cyber-threats-and-advisories/exercises
- NIST SP 800-84 — Guide to Test, Training, and Exercise Programs: https://csrc.nist.gov/publications/detail/sp/800-84/final
- ISO 22398:2019 — Guidelines for conducting exercises: https://www.iso.org/obp/ui/#iso:std:iso:22398:ed-1
