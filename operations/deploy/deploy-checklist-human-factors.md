# deploy-checklist-human-factors

**Issue:** Deploy checklists fail not because they list the wrong steps but because they ignore the humans running them. A checklist that grows to 60 items gets rubber-stamped during a 2 AM release; items that cannot actually be verified get ticked anyway; stale steps survive for services that were decommissioned years ago. Release-engineering writing from 2024-2026 consistently finds that manually-ticked checklists are prone to fatigue-driven blind confirmation — the very errors they exist to prevent — while effective ones stay short, tie automated items to real pipeline results, and borrow from aviation checklist design: testable, grouped, and owned. This article covers designing deploy checklists around human factors; it complements, not duplicates, the technical gate content in pre-production-checklist and post-deploy-monitoring-checklist.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Checklist design principles

1. **Keep each phase under ten items.** Aviation-style checklist design and Miller's law agree: working memory holds roughly five to nine items. Split a 40-item monster into launch-gate, cutover, and verification checklists rather than one wall of checkboxes nobody reads.
2. **Make every item testable.** "Confirm deploy is safe" is not an item; "health endpoint returns 200 in both regions" is. If an item cannot be answered yes or no by direct observation, it will eventually be ticked on faith.
3. **Write items imperatively.** "Confirm database backup completed" beats "backup?". The operator at 2 AM should execute, not interpret.
4. **Choose do-confirm or read-do deliberately.** Read-do suits routine deploys with manual steps; do-confirm (work from training, then verify against the list) preserves flow under pressure. Label which mode a checklist uses.
5. **Keep normal and abnormal variants.** Like aviation's normal and emergency checklists, maintain a distinct degraded-mode checklist for deploying during an incident, where gates such as load tests or soak time are consciously waived and recorded, never silently skipped.

## Human failure modes to design against

1. **Rubber-stamping.** Once a checklist has been ticked from memory twice, it stops being read. Counter it by tying automated items to live pipeline state so ticking without evidence is impossible.
2. **Checklist fatigue.** Long lists train people to skim. Prune ruthlessly every quarter: any item that has never caught a problem and cannot fail independently is a candidate for deletion.
3. **Interruption amnesia.** Deploys get interrupted by pages and questions. Number every item and require recording the deploy ID next to the last completed step so the operator can resume without re-deriving state.
4. **Authority gradient.** A junior operator will tick "approved by on-call lead" without asking if the checklist makes asking awkward. Name the approver explicitly and require their handle in the deploy log.
5. **Time-pressure inversion.** Under pressure people do the fast steps and defer the slow ones. Put the highest-consequence, lowest-effort items (backup verified, rollback artifact exists) at the very top.

## Automating items away

1. **Convert ticks to signals.** Current best practice (Cortex, Octopus guidance) is checklist status driven by pipeline results: the checkbox ticks itself when the smoke suite passes, not when a human says it did.
2. **Automate anything a machine can check.** Version parity, migration status, flag coverage, dashboard annotations — if a script can evaluate it, a human remembering it adds only error probability.
3. **Leave humans the judgment calls.** Keep manual only the items requiring context: is the error budget healthy enough, is this the right moment given the incident calendar, does the blast radius fit today's staffing.
4. **Fail the deploy on unmet automated gates.** A checklist item that can be overridden by ticking harder is decoration; wire critical gates into the pipeline so they block rather than warn.
5. **Measure the automation ratio.** Track what fraction of checklist items are machine-verified. A falling ratio means the checklist is rotting back into ceremony; a rising one means it is being engineered.

## Ownership and maintenance

1. **Version checklists in the repo.** Checklists drift from reality when they live in wikis. Keep them as reviewed markdown next to the deploy code so changes ride the same PR process.
2. **Assign a checklist owner.** Every checklist needs a named owner accountable for pruning and post-incident updates; ownerless checklists only ever grow.
3. **Update from every incident.** Any deploy-related incident must produce a checklist verdict: which item would have caught it, which item failed, what changed. No verdict means the retro is incomplete.
4. **Retire checklists for boring deploys.** The SRE position is that the best release process needs no human checklist at all. When a deploy becomes routine and fully automated, archive the checklist instead of keeping it as theater.
