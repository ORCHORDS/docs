> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `Iso 9001 Quality Management.md` in the docs repo.

> Auto-generated from `docs/standards/ISO_9001_QUALITY_MANAGEMENT.md` in the docs repo.

---
title: "ISO 9001:2015 — Quality Management System"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "operations"
status: "approved"
iso-refs: ["ISO 9001:2015"]
---

# ISO 9001:2015 — Quality Management System

## Purpose

This document maps ISO 9001:2015 quality management principles and requirements to Beetle Studio's software development processes. ISO 9001 provides a framework for consistently delivering products that meet customer and regulatory requirements.

## Scope

Applies to:
- Software development lifecycle
- Release and delivery processes
- Customer feedback handling
- Continuous improvement processes
- Supplier and dependency management
- Documentation and records management

---

## Seven Quality Management Principles

### 1. Customer Focus

| Principle | Application |
|-----------|------------|
| Understanding customer needs | User research, feature requests via issues |
| Meeting customer requirements | Acceptance criteria on every issue |
| Exceeding customer expectations | Performance beyond minimum specs |
| Measuring customer satisfaction | Beta program feedback (BETA_PROGRAM_GUIDE.md) |

### 2. Leadership

| Principle | Application |
|-----------|------------|
| Establishing unity of purpose | Product roadmap (docs/product/ROADMAP.md) |
| Creating conditions for engagement | Clear roles in BEETLE_STUDIO_TEAM.md |
| Directing and supporting contributors | Onboarding guide, mentoring |
| Recognizing contributions | Changelog attribution |

### 3. Engagement of People

| Principle | Application |
|-----------|------------|
| Competent and empowered people | Skill-matched issue assignment (auto-assign.yml) |
| Recognition and empowerment | Individual developer tokens and attribution |
| Open communication | PR review discussions, issue comments |
| Personal development | Training in new technologies |

### 4. Process Approach

| Principle | Application |
|-----------|------------|
| Managing activities as processes | CI/CD pipeline with defined stages |
| Inputs, activities, outputs defined | Issue → Branch → PR → Review → Merge → Release |
| Process interactions understood | Workflow dependencies documented |
| Risks and opportunities addressed | Security scan, benchmark gates |

### 5. Improvement

| Principle | Application |
|-----------|------------|
| Continual improvement as objective | Retrospectives, metrics tracking |
| Reacting to internal/external changes | Dependency updates, CVE responses |
| Promoting innovation | RFC process (docs/rfc/) |
| Training for improvement | Code review as learning |

### 6. Evidence-Based Decision Making

| Principle | Application |
|-----------|------------|
| Decisions based on data analysis | Benchmark results, crash telemetry |
| Balanced factual and intuitive | Performance data + user feedback |
| Using appropriate methods | Statistical analysis of test results |
| Monitoring measurement capability | CI reliability metrics |

### 7. Relationship Management

| Principle | Application |
|-----------|------------|
| Managing supplier relationships | Third-party library evaluation criteria |
| Optimizing impact on performance | Dependency performance benchmarks |
| Sharing information appropriately | Public docs, internal security docs |
| Recognizing supplier successes | Open-source contribution acknowledgment |

---

## ISO 9001:2015 Clause Mapping

### Clause 4 — Context of the Organization

| Requirement | Implementation |
|-------------|---------------|
| 4.1 Understanding the organization and its context | Market analysis in ROADMAP.md |
| 4.2 Understanding needs of interested parties | User personas, stakeholder map |
| 4.3 Determining scope of QMS | All software lifecycle processes |
| 4.4 QMS and its processes | Documented in CI_CD_PIPELINE.md |

### Clause 5 — Leadership

| Requirement | Implementation |
|-------------|---------------|
| 5.1 Leadership and commitment | CTO sponsors quality initiatives |
| 5.2 Quality policy | "Ship stable, secure, performant software" |
| 5.3 Organizational roles, responsibilities | BEETLE_STUDIO_TEAM.md defines all roles |

### Clause 6 — Planning

| Requirement | Implementation |
|-------------|---------------|
| 6.1 Actions to address risks and opportunities | Risk register, security threat model |
| 6.2 Quality objectives and planning | Release quality gates defined |
| 6.3 Planning of changes | Change management via PR workflow |

### Clause 7 — Support

| Requirement | Implementation |
|-------------|---------------|
| 7.1 Resources | Build infrastructure, developer tools |
| 7.2 Competence | Team skills matrix in config.py |
| 7.3 Awareness | Security training, onboarding guide |
| 7.4 Communication | Issue tracking, PR reviews, wiki |
| 7.5 Documented information | This docs repository |

### Clause 8 — Operation

| Requirement | Implementation |
|-------------|---------------|
| 8.1 Operational planning and control | Sprint planning, issue prioritization |
| 8.2 Requirements for products and services | Issue specs with acceptance criteria |
| 8.3 Design and development | Architecture docs, RFC process |
| 8.4 Control of externally provided processes | Dependency vetting, license checks |
| 8.5 Production and service provision | Build pipeline, release process |
| 8.6 Release of products and services | Release checklist (RELEASE_CHECKLIST.md) |
| 8.7 Control of nonconforming outputs | Bug tracking, rollback procedures |

### Clause 9 — Performance Evaluation

| Requirement | Implementation |
|-------------|---------------|
| 9.1 Monitoring, measurement, analysis, evaluation | CI metrics, benchmark tracking |
| 9.2 Internal audit | Quarterly code quality reviews |
| 9.3 Management review | Monthly product review meetings |

### Clause 10 — Improvement

| Requirement | Implementation |
|-------------|---------------|
| 10.1 General | Continuous improvement culture |
| 10.2 Nonconformity and corrective action | Bug fix process, root cause analysis |
| 10.3 Continual improvement | Retrospectives, tech debt tracking |

---

## PDCA Cycle in Beetle Studio

The Plan-Do-Check-Act cycle maps to the development workflow:

```
PLAN  → Issue created with spec and acceptance criteria
DO    → Developer implements on feature branch
CHECK → PR review, CI builds, security scan, benchmarks
ACT   → Merge to main, release, gather feedback, iterate
```

---

## Records and Documentation Requirements

| Record Type | Retention | Location |
|-------------|-----------|----------|
| Build logs | 90 days | CI system |
| Test results | Per release | CI artifacts |
| Code reviews | Permanent | PR comments |
| Release notes | Permanent | CHANGELOG + releases |
| Security findings | Until resolved + 1 year | Security tracker |
| Customer feedback | 2 years | Issue tracker |

---

## References

- [ISO 9001:2015 (ISO official)](https://www.iso.org/standard/62085.html)
- [ISO 9001:2015 Requirements Summary](https://www.9001council.org/iso-9001-summary.php)
- [7 Quality Management Principles (ETQ)](https://www.etq.com/blog/7-quality-management-principles-under-iso-90012015/)
- [ISO 9001 Clauses Interpretation](https://www.bprhub.com/blogs/interpretation-iso-9001-2015-clauses)
