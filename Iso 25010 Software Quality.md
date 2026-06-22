> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `Iso 25010 Software Quality.md` in the docs repo.

> Auto-generated from `docs/standards/ISO_25010_SOFTWARE_QUALITY.md` in the docs repo.

---
title: "ISO/IEC 25010:2023 — Software Product Quality Model"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "engineering"
status: "approved"
iso-refs: ["ISO/IEC 25010:2023", "ISO/IEC 25000:2014 (SQuaRE)"]
---

# ISO/IEC 25010:2023 — Software Product Quality Model

## Purpose

This document defines the quality characteristics and subcharacteristics that Beetle Studio measures against, per the ISO/IEC 25010:2023 product quality model (part of the SQuaRE series — Systems and software Quality Requirements and Evaluation).

The 2023 revision expanded from 8 to 9 characteristics, adding Safety and replacing Portability with Flexibility.

## Scope

Applies to:
- Architecture and design decisions
- Code review quality criteria
- Test strategy coverage targets
- Performance benchmarks
- Release readiness assessment
- User experience evaluation

---

## Quality Characteristics (9 total)

### 1. Functional Suitability

The degree to which the product provides functions that meet stated and implied needs when used under specified conditions.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Functional completeness | Degree to which functions cover all specified tasks and user objectives | Feature coverage vs. roadmap |
| Functional correctness | Degree to which a product provides correct results with needed precision | Unit test pass rate, QA regression |
| Functional appropriateness | Degree to which functions facilitate accomplishment of specified tasks | User workflow completion rate |

### 2. Performance Efficiency

Performance relative to the amount of resources used under stated conditions.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Time behaviour | Response and processing times and throughput rates | Frame render time, UI response <16ms |
| Resource utilization | Amounts and types of resources used | GPU/CPU usage during playback |
| Capacity | Maximum limits of a product parameter | Max timeline length, track count |

### 3. Compatibility

Degree to which a product can exchange information with other products and/or perform its required functions while sharing the same environment.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Co-existence | Perform efficiently while sharing environment with other products | No conflicts with other video editors |
| Interoperability | Exchange and use information with other systems | Import/export format support (FORMAT_SUPPORT_MATRIX.md) |

### 4. Interaction Capability (formerly Usability)

Degree to which a product can be used by specified users to achieve specified goals with effectiveness, efficiency, satisfaction, and freedom from risk.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Appropriateness recognizability | Users can recognize whether product is appropriate for needs | First-impression user testing |
| Learnability | Degree to which product enables learning with effectiveness | Time to first successful edit |
| Operability | Attributes that make it easy to operate and control | Keyboard shortcuts, UI responsiveness |
| User error protection | Degree to which product protects users against errors | Undo stack, confirmation dialogs |
| User engagement | Degree to which user interface is pleasing and satisfying | UI polish, animation smoothness |
| Inclusivity | Degree to which product can be used by people with diverse characteristics | WCAG 2.1 AA compliance (ACCESSIBILITY_COMPLIANCE.md) |
| User assistance | Degree to which product provides help when needed | Contextual help, tooltips, FAQ |
| Self-descriptiveness | Degree to which product presents info making it self-explanatory (NEW) | Clear labels, progressive disclosure |

### 5. Reliability

Degree to which a system performs specified functions under specified conditions for a specified period of time.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Faultlessness | Degree to which a system has no faults in its system | Defect density per KLOC |
| Availability | Degree to which a system is operational and accessible | Uptime of cloud sync services |
| Fault tolerance | Degree to which system operates despite faults | Graceful degradation on GPU errors |
| Recoverability | Degree to which product can recover data after failure | Auto-save recovery, crash dump analysis |

### 6. Security

Degree to which a product protects information and data so that persons or systems have the degree of access appropriate to their authorization levels.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Confidentiality | Data accessible only to those authorized | License key protection, encrypted storage |
| Integrity | Prevention of unauthorized data modification | File checksum validation |
| Non-repudiation | Actions can be proven to have taken place | Audit trail for collaborative edits |
| Accountability | Actions traceable to the entity responsible | User action logging |
| Authenticity | Identity of subject/resource can be proved | Code signing, update verification |
| Resistance | Degree to which product sustains operations under attack (NEW) | DDoS protection for cloud services |

### 7. Maintainability

Degree of effectiveness and efficiency with which a product can be modified to improve it, correct it, or adapt it to changes.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Modularity | Degree to which system is composed of discrete components | Module coupling metrics |
| Reusability | Degree to which an asset can be used in more than one system | Shared library usage |
| Analysability | Effectiveness of assessing impact of changes | Code complexity metrics (cyclomatic) |
| Modifiability | Degree to which product can be modified without degradation | Change failure rate |
| Testability | Effectiveness of establishing test criteria | Code coverage percentage |

### 8. Flexibility (replaced Portability in 2023)

Degree to which a product can be adapted for or transferred to other hardware, software, or operational environments.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Adaptability | Degree to which product can be adapted for different environments | Windows version support range |
| Scalability | Degree to which product can handle growing workloads (NEW) | Performance at 4K, 8K resolution |
| Installability | Degree to which product can be installed/uninstalled successfully | Installer success rate |
| Replaceability | Degree to which product can replace another for same purpose | Migration from other editors |

### 9. Safety (NEW in 2023)

Degree to which a product achieves acceptable levels of risk of harm to people, business, software, property, or the environment.

| Subcharacteristic | Definition | Beetle Studio Metric |
|-------------------|-----------|---------------------|
| Operational constraint | Degree to which product constrains its operation to safe parameters | GPU temperature monitoring |
| Risk identification | Degree to which product identifies unsafe situations | Warning on disk space low |
| Fail safe | Degree to which product achieves safe state upon failure | Auto-save before crash |
| Hazard warning | Degree to which product provides warnings of potential hazards | Alert on unsaved work |
| Safe integration | Degree to which product safely integrates with other products (NEW) | Plugin sandboxing |

---

## Quality Measurement Framework

### Metrics Collection

| Characteristic | Tool/Method | Frequency |
|----------------|------------|-----------|
| Functional suitability | Unit tests + integration tests | Every PR |
| Performance efficiency | Benchmark suite (benchmarks.yml) | Every PR touching Engine |
| Compatibility | Format import/export test suite | Weekly |
| Interaction capability | User testing sessions | Per release |
| Reliability | Crash rate telemetry | Continuous |
| Security | Security scan (security-scan.yml) | Every PR |
| Maintainability | Static analysis, complexity metrics | Every PR |
| Flexibility | Multi-platform build matrix | Per release |
| Safety | Risk assessment review | Per release |

### Quality Gates

| Gate | Minimum Threshold | Enforced By |
|------|-------------------|-------------|
| Unit test coverage | >= 70% | pr-build.yml |
| Benchmark regression | < 5% degradation | benchmarks.yml |
| Security findings | 0 Critical, 0 High | security-scan.yml |
| Code complexity | Cyclomatic < 15 per function | Static analysis |
| Build warnings | 0 (warnings-as-errors) | main-build.yml |

---

## References

- [ISO/IEC 25010:2023 (ISO official)](https://www.iso.org/standard/78176.html)
- [arc42 Quality Model (ISO 25010 update 2023)](https://quality.arc42.org/articles/iso-25010-update-2023)
- [PacificCert ISO 25010 Guide](https://blog.pacificcert.com/iso-25010-software-product-quality-model/)
- [Zenodo: 25010:2023 characteristics and definitions](https://zenodo.org/records/14758339)
