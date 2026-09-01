# ETSI NFV Managed-Service Governance

## Purpose

ETSI's Network Functions Virtualization (NFV) Industry Specification Group publishes the ISG NFV reference architecture, the MANO (Management and Orchestration) framework, and a multi-part set of specifications for virtualized network functions (VNFs) and containerized network functions (CNFs). The architecture is the authoritative baseline for platform teams that operate managed network services — including telco, edge, and 5G core deployments — and for any platform that wants a documented separation of concerns between NFVI, VNF/CNF, MANO, and service assurance.

## Scope

The ETSI NFV architecture addresses NFV Infrastructure (NFVI) — compute, storage, and networking — virtualization/containerization layers, the VNF/CNF workloads, and the MANO stack that orchestrates and manages them. It also addresses service assurance, performance monitoring, and reliability. It is not a control catalog; it pairs with ISO/IEC 27001/27017 and NIST SP 800-53 for security controls.

## Architectural separation

The reference architecture separates concerns into well-defined blocks:

- **NFVI**: physical and virtual resources, including compute, storage, and network.
- **VNF / CNF**: the workloads that deliver the network function.
- **MANO**: NFV Orchestrator (NFVO), VNF Manager (VNFM), and Virtualized Infrastructure Manager (VIM).
- **OSS / BSS**: Operations Support Systems and Business Support Systems for service assurance and commercial operations.
- **Service**: the externally observable capability delivered to the consumer.

Mixing these concerns is a common defect in vendor stacks; the architecture's value is precisely the clean separation.

## Containerization (CNF)

The CNF workstream addresses the migration of workloads from VMs to containers. CNF deployments typically use Kubernetes-class orchestrators and a service mesh. The architecture requires that CNF workloads expose the same lifecycle, configuration, and observability interfaces as VNFs, so that MANO and OSS/BSS do not need separate paths for the two workload types.

## Service assurance

Service assurance covers the lifecycle of a deployed service from a consumer-facing perspective: SLAs, performance metrics, fault detection, and remediation. In the MANO model, service assurance typically draws on metrics from both the NFVI and the workloads themselves; the architecture discourages duplicating metrics in multiple stacks.

## Engineering workflow

1. Map each in-scope service to the architecture's blocks; record the systems and teams responsible for each block.
2. For each block, document the interfaces and the contracts with neighboring blocks.
3. Track which workloads are VNF (VM-based) and which are CNF (container-based); plan convergence to a single workload model where appropriate.
4. Publish a service-assurance view that names the SLAs, the metrics, and the remediation ownership.
5. Re-evaluate when the architecture or the workload model changes.

## Controls and evidence

- Architecture-to-system map with named block owners.
- Interface contract register (for example, VNFM-VIM, VNFM-OSS).
- VNF/CNF inventory with deployment type, version, and lifecycle state.
- Service-assurance catalog with SLAs, metrics, sources, and remediation ownership.
- Change log tied to architecture revisions and workload-type migrations.

## Validation

- Independent reviewer confirms each block has a named owner and a documented interface contract.
- A CNF-onboarding exercise verifies that MANO can manage a CNF as a first-class workload.
- Service-assurance metrics are verified against the SLAs published to consumers.

## Failure modes and corrections

- Conflating VIM and NFVO responsibilities — correct by separating the management plane from the orchestration plane.
- Running separate assurance paths for VNF and CNF — correct by unifying on a service-assurance view keyed to SLAs.
- Letting CNF workloads bypass MANO — correct by routing all lifecycle operations through the orchestrator.
- Skipping interface contracts in favor of implicit integration — correct by publishing and reviewing interface contracts.

## Reference points

The architecture specifies named reference points between functional blocks. These reference points are the contract surface of the architecture: VNF-to-VNF (Vn-Nf), VNFM-to-VNF (Ve-Vnfm), NFVO-to-VNFM (Or-Vnfm), NFVO-to-VIM (Or-Vi), VNFM-to-VIM (Vi-Vnfm), and NFVI-to-VIM (Nf-Vi). Vendors that implement the architecture should publish which reference points they expose and which are internal. A governance review should confirm that the reference points relied on for interoperability are actually implemented and tested, rather than assumed.

## Descriptors

The architecture is descriptor-driven: VNFD (VNF descriptor), CNFD (CNF descriptor), NSD (network service descriptor), and related artifacts declare what is deployed and how it is composed. Descriptors are the equivalent of infrastructure-as-code in the NFV domain, and they deserve the same governance:

- version descriptors in source control;
- review descriptor changes through the standard change process;
- validate descriptors against a schema before deployment; and
- record descriptor provenance and integrity (signing) where the toolchain supports it.

## Limitations

- The architecture is large and complex; small deployments often cannot justify the full MANO stack.
- Some interop details (for example, specific reference points) evolve across specification versions.
- It does not specify how to migrate a legacy physical network function into VNF/CNF form.
- It does not address edge computing topologies that span operators; multi-domain federation requires adjacent ETSI work.

## Canonical sources

- ETSI ISG NFV (ETSI, primary authority) — Architectural Framework specification: https://www.etsi.org/deliver/etsi_gs/NFV/001_099/002/
- ETSI ISG NFV (ETSI, primary authority) — Management and Orchestration specification: https://www.etsi.org/deliver/etsi_gs/NFV/001_099/006/

## Scope note

This article summarizes project-neutral architecture guidance from ETSI ISG NFV. It does not claim that any specific deployment implements the full MANO stack or follows any particular ETSI specification version.