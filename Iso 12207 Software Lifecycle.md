> Auto-generated from `Iso 12207 Software Lifecycle.md` in the docs repo.

> Auto-generated from `Iso 12207 Software Lifecycle.md` in the docs repo.

> Auto-generated from `Iso 12207 Software Lifecycle.md` in the docs repo.

> Auto-generated from `Iso 12207 Software Lifecycle.md` in the docs repo.

> Auto-generated from `Iso 12207 Software Lifecycle.md` in the docs repo.

> Auto-generated from `docs/standards/ISO_12207_SOFTWARE_LIFECYCLE.md` in the docs repo.

---
title: "ISO/IEC/IEEE 12207:2017 — Software Life Cycle Processes"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "engineering"
status: "approved"
iso-refs: ["ISO/IEC/IEEE 12207:2017", "ISO/IEC/IEEE 15288:2023"]
---

# ISO/IEC/IEEE 12207:2017 — Software Life Cycle Processes

## Purpose

This document maps ISO/IEC/IEEE 12207:2017 software life cycle processes to Beetle Studio's development workflow. The standard defines 30+ processes organized into 4 groups covering the entire software lifecycle from conception through retirement.

## Scope

Applies to:
- All phases of Beetle Studio development
- Acquisition of third-party components
- Supply/distribution of releases
- Operation and maintenance post-release
- Eventual end-of-life/retirement

---

## Process Group Structure

ISO/IEC/IEEE 12207:2017 organizes processes into four groups:

| Group | Purpose | Process Count |
|-------|---------|---------------|
| Agreement | Establish contracts between acquirer and supplier | 2 |
| Organizational Project-Enabling | Provide infrastructure and resources | 5 |
| Technical Management | Manage the technical effort | 7 |
| Technical | Execute development/maintenance work | 16+ |

---

## Agreement Processes

### Acquisition Process

| Activity | Beetle Studio Implementation |
|----------|------------------------------|
| Prepare acquisition | Evaluate third-party libraries (FFmpeg, DirectX SDK) |
| Advertise acquisition | Identify candidate dependencies |
| Select supplier | Compare libraries on license, performance, maintenance |
| Establish agreement | Accept license terms (MIT, LGPL, proprietary) |
| Monitor agreement | Track dependency updates and EOL notices |

### Supply Process

| Activity | Beetle Studio Implementation |
|----------|------------------------------|
| Prepare response | Define release package contents |
| Establish agreement | Publish license terms |
| Execute supply | Build and publish releases (release-build.yml) |
| Deliver product | Windows Store, direct download |

---

## Organizational Project-Enabling Processes

### Life Cycle Model Management

| Activity | Implementation |
|----------|---------------|
| Establish life cycle model | Agile with CI/CD gates |
| Assess life cycle models | Quarterly process review |

### Infrastructure Management

| Activity | Implementation |
|----------|---------------|
| Establish infrastructure | Forgejo, Docker runners, build servers |
| Maintain infrastructure | Infrastructure monitoring (INFRASTRUCTURE_OVERVIEW.md) |

### Portfolio Management

| Activity | Implementation |
|----------|---------------|
| Qualify opportunities | Feature requests evaluated against PRIORITY_FRAMEWORK.md |
| Balance portfolio | Resource allocation across features/bugs/tech-debt |

### Human Resource Management

| Activity | Implementation |
|----------|---------------|
| Identify skills needed | Team skills matrix |
| Develop skills | Training, pair programming |
| Acquire and provide resources | Role-based team assignment (auto-assign.yml) |

### Quality Management

| Activity | Implementation |
|----------|---------------|
| Plan quality management | Quality gates in CI pipeline |
| Assess quality | Metrics: test coverage, defect density, benchmark results |
| Perform corrective action | Bug fix cycle, retrospectives |

---

## Technical Management Processes

### Project Planning

| Activity | Implementation |
|----------|---------------|
| Define project | Issue creation with scope, acceptance criteria |
| Plan project | Sprint planning, roadmap milestones |
| Activate project | Branch creation, resource assignment |

### Project Assessment and Control

| Activity | Implementation |
|----------|---------------|
| Assess project | PR review status, CI pass rates |
| Control project | Priority re-evaluation, scope adjustment |
| Manage risks | Security scan findings, performance regressions |

### Decision Management

| Activity | Implementation |
|----------|---------------|
| Prepare decisions | RFC proposals (docs/rfc/) |
| Analyze decision | Technical trade-off analysis |
| Make and manage decisions | Architecture Decision Records |

### Risk Management

| Activity | Implementation |
|----------|---------------|
| Plan risk management | Threat model, risk register |
| Manage risks | Security controls (ISO 27001 mapping) |
| Monitor risks | Continuous security scanning |

### Configuration Management

| Activity | Implementation |
|----------|---------------|
| Plan configuration management | Branching strategy (BRANCHING_STRATEGY.md) |
| Perform configuration identification | Git tags, SWID tags |
| Perform configuration change management | PR workflow with review |
| Perform configuration status accounting | Release history, changelog |
| Perform configuration evaluation | Release checklist verification |

### Information Management

| Activity | Implementation |
|----------|---------------|
| Plan information management | Documentation structure (this repo) |
| Perform information management | Automated doc generation, wiki updates |

### Measurement

| Activity | Implementation |
|----------|---------------|
| Plan measurement | Define KPIs (build time, test coverage, defect rate) |
| Perform measurement | CI collects metrics automatically |
| Evaluate measurement | Trend analysis, benchmark comparisons |

---

## Technical Processes

### Business/Mission Analysis

| Activity | Implementation |
|----------|---------------|
| Define problem space | Market research, user needs analysis |
| Characterize solution space | Feature feasibility assessment |

### Stakeholder Needs and Requirements Definition

| Activity | Implementation |
|----------|---------------|
| Elicit stakeholder needs | User research, beta feedback |
| Define requirements | Issue specs with acceptance criteria |
| Analyze requirements | Technical feasibility review |

### System/Software Requirements Analysis

| Activity | Implementation |
|----------|---------------|
| Define requirements | Detailed specs in docs/engineering/ISSUE_*_SPEC.md |
| Analyze requirements | Cross-reference with architecture |
| Manage requirements | Issue tracker state management |

### Architecture Definition

| Activity | Implementation |
|----------|---------------|
| Define architecture | ARCHITECTURE_OVERVIEW.md, MODULE_MAP.md |
| Analyze architecture | Performance modeling, dependency analysis |
| Synthesize solution | Design documents, RFCs |

### Design Definition

| Activity | Implementation |
|----------|---------------|
| Design components | Header/implementation file design |
| Manage design | Code review on architectural changes |

### Implementation

| Activity | Implementation |
|----------|---------------|
| Implement design | C++ coding, shader development |
| Manage implementation | Feature branches, CI validation |

### Integration

| Activity | Implementation |
|----------|---------------|
| Integrate components | PR merge to main branch |
| Manage integration | Merge conflict resolution, build verification |

### Verification

| Activity | Implementation |
|----------|---------------|
| Verify requirements met | Unit tests, integration tests (TEST_STRATEGY.md) |
| Manage verification | CI test suite execution (pr-build.yml) |

### Transition

| Activity | Implementation |
|----------|---------------|
| Package for delivery | Installer build (release-build.yml) |
| Install product | Inno Setup / MSIX deployment |
| Train users | User guide, quick start documentation |

### Validation

| Activity | Implementation |
|----------|---------------|
| Validate against stakeholder needs | Beta testing (BETA_PROGRAM_GUIDE.md) |
| Manage validation | User acceptance testing |

### Operation

| Activity | Implementation |
|----------|---------------|
| Operate product | End-user runs application |
| Manage operations | Crash reporting, telemetry |
| Support customers | FAQ, troubleshooting guide |

### Maintenance

| Activity | Implementation |
|----------|---------------|
| Manage maintenance requests | Bug reports via issue tracker |
| Implement modifications | Patch development cycle |
| Migrate/retire system | End-of-life planning |

### Disposal

| Activity | Implementation |
|----------|---------------|
| Plan disposal | EOL announcement timeline |
| Execute disposal | Final release, data export tools |

---

## Process Relationships to CI/CD

```
Issue Created
    |
    v
[Stakeholder Needs] --> [Requirements Analysis] --> [Design]
    |                                                    |
    v                                                    v
[Implementation] --> [Integration (PR)] --> [Verification (CI)]
    |                                              |
    v                                              v
[Validation (Beta)] --> [Transition (Release)] --> [Operation]
    |                                                    |
    v                                                    v
[Maintenance (Patches)] <---------- [Disposal (EOL)]
```

---

## References

- [ISO/IEC/IEEE 12207:2017 (ISO official)](https://www.iso.org/standard/63712.html)
- [ISO/IEC 12207 Wikipedia](https://en.wikipedia.org/wiki/ISO/IEC_12207)
- [arc42 Quality Model: ISO 12207](https://quality.arc42.org/standards/iso12207)
- [IEEE Xplore: 12207-2017](https://ieeexplore.ieee.org/document/8100771)
- [PacificCert ISO/IEC/IEEE 12207 Guide](https://pacificcert.com/iso-iec-ieee-12207-2017-systems-software-engineering/)
