# Commercial SSDF Requirements Traceability

When a commercial agreement imports the NIST Secure Software Development Framework (SSDF, NIST SP 800-218), the hard work is traceability: each framework task must become a numbered schedule line, each schedule line must carry an acceptance criterion, and each criterion must name the evidence a reviewer will inspect. Without that chain, secure-development obligations degrade into a general promise that neither party can verify at milestone time. This article describes the traceability method: selecting SSDF tasks, drafting objective acceptance criteria, linking evidence, and keeping the chain intact when the contract or the framework changes.

## Scope

This article covers the construction and maintenance of a requirements traceability matrix (RTM) that connects SSDF tasks to contract schedule lines and acceptance criteria for commercial software engagements. It covers matrix structure, criterion drafting, evidence linkage, milestone integration, and change control. It does not cover the substantive drafting of the security obligations themselves (covered by the companion article on secure development lifecycle contracting), nor full conformance assessment against government attestation forms, nor general requirements engineering for functional scope.

## Workflow or implementation guidance

**Step 1 — Extract the task inventory.** Read the framework's task list and mark each task as in scope, out of scope with reason, or conditional (triggered by, for example, use of a compiler, use of third-party components, or delivery of signed artifacts). The out-of-scope reasons matter more than the in-scope marks: they are the first thing a reviewer challenges. Typical early rows: organization-level secure coding standards and training (PO practices), repository and build integrity (PS practices), threat modeling and static analysis (PW practices), and vulnerability intake, triage, and remediation windows (RV practices).

**Step 2 — Draft schedule lines with stable identifiers.** Give every obligation a contract-visible identifier, such as SCHED-SEC-014, and phrase it with a single duty holder and a single observable outcome. One schedule line should not bundle a tool purchase, a procedure, and a report; split them so that partial compliance is visible instead of averaged away.

**Step 3 — Write acceptance criteria in measurable form.** For each line define: the trigger (per release, per quarter, on event), the artifact, the quality bar the artifact must clear, and the pass condition. "Static analysis results are available" fails as a criterion; "static analysis summary for each release, produced within the release record, with unresolved findings classified and dispositioned" passes. Criteria should avoid adjectives that require judgment calls at acceptance time.

**Step 4 — Bind criteria to milestones.** Map each schedule line to the contract milestone at which it is first verified (design review, first delivery, each subsequent release, annual review). Payment-triggering milestones should reference the matrix row numbers directly, so the acceptance meeting works from the matrix rather than a separate narrative report.

**Step 5 — Assign evidence owners and locations.** For each row record who produces the artifact, where it is stored, how long it is retained, and which party controls access. Evidence behind the supplier's firewall with no export path is a latent dispute; agree formats and retrieval up front.

**Step 6 — Run the verification pass.** Before each milestone, walk the matrix: row by row, confirm artifact existence, version, date, and consistency with the criterion. Log each row as met, partially met, or not evidenced, with the reviewer and date. Partially met rows get a disposition, not a silent pass.

**Step 7 — Govern change.** When the engagement's scope changes (new component source, new build pipeline), update the conditional rows and re-baseline the matrix with both parties' sign-off. When the framework revision changes, diff the task list, mark each task as unchanged, modified, added, or removed, and amend the schedule through contract change control rather than silently continuing on the old list.

**Step 8 — Archive per release.** Snapshot the matrix state used at each acceptance so that later disputes are argued against the criteria that were actually in force, not the current ones.

## Controls

The matrix is a controlled document: unique row identifiers never reused, version history retained, changes requiring dual sign-off. Criteria language is reviewed for testability before schedule finalization; any criterion that cannot be verified by inspecting an artifact is rewritten or converted to a stated intention outside acceptance. Conditional rows carry their trigger conditions explicitly. A completeness rule should hold that every security obligation in the schedule has a matrix row, and every matrix row has an evidence slot — no orphan clauses, no evidence without an obligation.

## Validation evidence

Validation artifacts include the current matrix with version and date, the task selection rationale (including out-of-scope reasons), milestone verification logs with row-level dispositions, archived matrix snapshots per accepted release, change-control records for both scope and framework revisions, and a periodic sample re-check in which an independent reviewer reproduces the verdict for a subset of rows using only the named evidence.

## Failure modes and correction

- **Criterion drift.** Criteria were quietly loosened in working documents while the schedule stayed strict. Correction: re-run verification against the schedule text and document any true gaps as nonconformities.
- **Orphan clauses.** A schedule obligation lost its matrix row during an edit. Correction: completeness check, restore the row, verify retrospectively.
- **Evidence without dates or versions.** Artifacts exist but cannot be tied to a release. Correction: regenerate evidence for current releases and amend the criterion to require identifiers going forward.
- **Framework revision ignored.** The matrix still maps tasks from a superseded revision. Correction: run the diff, amend through change control, and record the transition date.
- **Judgment-call criteria.** Rows relying on "adequate" or "reasonable." Correction: rewrite with observable conditions at the next amendment window.

## Limitations

A traceability matrix documents the obligations and their evidence; it does not itself make the development secure, and a fully green matrix can still describe a process with weak substance if criteria were drafted too leniently. Matrix maintenance adds overhead to every scope change. Framework task numbering and emphasis change between revisions, so historical matrices should be read against their own revision context. Contract interpretation questions belong with qualified counsel.

## Canonical sources

- National Institute of Standards and Technology, *Secure Software Development Framework (SSDF) Version 1.1 — NIST SP 800-218*: https://csrc.nist.gov/publications/detail/sp/800-218/final
- National Institute of Standards and Technology, *Cybersecurity Framework*: https://www.nist.gov/cyberframework
