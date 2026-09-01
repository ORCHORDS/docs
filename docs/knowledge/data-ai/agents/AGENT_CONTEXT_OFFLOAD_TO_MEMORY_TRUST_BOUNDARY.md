# Context Offload to Memory: Trust Boundary Under the MCP Memory Extension

## Scope

When an agent runs out of context, it offloads. Memory stores absorb the overflow as summaries, embeddings, structured facts, and references, and the agent reads back from those stores when relevant. The transfer is a trust boundary: any content the agent ever ingested is a candidate for what gets written to memory, and any retrieval that brings memory contents back into the model context re-introduces that content as if it were authoritative.

The MCP Memory extension provides the protocol vocabulary for memory reads, writes, scoping, and revocation. The vocabulary does not, on its own, prevent the writing of poisoned facts or the uncritical reading of stale or hostile entries. This article covers the trust discipline around memory that complements the protocol without claiming to replace it.

## Workflow or implementation guidance

1. Treat memory as a write-once-confirm-many store. Every entry should carry its source provenance at write time: which run, which prompt revision, which tool produced the fact, and what confidence the writing component assigned. Memory without provenance cannot be safely re-weighted later.
2. Classify memory entries by sensitivity and trust at write time, not at read time. Read-time classification is too late: by then the entry is already in the model context. The classification should drive whether the entry is eligible for automatic inclusion, requires explicit confirmation, or is excluded from certain contexts.
3. Restrict automatic memory inclusion to entries the agent itself authored under defined conditions. Memory written by the user or by an external system must go through a confirmation flow before it can shape model output. The default for untrusted memory is silence.
4. Apply expiry and staleness rules. Memory about the world, about the user's environment, or about the user themselves decays. Carry an explicit lifetime, and treat an expired entry as missing rather than as still authoritative. A long-lived memory that turned wrong is worse than a short memory that ended.
5. Scope memory by tenant, identity, and purpose. A memory entry for tenant A must not be readable by tenant B under any operational path, including through prompts or tool arguments. Memory scopes are authorization scopes, not metadata tags.
6. Record memory reads the same way other privileged reads are recorded: who read what, when, with what authorization decision, and what was returned. Memory audit trails make injection attempts investigable and make retention review possible.
7. Provide revocation as a first-class operation. When a fact is known to be wrong, when a tenant leaves, or when an entry is discovered to be hostile, the entry must be revocable such that future reads cannot return it. Tombstoning and search-time filtering are both acceptable as long as the operational property holds.
8. Avoid memory writes from prompt content that the agent has not classified. A model may write to memory as a tool call, but the call must be authorized and validated like any other privileged action. Memory is a side-effecting resource, not a passive log.

## Controls

Memory storage should be encrypted at rest, with key management aligned to the most sensitive content the store holds. Where memory carries tenant-confidential content, segregate storage per tenant or per sensitivity tier. Encryption keys bound to broad operational roles weaken the protection; bind keys narrowly.

Search and retrieval paths must enforce the same authorization as the underlying records. An embedding-based search that returns records the caller is not authorized to read - even if the vector match was strong - violates the boundary. Score-time filtering is necessary when result sets are produced by similarity rather than by identifier.

Quota and rate controls on memory are dual-purpose. They prevent runaway growth, which is itself a security property when the store can be poisoned at scale, and they ensure that an attacker cannot exhaust the storage to evict legitimate entries. Quota exceptions must be logged and reviewable.

## Validation evidence

Demonstrate provenance. A memory entry written under a defined source is readable with the provenance attached, and a downstream consumer can reason about reliability from that provenance. Show that an entry written without provenance is rejected or quarantined rather than accepted as authoritative.

Demonstrate scope. A tenant-A read returns no tenant-B entries under any input perturbation. Show that an attempt to read across scope via a crafted query is refused with a distinct error. Show that memory scope survives reconfiguration of the underlying storage and is not merely a metadata check that can be bypassed.

Demonstrate revocation. After revocation, a known identifier returns no record, a known embedding no longer matches against the revoked record, and an audit entry records the revocation event with actor and reason. Demonstrate that expiry applies at read time even when the underlying record still exists, and that the read returns nothing authoritative.

## Failure modes and correction

The dominant failure is silent memory poisoning, where a hostile entry shapes subsequent agent behavior without ever being inspected. Correct by restricting automatic inclusion to entries that satisfy strict provenance and trust checks, and by surfacing memory contents to the user or operator when an entry materially influences an action.

A second failure is memory without expiry. Entries written under conditions that no longer apply remain in the model context, sometimes producing hallucinated reasoning that the operator cannot trace. Correct by enforcing lifetimes at write time and reviewing long-lived entries for continued applicability.

A subtler failure is search-time authorization bypass. A vector store returns near-neighbors regardless of who asked, and the application filters after the fact. Correct by enforcing scope before the result set is produced, and by testing retrieval behavior with both legitimate and illegitimate inputs.

## Limitations

Memory trust discipline is not a substitute for input validation; an entry written by a hostile tool call remains a hostile entry, however well classified. Vector search introduces fuzzy boundaries that strict authorization regimes cannot perfectly express. Memory also raises retention obligations that may not align cleanly with personal-data deletion rights, requiring additional governance rather than technical controls alone. The MCP Memory extension is a protocol, not a policy; useful memory requires policy on top of it.

## Canonical sources

- **Model Context Protocol, Extensions overview:** https://modelcontextprotocol.io/extensions/overview
- **Model Context Protocol, specification index:** https://modelcontextprotocol.io/specification/2025-11-25
- **OWASP Cheat Sheet Series, Secrets Management (handling for memory-embedded credentials):** https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
