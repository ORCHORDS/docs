# Agent Memory Poisoning Detection

Long-term memory turns an agent into a slower learner with a longer memory of attacks. An adversary who gets one hostile instruction stored as a "user preference" or "learned fact" gets it replayed into context on every future session, long after the original conversation is gone. Poisoning is cheap to attempt: a document the agent summarizes, a form field, a message the agent is told to remember. Detection is about provenance and corroboration at write time, plausibility scoring at read time, and a rollback path that actually works. This article covers all three, plus the forensic loop.

## Scope

Applies to agent systems with persistent memory stores: user-preference records, episodic summaries, vector-indexed documents, and learned-procedure notes. Covers write-path provenance capture, corroboration rules, read-path risk scoring, detection response, and rollback. Does not cover vector-store hardening generally, prompt-injection filtering of live tool results, or RBAC on the memory service, which are complementary controls assumed to exist.

## Workflow or implementation guidance

1. Structure memory as typed records, never free text blobs. Each record carries: content, record type (fact, preference, procedure, episodic summary), subject (whose memory namespace it belongs to), provenance (source channel, conversation ID, tool that produced it), confidence, creation and last-corroborated timestamps, and a content hash.
2. Capture provenance at the moment of writing, not reconstructed later. The write path knows whether the content came from a direct user statement, a tool result, a summarized document, or the agent's own inference. Record that channel, and record the upstream digest when the source was external content. Inference-derived records are marked as such; they corroborate nothing by themselves.
3. Route all writes through one gate that enforces classification rules: preference writes require an explicit user statement in-channel, not an inference from behavior; fact writes about third parties or systems require a tool-verified source; procedure writes (how to do things) are quarantined to a higher review tier because they directly steer future actions.
4. Apply corroboration thresholds at write time. A fact accepted from untrusted content (a fetched page, an email body) starts in a pending state and only becomes active after an independent source agrees, with "independent" meaning a different origin, not two passages from the same fetch. Preferences from a single ambiguous statement stay low-confidence until reaffirmed.
5. Score risk at read time, because that is where poison acts. Before a retrieved record enters context, compute a risk score from: source channel trustworthiness, corroboration count and independence, age since last corroboration, whether the record touches sensitive action domains (payments, credentials, access, communication on the user's behalf), and anomaly versus neighboring records for the same subject.
6. Gate high-risk reads. Records above a risk threshold that also touch sensitive domains require either user confirmation inline ("I remember you prefer X, from a document on 2026-08-02, apply?") or exclusion from the action, depending on the deployment's latency budget. Never let a low-provenance record silently drive a sensitive action.
7. Detect poisoning patterns continuously: sudden clusters of writes from one source channel, procedure records whose content matches known injection phrasings, preference flips that contradict a long stable history, and records whose content hashes match entries seen poisoned at other tenants.
8. Define the response ladder: quarantine the suspect record (readable by auditors, excluded from retrieval), alert the subject's owner, run a similarity sweep for sibling records from the same provenance event, and roll back.
9. Test rollback for real: memory is append-mostly with periodic snapshots, so quarantine plus snapshot restore can remove a poisoning event and everything after it. Rehearse the restore quarterly; an untested rollback is a rumor.

## Controls

- Memory namespace isolation per user and per principal, enforced by the read path as well as the write path, so poison cannot cross subjects.
- Write-rate ceilings per source and per conversation, because mass poisoning is loud when rate-limited.
- Injection-signature screening on memory writes, keyed off the same patterns used for tool-result filtering, tuned to warn rather than block so legitimate content is not lost.
- Immutable audit log of every write and read decision with record ID, provenance, risk score, and the policy version that decided.
- Retention and decay rules: uncorroborated records expire on a schedule; sensitive-domain records require periodic reaffirmation or lapse.

## Validation evidence

- Poisoning drill set: injected instructions hidden in summarized documents, preference statements fabricated via inference, and procedure records disguised as helpful notes. Each fixture must end quarantined or gated, with the triggering signal documented.
- Corroboration test: the same false fact sourced twice from one origin stays pending; sourced from two distinct origins it activates, proving the independence rule works as specified.
- Read-gate evidence: traces showing a high-risk record being surfaced with attribution and confirmation rather than silently applied, and exclusion paths when confirmation is denied.
- Rollback rehearsal report: time to quarantine, time to restore from snapshot, and verification that restored state contains no descendant records of the poisoned write.
- Detection telemetry: alert counts by pattern family over a quarter, with confirmed-true versus false-positive breakdown.

## Failure modes and correction

- Poison arrives through a channel the provenance model labels trusted, such as a compromised integration whose outputs inherit the integration's trust level. Correction: re-baseline channel trust when an integration's own security posture changes; trust attaches to evidence, not to brand.
- Corroboration is satisfied by two aliases of one source. Correction: independence is computed over origin identity, including redirect chains and ownership, not over superficial URLs.
- Read-time scoring adds latency and gets bypassed "temporarily" during an outage. Correction: the bypass is a break-glass action, logged and time-boxed, and sensitive-domain gating never takes the bypass.
- Quarantine quietly degrades recall as pending records accumulate, and someone flushes them all to active to fix search quality. Correction: pending-capacity metrics and a review queue, so activation is a human decision per record or per source, not bulk.

## Limitations

Detection is probabilistic; sophisticated poison phrased as plausible user preference passes read-time scoring, which is why sensitive actions need independent confirmation regardless of memory confidence. Provenance quality depends on the write path staying honest, so a bug in one integration corrupts labels wholesale. Cross-tenant detection only works where deployment topology allows it, and multi-tenant isolation boundaries limit shared signatures. Finally, aggressive quarantine trades recall for safety, and the right dial position depends on how costly false negatives are in the specific deployment, not on any universal constant.

## Canonical sources

- OWASP, LLM Top 10 for LLM Applications (LLM08 Supply Chain and memory/vector-store risks): https://genai.owasp.org/llm-top-10/
- NIST AI 100-2, A Taxonomy and Terminology of Adversarial Machine Learning: https://nvlpubs.nist.gov/nistpubs/ir/2024/NIST.AI.100-2e2023.pdf
- NIST SP 800-61 Rev. 2, Computer Security Incident Handling Guide: https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r2.pdf
