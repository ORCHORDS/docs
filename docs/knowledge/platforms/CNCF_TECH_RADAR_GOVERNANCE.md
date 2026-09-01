# CNCF Technology Radar Governance

## Purpose

The CNCF Technology Radar (and the broader thoughtworks-style radar format adopted by many CNCF projects) is a periodic, opinionated view of the cloud-native landscape. It classifies tools and practices into four rings — adopt, trial, assess, hold — across the categories of languages, frameworks, infrastructure, and practices. The radar is most useful as a forcing function for explicit, dated technology decisions.

## Scope

A radar is not a standard, a control catalog, or a procurement rule. It is a curated list that should be paired with internal evidence (POC results, runbooks, incident records, audit findings). This article documents a reusable governance pattern that pairs the radar format with the change-management discipline that platforms need.

## The four rings

- **Adopt**: the technology or practice is recommended for general use; teams may use it without further justification.
- **Trial**: the technology or practice is ready for limited production use; teams using it must record evidence and an exit criterion back to assess or adopt.
- **Assess**: the technology or practice is worth exploring; teams using it in production must have explicit justification and a documented exit plan.
- **Hold**: the technology or practice is not recommended; new uses require an exception.

The rings are deliberately coarse so that the boundary between them is visible to a reviewer.

## Blip discipline

Each entry on the radar — a "blip" — should be dated, named, and summarized in a sentence or two. Movement between rings should be justified with a reason that names the evidence (e.g., "moved from trial to adopt: two production deployments for six months with no P1 incidents"). Without dated blips and reason records, the radar becomes folklore.

## Engineering workflow

1. Publish the radar on a fixed cadence (typically quarterly or bi-annually) with named editors.
2. Capture each blip with a date, a ring, a one-line rationale, and a change-reason when moved.
3. Tie the radar to the change-management process: new technology adoptions reference the radar entry that permitted them.
4. Run a review of "hold" blips at least annually to confirm the exception is still active.
5. Pair every "trial" and "assess" blip with an explicit exit criterion that names the evidence required to move it.

## Controls and evidence

- A dated, signed radar with named editors.
- Per-blip change log: previous ring, new ring, change reason, evidence link.
- Exception register for every "hold" blip that is in active use.
- Change tickets that reference the radar entry.

## Validation

- Independent reviewer confirms the radar is current and the change log is complete.
- An exception register review confirms every "hold" exception is approved and dated.
- Trial/assess exit criteria are checked against actual usage data.

## Failure modes and corrections

- Publishing the radar without naming editors — correct by listing named editors and an update cadence.
- Treating the radar as a permission rather than a forcing function — correct by requiring a radar entry for new adoption and a change ticket for movement.
- Letting blips sit in "trial" indefinitely — correct by enforcing exit criteria and reviewing at the next radar publication.
- Using the radar to overrule a security finding — correct by treating the radar as one input alongside the control catalog and threat model.

## Quadrants and scope

Most radars organize blips into quadrants — commonly techniques, tools, platforms, and languages-and-frameworks. The quadrants exist to prevent one category from crowding out the others: a radar dominated by tools with no entries under techniques usually signals that the team is adopting products without adopting practices. Reviewers should confirm that each quadrant is meaningfully populated, or explicitly record why a quadrant is empty.

## Cadence and archival

The radar's value decays without a publication cadence and an archive:

- Fixed cadence (quarterly or bi-annually) keeps the radar from becoming a historical document.
- The archive of prior editions is the audit trail; a reviewer should be able to reconstruct what the organization believed at a given date and what changed since.
- Each edition should record the date of publication, the editors, and a summary of the most significant movements.
- Blips that disappear entirely should be recorded as removed, with a reason, rather than silently deleted.

## Relationship to graduated projects

CNCF project graduation stages (sandbox, incubating, graduated) are a separate maturity signal from radar rings. A graduated project is not automatically "adopt" on an internal radar, and a sandbox project is not automatically "hold." Teams should treat the CNCF maturity stage as one input to the ring decision, alongside internal evidence, support requirements, and operational fit.

## Limitations

- A radar is opinionated and reflects the editors' view; it is not a survey.
- Ring classifications can lag the ecosystem by one or two release cycles.
- A radar does not specify how to operate a tool; teams still need runbooks.
- It does not substitute for procurement due diligence on licensing, support, and supply-chain risk.

## Canonical sources

- CNCF TAG App Delivery (CNCF, primary authority) — TAG App Delivery Radar: https://github.com/cncf/tag-app-delivery/tree/main/radar
- CNCF (CNCF, primary authority) — TAGs overview and charter: https://github.com/cncf/

## Scope note

This article summarizes project-neutral governance patterns inspired by CNCF TAGs and the broader radar format. It does not adopt or reject any specific blip on any specific radar.