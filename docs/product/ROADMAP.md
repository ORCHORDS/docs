---
title: "Product Roadmap"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Product Roadmap

**Project:** Beetle Studio  
**Owner:** Chris Taylor (Product Manager)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)  
**ISO Standards:** ISO/IEC 12207:2017 (requirements definition, planning), ISO/IEC 25010:2023 (functional suitability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Living product roadmap, feature lifecycle, and priority tiers |
| **Diátaxis form** | Explanation |
| **Primary audience** | Chris Taylor, Kirk Beka, Mooned Dev, all leads |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines Beetle Studio's living product roadmap -- the prioritized list of features, improvements, and infrastructure work that drives the product forward. Per **ISO/IEC 12207:2017 section 6.1**, the product roadmap is the bridge between user needs and engineering work. The roadmap is **not** a commitment -- it is a living plan updated quarterly.

This document defines Beetle Studio's living product roadmap — the prioritized list of features, improvements, and infrastructure work that drives the product forward. Per **ISO/IEC 12207:2017 §6.1**, the product roadmap is the bridge between user needs (captured through research and feedback) and the engineering work planned for future releases.
## Contents

- [Roadmap Philosophy](#roadmap-philosophy)
- [Roadmap Tiers](#roadmap-tiers)
  - [Now (Current Quarter)](#now-current-quarter)
  - [Next (Next 1–2 Quarters)](#next-next-12-quarters)
  - [Later (Future Planning)](#later-future-planning)
- [Feature Lifecycle](#feature-lifecycle)
  - [Discovery](#discovery)
  - [Definition](#definition)
  - [Design](#design)
  - [Build](#build)
  - [Test](#test)
  - [Ship](#ship)
- [Roadmap Communication](#roadmap-communication)
- [Roadmap Reviews](#roadmap-reviews)
- [How Features Are Prioritized](#how-features-are-prioritized)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Roadmap Philosophy

We build the roadmap using these principles:

1. **User problems first** — we prioritize features that solve real user problems, not features that look good on a spec sheet
2. **Feedback-driven** — every item on the roadmap is grounded in user research, beta feedback, or strategic need
3. **Technically feasible** — engineering validates estimates before features are committed
4. **Releasable increments** — features are broken into shippable chunks, not monolithic projects
5. **Transparent** — the roadmap is shared with the entire team; tradeoffs are explicit

---

## Roadmap Tiers

### Now (Current Quarter)

Features actively being designed or built. High confidence they will ship.

| Feature | Type | Status | Owner |
|---|---|---|---|
| Multi-camera track support | Feature | In development | Emma Thompson |
| GPU-accelerated color wheels | Performance | In development | James Park |
| VST3 plugin support | Feature | In development | Ryan Foster |

### Next (Next 1–2 Quarters)

Features that are prioritized and planned, but not yet in development.

| Feature | Type | Estimated Quarter | Dependencies |
|---|---|---|---|
| Cloud collaborative editing | Feature | Q2 2027 | Backend sync (v1) |
| Plugin marketplace | Feature | Q1 2027 | Plugin SDK v1 |
| AV1 hardware encoding (AMD) | Performance | Q4 2026 | AMD SDK update |
| macOS support | Platform | Q3 2027 | Cross-platform engine work |

### Later (Future Planning)

Important features on the horizon. No committed timeline yet.

| Feature | Type | Notes |
|---|---|---|
| Neural effects / AI-assisted editing | Innovation | Exploring tooling; no committed timeline |
| Mobile companion app | Platform | Concept only |
| Scripting / automation API | Platform | Developer ecosystem play |

---

## Feature Lifecycle

A feature moves through these stages before it ships:

```
Discovery ──► Definition ──► Design ──► Build ──► Test ──► Ship
    │             │            │          │         │        │
    ▼             ▼            ▼          ▼         ▼        ▼
 User research  PRDs        UI/UX    Engineering  QA      Release
 + validation  approved    finalized  Sprint work  Signoff  Notes
```

### Discovery
- User feedback, competitive analysis, or strategic need identified
- Chris Taylor captures problem statement
- Estimated business value documented

### Definition
- Product Requirements Document (PRD) written
- Priority assigned using the [`PRIORITY_FRAMEWORK.md`](./PRIORITY_FRAMEWORK.md)
- Kirk Beka reviews for technical feasibility and scope
- Acceptance criteria defined

### Design
- Nina Patel (UX) designs interaction model
- Alex Chen (UI) implements UI components
- Daniel Kim (Effects) specs plugin API changes if applicable

### Build
- Work estimated and added to sprint backlog
- Engineers implement in sprint
- Lisa Martinez plans test coverage

### Test
- Lisa Martinez runs regression tests
- Beta testers validate feature end-to-end
- Bug fixes resolved before ship

### Ship
- Release notes written by Tom Anderson
- Changelog updated by Sarah Miller
- Announcement by Jason Wong (marketing)
- Post-launch monitoring for 2 weeks

---

## Roadmap Communication

| Audience | Format | Frequency | Owner |
|---|---|---|---|
| Engineering team | Detailed roadmap in Linear (backlog) | Sprint planning | Chris Taylor |
| Leadership | Roadmap review presentation | Monthly | Chris Taylor |
| Beta testers | Feature preview newsletter | Per feature | Rachel Green |
| Public | High-level roadmap on website | Quarterly | Chris Taylor + Jason Wong |
| Investors | Strategic roadmap | Quarterly | Mooned Dev |

---

## Roadmap Reviews

The roadmap is reviewed and updated:

| Review Type | Frequency | Attendees | Output |
|---|---|---|---|
| **Sprint planning** | Every 2 weeks | Chris Taylor + engineering leads | Sprint backlog confirmed |
| **Quarterly roadmap review** | Every quarter | Full leadership team | Roadmap updated for next quarter |
| **Ad-hoc** | As needed | Chris Taylor + Kirk Beka | Roadmap adjusted if priorities change |

Quarterly reviews assess:
- What shipped and what was the impact?
- Were estimates accurate?
- Did priorities shift based on new information?
- What's changed in the competitive landscape?
- What needs to move, add, or remove?

---

## How Features Are Prioritized

Features are prioritized using MoSCoW + RICE scoring. See [`PRIORITY_FRAMEWORK.md`](./PRIORITY_FRAMEWORK.md) for the full methodology.

**Summary:**
- **Must have** — core functionality; blocks user from doing their job
- **Should have** — significant improvement; strong user demand
- **Could have** — nice to have; nice improvement if time allows
- **Won't have (this release)** — explicitly deprioritized; documented why

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial roadmap — aligned with ISO/IEC 12207:2017 §6.1 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Requirements Definition, Planning), ISO/IEC 25010:2023 (Functional Suitability)*



---

## References

### Internal Documents

- [$title](././PRIORITY_FRAMEWORK.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Chris Taylor | Initial version |
| 1.0.1 | June 2026 | Chris Taylor | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Chris Taylor (Product Manager)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type