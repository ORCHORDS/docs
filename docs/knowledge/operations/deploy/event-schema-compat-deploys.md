# event-schema-compat-deploys

**Issue:** A rolling deploy of a service that produces or consumes events (Kafka, Kinesis, RabbitMQ, NATS) means two generations of code are live at once, reading and writing the same topics with potentially different schemas. Deploy the producer first and old consumers crash on deserialize; delete a field before the last reader of that field is gone and you lose data silently. Most teams gate their REST contracts (API versioning-2026.md) but leave their event contracts ungated, then discover during a deploy that "add one optional field" broke a consumer built 18 months ago. This article covers schema-registry compatibility modes, the deploy-ordering rules each mode implies, gating schema changes in CI, and how to ship genuinely incompatible changes without a coordinated shutdown.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why event deploys break in ways HTTP deploys do not

1. **Messages outlive the deploy that wrote them.** An HTTP response is consumed immediately; a Kafka record can sit in a topic for days before a consumer reads it — or before someone rewinds a consumer group to reprocess. A schema change that is "fine for live traffic" can still detonate on replay.
2. **Rolling deploys guarantee version skew.** During the rollout window, old and new consumer pods process partitions concurrently, and if the fleet pauses (or a pod is wedged — see kubernetes-deploy-debugging.md), skew can persist for hours. The schema must tolerate both generations simultaneously, not sequentially.
3. **Failure is deferred and misattributed.** A producer shipping an incompatible schema often deploys cleanly; the error surfaces later in a different team's consumer, lands in a DLQ, or appears as a spike in deserialize errors nobody alerts on. The blast radius is separated in time and ownership from the cause.
4. **Async consumers cannot be load-balanced around.** With HTTP you can route traffic away from old pods; with a consumer group, whichever pod owns the partition *is* the reader, whatever version it runs.

## Compatibility modes and what they actually promise

1. **BACKWARD (the usual default): new schema can read data written with the last schema.** Per Confluent's docs, backward compatibility means consumers using the new schema can process records produced with the new *or previous* schema — the classic compatible changes being adding an optional field with a default, or removing a field.
2. **FORWARD: the mirror image — old consumers can read new data.** Required when you cannot upgrade consumers before producers produce the new shape (e.g. producers are owned by another team on their own cadence).
3. **FULL: both directions.** Old and new code can read each other's data; producers and consumers "can be upgraded independently," which is the property you want if you deploy a producer and consumer from the same service in one rolling update.
4. **Transitive variants check all history, not just the last version.** `BACKWARD_TRANSITIVE` requires the new schema to read data written with *every* prior registered version, not merely the latest. Non-transitive modes only guarantee compatibility between X and X-1 — a consumer still running X-3 during a slow rollout is unprotected. This is why Confluent's own guidance recommends `BACKWARD_TRANSITIVE` for Protobuf (adding message types is not forward-compatible) and why replay-happy Kafka estates default to it.
5. **NONE means the registry will accept anything and protect nothing.** With checks disabled, an incompatible change (Avro `number` to `string`, a renamed field) requires upgrading every client in lockstep or migrating to a new topic. Reserve it for subjects you are actively decommissioning.
6. **The mode is a registry setting, not a hope.** Set it globally or per subject via the registry REST API (a global REST call overrides the properties-file setting) and treat the configured mode as load-bearing infrastructure config, versioned like code.

## Deploy-ordering rules per mode

1. **BACKWARD / BACKWARD_TRANSITIVE: consumers first, then producers.** Upgrade every consumer to a version that understands the new schema before any producer starts emitting it. In pipeline terms: deploy the consumer service, wait for the consumer group to fully rebalance onto new code, then deploy the producer.
2. **FORWARD / FORWARD_TRANSITIVE: producers first, then consumers.** Ship the producer change, wait until old-schema records are no longer being consumed (check consumer lag against the offset where the new schema started), then upgrade consumers.
3. **FULL / FULL_TRANSITIVE: order-independent — but still stage it.** Independent upgradeability is a property you want to *prove* per change, not assume forever; one accidental incompatible field reverts you to needing ordering you no longer have.
4. **Kafka Streams apps are consumers *and* producers with state.** Confluent documents that Streams supports only backward compatibility or stronger (FULL, transitive variants) because the app also replays its own state/changelog topics written with old schemas. The upgrade ordering for Streams: upgrade the Streams application *before* the upstream producer changes what it emits.
5. **Codify the ordering as pipeline dependencies, not tribal memory.** If the consumer and producer are separate services, the producer's prod deploy should be gated (environment-promotion mechanics, deployment-approval-workflow.md) on the consumer deploy having completed — a `needs:` edge or a promotion-gate check, not a Slack message saying "deploy consumers first please."

## Gate schema changes in CI

1. **Run the registry's compatibility check before merge, not at produce time.** Post the candidate schema to the registry's compat endpoint against the target subject in dry-run; fail the PR if it conflicts. This converts a deploy-day incident into a red X on line 3 of the diff.
2. **Bump the subject on purpose, never by accident.** Subject naming (TopicNameStrategy vs RecordNameStrategy vs explicit) decides whether a record rename silently forks into a new subject with no history. Pick one strategy per estate and lint generated registrations against it.
3. **Diff generated code, not handwritten types.** With Protobuf/Avro, the artifact that matters is the generated accessor surface consumers compile against. CI should build the generated bindings and surface breaking changes (a required field appearing, an enum value removed) the way api-versioning-2026.md treats REST contract diffs.
4. **Test both generations against both schemas.** A cheap, high-value CI job: serialize fixtures with the old schema, deserialize with the new build, and vice versa. This catches the default-value and nullable traps the registry's structural check misses.
5. **Alert on DLQ growth and deserialize errors, owned by the producer team.** If incompatible data does ship, the safety net is an alert on schema-rejection metrics — otherwise the failure mode is quiet data loss, which is the worst category in post-incident-review-template.md.

## Shipping genuinely incompatible changes

1. **Dual-publish to a new topic/subject, then cut consumers over, then stop the old stream.** This is expand-contract for event streams: stand up v2 subject (fresh history, `NONE` or strict mode as appropriate), have producers write both shapes, migrate readers group by group, and retire v1 after lag reaches zero *and* retention has passed.
2. **Use a new schema ID with a reader-of-last-resort.** Where a new topic is impossible, publish the new shape under a new subject version while the final old consumers run a shim that translates — then contract the shim away. Document the shim's expiry date in the PR that adds it, or it becomes permanent.
3. **Version the event, not just the schema.** A `user.created.v2` stream is explicit, greppable, and drainable; a silently-mutating `user.created` subject is archaeology. Reach for new-stream versioning when the semantic contract changes (fields repurposed, not just added).
4. **Plan the mixed-version window explicitly.** State in the migration doc: how long both shapes will be produced, what the rollback is at each stage (which producer version to redeploy, which subject mode to relax), and how reprocessing/replay jobs are handled mid-migration. The replay tooling is often the forgotten consumer — include it in the consumer inventory.
5. **Never rely on "we'll coordinate a shutdown."** The lockstep upgrade that NONE-mode compatibility implies is achievable exactly once per team before someone forgets a cron consumer in a basement service. If the change cannot be made additive, it needs the dual-publish path above, not a calendar invitation.
