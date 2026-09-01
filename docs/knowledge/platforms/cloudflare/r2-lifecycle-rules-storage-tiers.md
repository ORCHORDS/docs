# R2 Lifecycle Rules and Storage Tiers

Objects accumulate. Uploads that mattered intensely for a week become logs nobody opens, and storage bills grow quietly in proportion to neglect. R2 lifecycle rules automate the two decisions every object eventually faces — when to move to a cheaper storage class, and when to stop existing — while storage classes set the price structure those rules navigate. Configured well, a lifecycle policy is a standing cost control that needs no per-object attention. Configured carelessly, it is a slow-acting data loss incident with a delay fuse. This article covers designing tiering and expiry rules, the trade-offs between storage classes, and the checks that keep deletion policy from deleting the wrong things.

## Scope

Covers R2 object lifecycle configuration: rules that expire (delete) objects or transition them between storage classes based on age, prefix, or filter conditions, plus the Standard and Infrequent Access storage class trade-offs. Applies to R2 buckets holding user content, logs, media, or derived artifacts. Excludes bucket-level access policy, custom domains, and object locking for compliance retention (which must be evaluated separately because legal hold overrides cost-driven expiry).

## Workflow or implementation guidance

1. Inventory the bucket by prefix and age before writing any rule. A lifecycle rule is a bulk operation over future objects; knowing the current shape (how many objects, average size, age distribution per prefix) is the prerequisite to predicting its effect.
2. Classify prefixes by access decay: hot (accessed within days), warm (accessed within weeks), cold (accessed rarely), and dead (retained only for compliance or forgotten). The classification decides which rules each prefix deserves.
3. Map classes to decay: frequently accessed data belongs in Standard storage; data accessed infrequently suits Infrequent Access, whose lower storage price is offset by higher per-operation charges. The crossover point depends on your read rate per GB per month — below it, IA loses money.
4. Compute the Infrequent Access crossover explicitly for each candidate prefix: monthly operations per GB times the IA operation premium versus the storage saving. A prefix with nightly reads may still belong in Standard; a prefix touched once a quarter belongs in IA.
5. Write expiry rules with a deliberate safety margin. If business needs 90 days of logs, expire at 90 days only after confirming the retention requirement; where the requirement is fuzzy, pick the longer side first — shortening later is easy, resurrecting expired objects is not.
6. Apply filters narrowly. Scope rules to prefixes (and, where supported, conditions such as object size) so a catch-all `expire everything older than X` cannot reach a prefix that was added later without review.
7. Stage rules on a test bucket with a representative sample, verify the transitions and expirations fire as expected, then apply to production and record the applied configuration as the baseline for future audits.
8. Revisit quarterly: new prefixes drift in, access patterns shift, and a rule set that matched the inventory at design time silently mismatches it a year later.

## Controls

- Prefix-scoped rules mandate: lifecycle rules must target specific prefixes; bucket-root catch-all rules require explicit exception review.
- Expiry approval gate: any rule that deletes objects requires a named data owner's sign-off and a stated retention basis.
- Crossover calculation record: each transition-to-IA rule carries the operations-versus-storage arithmetic that justified it.
- Compliance-hold reconciliation: before applying new expiry rules, the object-lock and legal-hold configuration is checked so cost-driven deletion cannot conflict with retention obligations.
- Staged application: new or modified rules are validated on a test bucket first, with observed transitions recorded.
- Quarterly rule audit: applied rules are re-read from the bucket configuration and compared against the recorded baseline; unexplained drift is escalated.

## Validation evidence

- Bucket inventory summary (object counts, bytes, age histogram per prefix) from before rule design.
- The applied lifecycle configuration as read back from the bucket after deployment.
- Test-bucket run log showing transitions and expirations occurring at the intended ages for representative objects.
- Crossover calculation sheets for each storage-class transition rule.
- Data owner sign-off recorded for every expiry rule, with the retention basis stated.
- Quarterly audit output comparing live configuration against baseline, with deltas explained.

## Failure modes and correction

- Catch-all expiry rule deletes a newly added prefix's data: correct by narrowing filters to explicit prefixes immediately, restore affected objects from external copies if any exist, and adopt the prefix-scoped mandate as the systemic fix.
- Objects moved to Infrequent Access are read far more often than predicted: operation charges exceed the storage saving; reverse the transition for that prefix and recompute the crossover with observed access data.
- Expiry set shorter than a compliance retention requirement: suspend the rule, re-derive retention needs with legal or compliance input, and add the reconciliation control to prevent recurrence.
- Rules configured but never verified to fire: lifecycle actions are asynchronous and eventual; verification requires checking object states over time, not assuming configuration equals effect.
- Prefix conventions drift so new data lands outside all rules: detected in the quarterly inventory; fix by adding rules or normalizing prefixes.
- Transition thrash for borderline objects that alternate classes: widen the transition threshold or freeze the class choice for a minimum dwell period per object.

## Limitations

- Lifecycle actions are applied asynchronously; expiry and transitions take effect over time rather than at an exact instant.
- Storage class pricing trade-offs shift with usage patterns, so a once-profitable transition rule can silently become unprofitable.
- Lifecycle rules cannot resurrect objects; expiry is permanent deletion.
- Interaction between lifecycle rules and object lock/retention configurations follows retention rules and needs case-by-case confirmation.
- Prefix-based filtering depends on key discipline; objects uploaded under inconsistent keys escape intended scoping.

## Canonical sources

- Cloudflare R2 docs, "Object lifecycles": https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- Cloudflare R2 docs, "Storage classes": https://developers.cloudflare.com/r2/buckets/storage-classes/
