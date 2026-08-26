# release-branches-vs-tags-policy

**Issue:** Teams burn surprising amounts of time arguing about what a "release" even is: does it start with a branch, a tag, or a CI run on trunk? The policy choice determines whether fixes ship once or get cherry-picked five times, whether a production incident can be answered with "what exact code is running", and whether the branching model quietly caps deploy frequency. DORA's guidance is direct: teams deploying multiple times a day need no release branches at all — changes go to trunk and deploy — while release branches earn their keep only when cut from trunk on demand and kept short-lived. This article defines the decision: tag-and-ship from trunk as the default, release branches for genuinely long support windows, and immutable artifacts as the thing actually deployed either way.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The default: tag and ship from trunk

1. **Trunk is the only long-lived branch.** Feature branches live hours or days; nothing else persists. Every merged change is a deploy candidate, and the pipeline can ship trunk at any time.
2. **A tag records the release event.** Cutting `v2.7.3` on trunk is an annotation, not a fork: it marks the exact commit the release build was produced from, giving audits and incident response a stable source anchor.
3. **Tags do not freeze code.** Nothing stops trunk after a tag; the next release is the next tag. This is what keeps deploy frequency uncapped by the branching model.
4. **Fix forward, redeploy.** For a bug found post-release, the default path is a fix merged to trunk and shipped as a new tag — one code path, no cherry-pick debt. Rollback, when needed, redeploys the previous artifact.

## When release branches earn their keep

1. **Long support windows.** If customers run supported versions for months (on-prem installs, mobile OS review cycles, regulated LTS), backported fixes need a `release/2.7.x` branch cut from trunk at the tag; DORA's trunk-based capability page frames exactly this as the acceptable exception.
2. **Strict stabilization windows.** When a release must soak with a frozen feature set for contractual reasons, a short-lived stabilization branch taken late from trunk is cheaper than freeze discipline on trunk itself.
3. **Branches are cut, never created sideways.** A release branch always starts at a trunk tag, receives cherry-picks or merges back, and is not a place where features happen. Branches live for the support window, are named for the version, and are deleted when support ends.
4. **Count them.** A policy of "release branches only when needed" decays into permanent branches; set a soft limit (say, two active release lines) and require justification for a third.

## Tags anchor, artifacts deploy

1. **The deployed thing is the artifact, not the ref.** Production runs an immutable, digest-identified build (image, bundle, package). The tag names the commit it came from; the digest is what rollback and audit operate on.
2. **Record the linkage.** Every release records tag, artifact digest, build provenance, and deploy metadata together; "what is running in prod" must be answerable from one query, not git archaeology.
3. **Never build the same tag twice differently.** A tag whose commit rebuilds to a different artifact (mutable base images, floating dependencies) breaks the anchor; reproducibility discipline (see dependency-vendoring-offline-deploys) is what makes tags meaningful.
4. **Moving tags are forbidden.** Re-pointing `v2.7.3` at a different commit to "fix" a bad release destroys auditability; the fix is `v2.7.4`.

## Anti-patterns

1. **GitFlow as a lifestyle.** Long-lived develop plus release branches plus hotfix branches multiplies every fix across branches and caps release cadence at the branch-sync ceremony; most web services need none of it.
2. **Environment branches.** Branches named for staging or production mean deploys are diffs between branches; config belongs in the environment, versions in artifacts (see env-var-management-strategy).
3. **Cherry-pick pipelines.** If every fix must be cherry-picked to two or more release branches, the policy has quietly re-created a merge queue with extra steps; fix-forward on trunk with fast releases is the exit.
4. **Tags as human-only deploy triggers.** A policy where releases happen only "when someone cuts a tag" without automation makes the tag a bottleneck ritual; the pipeline should be able to release trunk on demand, tags or no tags.

## Writing the policy down

1. **One page, three questions.** The policy answers: where releases come from (trunk), when branches are allowed (support windows, with limits), and what identifies a release (tag plus artifact digest plus provenance).
2. **Encode what is enforceable.** Branch protection on trunk, deletion policy for release branches, and CI checks that block mutable or unsigned releases turn the policy from prose into constraints.
3. **Revisit when cadence changes.** A team moving from monthly to daily deploys should collapse its branch model before the branches collapse it; the branching policy follows the delivery cadence, not the reverse.
