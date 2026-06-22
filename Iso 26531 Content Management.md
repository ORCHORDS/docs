> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `Iso 26531 Content Management.md` in the docs repo.

> Auto-generated from `docs/standards/ISO_26531_CONTENT_MANAGEMENT.md` in the docs repo.

---
title: "ISO/IEC/IEEE 26531:2023 — Content Management for Documentation"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "documentation"
status: "approved"
iso-refs: ["ISO/IEC/IEEE 26531:2023", "ISO/IEC/IEEE 15289:2019"]
---

# ISO/IEC/IEEE 26531:2023 — Content Management for Product Life Cycle Documentation

## Purpose

This document defines content management requirements for Beetle Studio's documentation system, based on ISO/IEC/IEEE 26531:2023. The standard specifies requirements for managing content used in product life cycle, software, and service management documentation.

## Scope

Applies to:
- All documentation in this repository (beetle-studio/docs)
- Wiki content
- User-facing help content
- API documentation
- Release notes and changelogs
- Internal engineering documentation

---

## Content Management Principles

### Component Content Management System (CCMS)

ISO/IEC/IEEE 26531 distinguishes between:
- **Document Management System (DMS)**: Manages complete documents as units
- **Component Content Management System (CCMS)**: Manages reusable content objects below the document level

Beetle Studio uses a **Git-based CCMS** where:
- Content objects = individual Markdown files
- Version control = Git history
- Collaboration = Pull request workflow
- Publication = Static site generation / Forgejo rendering

### Key Capabilities Required

| Capability | Implementation |
|-----------|---------------|
| Storage and retrieval of content objects | Git repository (beetle-studio/docs) |
| Content revision tracking | Git commit history |
| Content audit trail | Git blame, PR review history |
| Collaborative environment | Forgejo PRs, issue discussions |
| Content reuse across deliverables | Shared Markdown includes, cross-references |
| Multiple deliverable formats | Markdown renders to HTML, PDF export possible |

---

## Content Object Structure

### Metadata Requirements (Frontmatter)

Every content object (document) MUST include standardized metadata:

```yaml
---
title: "Document Title"
version: "1.0.0"
last-updated: "YYYY-MM-DD"      # ISO 8601
owner: "team-or-person"
status: "draft|review|approved|deprecated"
iso-refs: ["relevant standards"]
---
```

### Content Object Lifecycle States

| Status | Definition | Allowed Actions |
|--------|-----------|-----------------|
| draft | Work in progress | Edit freely |
| review | Under review | Comments only; edits require new review |
| approved | Accepted for publication | Changes require new PR with review |
| deprecated | No longer current | Mark replacement; archive after 6 months |

### State Transitions

```
draft --> review --> approved --> deprecated
  ^         |           |
  |         v           |
  +--- rejected         +--- (updated) --> draft
```

---

## Content Organization

### Taxonomy (Directory Structure)

| Directory | Content Type | Audience |
|-----------|-------------|----------|
| docs/engineering/ | Technical specifications | Developers |
| docs/graphics/ | Rendering/shader docs | Graphics team |
| docs/audio/ | Audio system docs | Audio team |
| docs/effects/ | Effects/plugin docs | Effects team |
| docs/ui/ | UI component docs | UI/UX team |
| docs/user/ | End-user documentation | Users |
| docs/help/ | Support documentation | Users/Support |
| docs/operations/ | Ops procedures | DevOps/Ops |
| docs/releases/ | Release management | Build/Release team |
| docs/security/ | Security documentation | Security team |
| docs/product/ | Product management | Product/Management |
| docs/standards/ | Standards references | All |
| docs/rfc/ | Request for Comments | Engineering |

### Naming Convention

- ALL_CAPS_WITH_UNDERSCORES.md for specification documents
- lowercase-with-hyphens.md for guides and tutorials
- RFC-NNN-title.md for RFCs

---

## Content Reuse Strategy

### Cross-Reference Links

Documents reference each other using relative Markdown links:
```markdown
See [Security Policy](../SECURITY_POLICY.md) for details.
Per [ISO 8601](../standards/ISO_8601_DATE_TIME.md), all dates use YYYY-MM-DD.
```

### Shared Definitions

Common terms defined once in a glossary, referenced elsewhere. Avoids content duplication and ensures consistency.

### Single-Source Publishing

Same content serves multiple outputs:
- Forgejo web rendering (primary)
- PDF export for offline reference
- In-app help system
- Wiki mirrors

---

## Review and Approval Process

### Review Requirements

| Document Type | Reviewers Required | Approval Authority |
|---------------|-------------------|-------------------|
| Engineering spec | 2 engineers + team lead | CTO |
| User documentation | 1 engineer + UX lead | Documentation lead |
| Security policy | Security lead + CTO | CTO |
| Release notes | Build engineer + PM | Product manager |
| Standards reference | 1 engineer | Documentation lead |

### Review Workflow

1. Author creates/modifies document on feature branch
2. PR opened with `docs:` prefix in title
3. Auto-merge-md.yml merges MD-only PRs (for minor updates)
4. Substantive changes require manual review
5. Approved → merged to main → immediately published

---

## Audit Trail Requirements

| Requirement | Implementation |
|-------------|---------------|
| Who changed what, when | Git commit history (author, date, diff) |
| Why it was changed | Commit message + PR description |
| Who approved the change | PR review approvals |
| Previous versions accessible | Git history / tags |
| Changes traceable to requirements | Issue references in commit messages |

---

## Content Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Currency | All docs updated within 90 days of related code change | Last-updated vs. code commit dates |
| Completeness | Every public feature documented | Feature list vs. doc coverage |
| Accuracy | Zero known inaccuracies | Reported issues |
| Consistency | Uniform style and terminology | Style guide compliance |
| Findability | All docs indexed | INDEX.md completeness |

---

## Relationship to Other Standards

| Standard | Relationship |
|----------|-------------|
| ISO/IEC/IEEE 15289:2019 | Defines content of life-cycle information items |
| ISO/IEC/IEEE 26511:2018 | Requirements for managers of information for users |
| ISO/IEC/IEEE 26512:2018 | Requirements for acquirers and suppliers of information for users |
| ISO/IEC/IEEE 26513:2017 | Requirements for testers and reviewers of information for users |
| ISO/IEC/IEEE 26514:2022 | Requirements for designers and developers of information for users |

---

## References

- [ISO/IEC/IEEE 26531:2023 (ISO official)](https://www.iso.org/standard/81703.html)
- [IEEE 26531-2015 (IEEE Xplore)](https://ieeexplore.ieee.org/document/7106441/amendments)
- [ISO/IEC/IEEE 15289:2019 (Content of life-cycle information items)](https://www.iso.org/standard/74909.html)
- [ISO/IEC/IEEE 26531:2023 Online Browsing (ISO OBP)](https://www.iso.org/obp/ui/en/)
