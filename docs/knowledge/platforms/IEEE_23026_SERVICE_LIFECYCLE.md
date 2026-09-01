# IEEE 23026 Service Lifecycle

## Purpose

IEEE 23026-2023, "Standard for Service Life Cycle Implications for Software Systems," codifies a service lifecycle model that connects software product development, deployment, operations, and retirement to the consumer-facing service. It is the authoritative baseline when an organization needs a shared vocabulary for who owns the service (vs. the software that delivers it), how transitions are governed, and how retirement is planned.

## Scope

The standard addresses the full service lifecycle: concept, development, deployment, operations, improvement, and retirement. It applies whether the service is delivered by on-premise software, a managed cloud service, or a hybrid topology. It does not specify software-development methodology (that is the domain of ISO/IEC/IEEE 12207) and does not specify product quality attributes (that is the domain of ISO/IEC 25010).

## Service vs. software

The standard makes a deliberate distinction:

- **Software**: a product that delivers capabilities to operators or developers.
- **Service**: a consumer-facing capability that is delivered continuously, governed by SLAs, and operated as an ongoing concern.

The two are linked: a service is typically delivered by software, but the service has its own lifecycle. Operating the service continues after the software is released; retiring the service is not the same as retiring the software.

## Lifecycle stages

The standard organizes the lifecycle into stages with explicit transitions. The transitions — not the stages — are where governance and approval live.

- **Service concept**: identification of a consumer need and a value proposition.
- **Service development**: design and implementation of the software and the operational capability that will deliver the service.
- **Service deployment**: onboarding the service into the operating environment, including acceptance testing, training, and cutover.
- **Service operation**: day-to-day operation, including monitoring, incident management, capacity management, and consumer support.
- **Service improvement**: continuous improvement informed by consumer feedback, operational metrics, and incident trends.
- **Service retirement**: end-of-life planning, consumer migration, and decommissioning.

## Roles and responsibilities

The standard recommends explicit role assignment. Common roles include:

- **Service owner**: accountable for the service end to end, including consumer outcomes and lifecycle transitions.
- **Service manager**: day-to-day management of operations and improvement.
- **Development owner**: accountable for the software that delivers the service.
- **Operations owner**: accountable for the runtime platform and incident management.
- **Consumer owner**: accountable for representing consumer needs during concept, improvement, and retirement.
- **Security and compliance owner**: accountable for controls applicable to the service.

Single-role-per-service is common but not required; what matters is that the responsibilities are assigned, not implied.

## Engineering workflow

1. For each in-scope service, name the service owner and document the role assignment.
2. For each lifecycle stage, name the entry and exit criteria, the artifacts required to move between stages, and the approver.
3. Publish the service catalog with the stage, owner, SLAs, and retirement plan for every service.
4. Operate a backplane that records lifecycle transitions and the approvals behind them.
5. Review the service catalog at least annually and after every material change.

## Controls and evidence

- Service catalog with named owners, stage, SLAs, and retirement status.
- Lifecycle transition log with entry/exit artifacts and approver names.
- Retirement plans with consumer-migration paths and decommissioning timelines.
- Role-assignment matrix with backups for each named role.
- Annual review record signed by service owners.

## Validation

- Independent reviewer confirms each service has a named owner and a current stage.
- Lifecycle transitions are sampled and verified against the backplane.
- Retirement plans are exercised at least once per year, ideally against a low-risk service.

## Failure modes and corrections

- Treating the service catalog as a software inventory — correct by adding consumer-facing fields: SLAs, retirement plans, and consumer owners.
- Letting transitions happen informally — correct by requiring entry/exit artifacts and named approvers.
- Conflating software retirement with service retirement — correct by separating the two lifecycles and planning consumer migration separately.
- Allowing single-owner single-team services to skip the retirement plan — correct by requiring a retirement plan for every service regardless of team size.

## Limitations

- The standard is a lifecycle model, not a methodology; teams still choose agile, waterfall, or hybrid.
- It does not prescribe specific tooling for the service catalog or the lifecycle backplane.
- It does not, by itself, define SLAs or service-assurance metrics; those come from the service discipline and the consumer contract.
- It is most valuable in organizations with multiple services and stable ownership; small teams may legitimately run a lightweight variant.

## Canonical sources

- IEEE 23026-2023 (IEEE, primary authority) — Standard for Service Life Cycle Implications for Software Systems: https://standards.ieee.org/ieee/23026/7234/
- ISO/IEC/IEEE 12207:2017 (ISO/IEC/IEEE, primary authority) — Systems and software engineering — Software life cycle processes: https://www.iso.org/standard/63712.html

## Scope note

This article summarizes project-neutral use of IEEE 23026-2023 alongside ISO/IEC/IEEE 12207. It does not claim that any specific organization has adopted the standard or that any specific service is compliant with it.