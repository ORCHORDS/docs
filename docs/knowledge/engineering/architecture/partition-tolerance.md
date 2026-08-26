# partition-tolerance

**Issue:** Understanding and designing for network partition scenarios
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams assume network failures are rare and skip partition-handling logic, leading to split-brain scenarios.

## Pattern / Solution
A network partition is when nodes cannot communicate. The system must decide: reject requests (CP) or serve potentially stale data (AP).

Split-brain prevention:
- Quorum: require majority of nodes to agree before accepting writes
- Leader election via Raft or Paxos
- Fencing tokens: monotonically increasing token; old leaders cannot write

```
Normal:  [Node A] ←→ [Node B] ←→ [Node C]
Partition: [Node A] | [Node B] ←→ [Node C]
           minority     majority (quorum)
```

With quorum of 2/3: Node A stops accepting writes. Nodes B+C continue. On heal, A syncs.

## Gotchas
- Quorum size affects availability; smaller quorum = higher availability but weaker consistency
- Fencing tokens must be validated by storage layer, not just by the lock service
- Partial partitions (asymmetric routing) are harder to detect than full splits

## Related
- `cap-theorem-explained.md`
- `distributed-lock-design.md`
- `two-generals-problem.md`
