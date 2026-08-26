# rollback-drills-restore-testing

**Issue:** Every team claims they "can roll back," but almost nobody has actually executed their rollback path under pressure recently. The image tag they would redeploy has been garbage-collected, the DB "restore point" assumes a PITR window nobody has timed, the config/feature-flag state that accompanied the bad release has drifted three versions since, and the runbook's step 4 references a dashboard that was renamed. This article covers rehearsed rollbacks as a practice: pinning composite restore points (code + schema + config + flags), running game-day drills that exercise the full path, and measuring whether your rollback actually meets the RTO you tell leadership it meets. It is the drills-and-rehearsal companion to rollback-runbook.md and pre-deploy-database-backup.md.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why untested rollback paths are fictional

1. **A rollback you have never executed is a hypothesis, not a capability.** AWS's Well-Architected definition of a game day is "simulating a failure to test systems, processes, and team responses by actually performing the actions the team would take" — the operative phrase being *actually performing*. A runbook that has only ever been read is documentation, not muscle memory.
2. **Green backup dashboards prove nothing about recovery.** The recurring failure mode in DR postmortems (see Eon's disaster-recovery-testing writeups) is treating a *completed backup job* as proof of recoverability — it only proves a copy exists, not that it restores, not that the restore is complete, and not that anything can authenticate to the restored system afterward.
3. **Rollback dependencies rot faster than the code.** Old image tags get pruned from the registry, Helm chart versions get deleted from the repo, secrets referenced by the old manifest have been rotated, and the metrics baseline you would compare against has been re-indexed. Untested paths decay silently.
4. **Partial rollbacks are worse than none.** Rolling back the app but not the feature-flag state, or the code but not the config change, produces a hybrid state nobody has ever seen in staging. This is how a 10-minute incident becomes a 4-hour one — the system is in a state that matches no known-good snapshot.
5. **Stress inverts competence.** Game-day practitioners consistently observe that without a tested abort procedure, teams "spend 20 minutes figuring out how to stop an experiment while users are affected." Under adrenaline, people skip steps, misread their own runbook, and fumble the credential lookup that was never rehearsed.

## The composite restore point — pin everything as one bundle

1. **A rollback target is a tuple, not an image tag.** Pin, together and immutably: the container image *by digest* (not a mutable tag — see container-image-tagging.md), the Helm/manifest release revision, the last-known-good schema migration version, the config/secret revision, and the feature-flag state snapshot. Store the tuple as an artifact of every production deploy (e.g. a JSON emitted by the pipeline).
2. **Make the DB restore point explicit and time-bounded.** Record the migration checkpoint (e.g. the applied-migrations head, or a WAL/PITR timestamp captured at cutover — the mechanics are in pre-deploy-database-backup.md) inside the same tuple. State the PITR window your provider actually gives you; a "restore to just before the deploy" claim with a 15-minute-granularity backup is a lie you discover during the incident.
3. **Pin the flag state alongside the image.** Most 2025-era rollbacks are flag rollbacks, not code rollbacks. Snapshot the flag evaluation config at deploy time so the drill can restore the exact same combination of code + flags that previously served traffic. See feature-flag-deploy-coupling.md for why flags and deploys drift apart without this.
4. **Version the rollback tooling itself.** If rolling back requires a specific CLI or action version, pin it the same way the forward deploy does. A drill that fails because `rollback.sh` calls a plugin API that changed is a finding, not an inconvenience — capture it.
5. **Keep the bundle for N releases, not forever.** Retention should match your realistic rollback horizon (typically 2-4 releases). Beyond that, the schema has usually moved past backward compatibility and "rollback" becomes "forward-fix" anyway.

## The game-day drill format

1. **Pick one concrete scenario per drill, drawn from near-misses.** Good scenarios: "yesterday's release doubled p99 and we must restore the previous tuple," or "a migration corrupted a subset of rows and we must restore one table to a point-in-time and replay." Scenarios sourced from your own postmortems (post-incident-review-template.md) beat invented ones.
2. **Assign the classic game-day roles.** A participant executing the runbook on a real (staging or shadow) environment, a controller injecting complications, and an observer recording timestamps and deviations from the runbook. The observer's log *is* the deliverable.
3. **Include at least one inject.** Mid-drill, the controller breaks something the runbook assumes: the on-call's token is expired, the registry is rate-limiting pulls, the "old" revision was garbage-collected. Injects are where fictional runbooks die — that is the point.
4. **Execute against real infrastructure where possible.** Restore into a throwaway environment (the pattern in pre-deploy-database-backup.md restores a dump to a temp instance); a tabletop-only exercise where people narrate what they *would* click finds roughly 30% of the issues a hands-on drill finds, because hands-on drills surface missing permissions, dead links, and tooling rot.
5. **Time-box the drill and stop at the box.** If the drill blows past the RTO you promise, record it as a failure of the rollback path, not of the team. The honest output of early drills is usually "our rollback is 3x slower than we believed."
6. **Close the loop like an incident.** File findings with owners. The most common first-drill findings: expired or missing credentials for the restore path, image/revision pruning that removed the rollback target, and runbook steps that reference renamed dashboards or departed Slack channels.

## What to measure

1. **Time-to-rollback end to end, split into phases.** Detect → decide (who has authority, how fast do they answer) → execute → verify (smoke tests + error-rate check against the pre-deploy baseline). Report the split, because "we can roll back in 5 minutes" usually means "execution is 5 minutes once someone decides, which takes 25."
2. **RTO/RPO validation against the stated targets.** disaster-recovery-failover.md notes RTO/RPO targets are "meaningless without a tested runbook" — the drill is where you convert those numbers from marketing into measurements. If measured RTO is 40 minutes and the stated target is 10, one of them must change.
3. **Fidelity checks on restored state.** Row counts or checksums on restored tables, a canary read path through the restored service, and a diff of the flag/config state against the pinned bundle. A restore that comes up but serves subtly wrong data is a worse outcome than one that fails loudly.
4. **Drift found per drill.** Count the things that had silently rotted since the last drill (dead links, pruned revisions, renamed resources). A rising drift count between drills means your rollback path needs to be exercised more often, or automated harder.

## Cadence and ownership

1. **Quarterly minimum for the flagship service, event-driven otherwise.** Run a drill after any major change to the rollback surface: new database engine version, registry migration, flag-platform migration, or a change to deploy topology (e.g. moving to blue-green — see blue-green-traffic-switch.md — which changes what "rollback" even means).
2. **Rotate the participant.** If only the author of the runbook can complete it, you have a bus-factor problem wearing a process costume. Each drill should be executable by someone who has never run it before; their friction is the signal.
3. **Treat drill results as release-gating evidence.** A service whose rollback path failed its last drill carries that status in the risk register (risk-based-deployment-gating.md). Teams that couple drill recency to deploy risk stop treating drills as optional culture and start treating them as maintenance.
4. **Anti-patterns to refuse explicitly.** Tabletop-only "drills" counted as coverage; drills that always succeed because the injects were removed after the first failure; backups verified by checking a dashboard instead of restoring; and rollback plans that exist only as a diagram in a slide deck. Each of these produces a false confidence that surfaces for the first time during a real incident, in front of customers.
