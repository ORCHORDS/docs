# Leader Election Consensus Raft Etcd

## Scope

This article addresses leader election as a special case of distributed consensus, with a focus on the Raft consensus algorithm and its reference implementation in etcd. It explains the role of leader election in a distributed system, the guarantees Raft provides, the mechanism by which Raft elects a leader, and the practical implications for systems that depend on Raft. The discussion covers the Raft paper, the etcd implementation, the relationship between leader election and log replication, and the trade-offs of running Raft under varying conditions. The article applies to any system that uses Raft for consensus, including Kubernetes (via etcd), CockroachDB, Consul, and Cloudflare Durable Objects (which provide a single-writer primitive that solves a subset of the leader-election problem).

## Workflow or implementation guidance

A distributed system often needs to designate one process as the coordinator for some shared resource: the primary of a database, the leader of a worker pool, the master of a cluster. The designation must be unique: at most one leader at any moment. The designation must also be durable: if the leader fails, another leader is elected without manual intervention. The combination of uniqueness and durability is exactly what a consensus algorithm provides.

Raft is a consensus algorithm designed for understandability. It decomposes the consensus problem into three sub-problems: leader election, log replication, and safety. A Raft cluster has one leader at any time; all client requests go through the leader, and the leader replicates each request as a log entry to the followers. A majority of the cluster must acknowledge the log entry before the leader applies it to the state machine and responds to the client. The leader's authority is therefore backed by the same majority that backs the log.

Leader election in Raft is triggered when a follower times out waiting for a heartbeat from the leader. The follower increments its term, transitions to candidate state, votes for itself, and sends RequestVote RPCs to the other peers. A candidate becomes leader if it receives votes from a majority of the cluster. If no candidate wins a majority in a term, the term ends without a leader, and a new election begins with longer randomised timeouts. The randomisation prevents split votes; the timeouts ensure that an election eventually succeeds.

etcd is the reference implementation of Raft used in production at scale. It exposes a key-value store with strong consistency: every read sees a recent write, and every write is acknowledged by a majority before it is returned. The leader is the writer; the followers receive the leader's writes via Raft log replication. Reading from a follower requires a "read index" call to the leader to ensure that the follower is not stale.

The first step in using Raft (directly or via etcd) is to understand the failure modes: a network partition can cause two leaders to be elected (one in each partition's majority), but only one of them can commit writes, and the other will step down when the partition heals. The second step is to design the cluster size. Three or five nodes are typical; an even number does not add fault tolerance and should be avoided. The third step is to design the timeout. A timeout that is too short causes spurious elections; a timeout that is too long delays recovery. The fourth step is to plan for log compaction. The Raft log grows with every committed entry; periodic snapshots allow old entries to be discarded.

For systems that do not need full Raft but only need a single-writer, simpler primitives exist. Cloudflare Durable Objects provide single-writer semantics by design: only one execution context runs at a time inside a Durable Object, and the runtime guarantees serialised access. This is sufficient for many leader-election use cases (a single writer for a queue, a single coordinator for a workflow) without the operational cost of running a Raft cluster.

## Controls

Raft controls cover cluster membership, log compaction, and observability. Cluster membership changes must be made carefully: adding or removing a node changes the majority calculation, and a mid-flight change can split the cluster's quorum. The standard approach is the joint consensus algorithm, which allows the old and new configurations to coexist during the transition. Log compaction must be triggered before the log grows too large; otherwise, a new node joining the cluster cannot catch up. Observability must include term number, log index, commit index, and the state of each peer; without these, leader flapping or log divergence cannot be diagnosed.

In etcd specifically, controls include the WAL (write-ahead log) durability setting, the snapshot frequency, the heartbeat interval, and the election timeout. Each of these has a documented default, but the defaults are tuned for the typical Kubernetes use case and may need adjustment for other workloads.

## Validation evidence

Validation must prove that the cluster tolerates the loss of a minority of nodes. A standard test kills one node, observes that the cluster continues to serve, and then brings the node back and verifies that it catches up. A more demanding test kills a majority's worth of nodes and verifies that the cluster correctly stops accepting writes (because no quorum is available). A yet more demanding test partitions the network and verifies that at most one partition elects a leader and that the other partition steps down when the partition heals.

Validation must also prove that the leader election itself is timely. The test kills the leader and measures the time until a new leader is elected; this time must be within the SLO. Validation must also prove that the log is not lost. The test crashes the leader immediately after it has acknowledged a write but before it has replicated; on restart, the cluster must either commit or roll back the write consistently.

## Failure modes and correction

The dominant failure is split brain caused by a network partition. Two partitions each believe they have a majority and elect their own leader. The cure is Raft's term mechanism: the partition with the higher term will reject stale leaders when the partition heals. A second failure is the leader election thrashing. The timeouts are too short, and the cluster keeps triggering elections. The cure is to increase the timeout and to randomise it.

A third failure is disk corruption. The leader's WAL is corrupted, and the leader crashes. The cure is to monitor WAL integrity and to have a documented recovery procedure that includes re-snapshotting from the followers. A fourth failure is slow followers. A follower is slow to acknowledge, and the leader's commits are delayed. The cure is to monitor per-follower lag and to remove chronically slow followers from the cluster.

A fifth failure is the cluster being too small. A three-node cluster loses one node and continues; loses a second node and stops. If the workload requires surviving two failures, the cluster must have five nodes. The cure is to size the cluster for the failure tolerance the workload requires.

## Limitations

Raft is not a free lunch. Running a Raft cluster adds operational overhead: the cluster must be deployed, monitored, patched, and recovered. Every write goes through the leader and is acknowledged by a majority, so write latency is the round-trip time to the majority. Raft is also a consensus algorithm; it does not solve the problem of the application being able to tolerate split brain at the application level. The application must still be designed against the case of temporary unavailability of the leader. For systems that only need a single writer and can tolerate the rest of the cluster being unable to make progress during a partition, simpler primitives (Durable Objects, ZooKeeper's ZAB, Redis Sentinel) are sufficient.

## Canonical sources

- Diego Ongaro — *Consensus: Bridging Theory and Practice* (PhD thesis, Stanford 2014), the canonical Raft reference, with leader election, log replication, and joint consensus: https://raft.github.io/raft.pdf
- Diego Ongaro and John Ousterhout — *In Search of an Understandable Consensus Algorithm* (USENIX ATC 2014), the original Raft paper
- etcd project documentation and *etcd: A reliable distributed key-value store* design document, including the maintainer's design notes on learner nodes and Raft implementation: https://etcd.io/
- HashiCorp Consul and CockroachDB documentation, secondary references for production Raft deployments and the operational concerns that follow from them
