# CNCF KubeEdge Edge Node Governance

## Purpose

KubeEdge (CNCF Incubating) extends Kubernetes orchestration to edge nodes by running a lightweight EdgeCore agent on edge devices and an EdgeMesh for cross-edge networking. The edge-node governance pattern captures the cloud-edge split (CloudCore + EdgeCore), the offline-tolerance requirements, the deviceTwin / eventBus sync semantics, and the bandwidth and latency constraints of the link between cloud and edge. Without explicit governance, edge workloads behave like cloud workloads and exceed link capacity or fail under intermittent connectivity.

## Current context and source status

KubeEdge 1.16 (released 2024) and KubeEdge 1.18 (released 2025) are the current supported versions. KubeEdge 1.19 entered beta in 2026. The project follows the CNCF Incubating governance model. KubeEdge supports MQTT, EdgeMesh, and EdgeMesh over WebSocket transports.

## Governance pattern

1. Inventory every edge node with EdgeCore version, transport, and link profile.
2. Pin EdgeCore and CloudCore versions in cluster bootstrap.
3. Use `node.kubernetes.io/edge` label to schedule edge workloads exclusively on edge nodes.
4. Configure EdgeCore transport (WebSocket, QUIC, or MQTT) per the link profile.
5. Use deviceTwin and eventBus only when bi-directional sync is required; otherwise use cloud-edge events.
6. Define offline-tolerance policies: workloads must survive intermittent connectivity for the documented period.
7. Monitor edge metrics: `edgecore_sync_total`, `edgecore_eventbus_dropped`, link latency.
8. Alert on edge nodes that fall behind cloud sync beyond the documented SLA.
9. Maintain a documented rollback procedure: drain edge node, upgrade EdgeCore, re-attach.
10. Review edge workload resource limits against link capacity (for example, no remote-pulling of large images during incident).

## Validation and evidence

- EdgeCore and CloudCore versions recorded in cluster inventory.
- Edge node labels verified by `kubectl describe node`.
- Transport configuration documented per link profile.
- Offline-tolerance tested in staging by simulating link outage.
- Edge metrics dashboard deployed.
- Rollback procedure tested in staging.

## Failure correction

Common defects include scheduling cloud-only workloads on edge nodes, missing offline-tolerance testing, and unbounded deviceTwin sync causing edge node OOM. Corrective actions include enforcing edge labels in admission, requiring offline-tolerance test gate, and limiting deviceTwin state size.

## Limitations

- KubeEdge does not extend the Kubernetes control plane fully (for example, Job controller runs in cloud only).
- Edge workloads cannot use cloud-hosted secrets without a sync mechanism.
- Large image pulls over slow links are an anti-pattern.
- EdgeMesh is not a substitute for full service mesh at edge.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (KubeEdge deployment topology), **engineering** (edge workload design), **security** (edge-to-cloud authentication and mTLS), and **templates** (EdgeCore bootstrap template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- KubeEdge documentation (CNCF Incubating): https://kubeedge.io/docs/
- KubeEdge GitHub repository (CNCF Incubating): https://github.com/kubeedge/kubeedge
- KubeEdge architecture overview (CNCF Incubating): https://kubeedge.io/docs/architecture/

Sources were verified on September 1, 2026.