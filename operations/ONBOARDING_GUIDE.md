---
title: "Team Onboarding Guide"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Team Onboarding Guide

**Project:** Mr.Orchords  
**Owner:** Mr.Orchords (Operations Manager)  
**Reviewers:** Mr.Orchords (CTO), all engineering leads  
**ISO Standards:** ISO/IEC 12207:2017 (human resources, development process), ISO/IEC 25010:2023 (maintainability)  
**Version:** 1.0.0  
**Last Updated:** 2026-06-21

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | First-day, first-week, first-month checklist for new hires |
| **Diátaxis form** | How-to guide |
| **Primary audience** | All new hires, Mr.Orchords, all engineering leads |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This guide walks new team members through their first two weeks at Mr.Orchords, covering environment setup, tool access, and team introductions.

## Contents

- [Before Day One (HR — Mr.Orchords)](#before-day-one-hr-mrorchords)
  - [Access & Accounts](#access-accounts)
  - [Welcome Package](#welcome-package)
- [Day One](#day-one)
  - [Morning (9:00 AM – 12:00 PM)](#morning-900-am-1200-pm)
  - [Afternoon (1:00 PM – 5:00 PM)](#afternoon-100-pm-500-pm)
- [First Week Checklist](#first-week-checklist)
  - [All Team Members](#all-team-members)
  - [Engineering Team](#engineering-team)
  - [Product & Design Team](#product-design-team)
  - [QA Team](#qa-team)
  - [DevOps Team](#devops-team)
  - [Marketing & Community Team](#marketing-community-team)
- [First Month](#first-month)
  - [Week 2: Contribute](#week-2-contribute)
  - [Week 3: Own Something Small](#week-3-own-something-small)
  - [Week 4: Review](#week-4-review)
- [Key Contacts for New Hires](#key-contacts-for-new-hires)
- [Useful Resources](#useful-resources)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Before Day One (HR — Mr.Orchords)

Before a new hire's first day, the following must be complete:

### Access & Accounts

- [ ] Laptop ordered and configured (or existing machine re-imaged)
- [ ] Microsoft email account created (`name@orchords.com`)
- [ ] Forgejo organization invite sent (`dev.orchords.com/mr-orchords`)
- [ ] Forgejo Actions + repository access provisioned
- [ ] Firebase project access granted (if backend or cloud role)
- [ ] Slack workspace invite sent
- [ ] 1Password team account provisioned
- [ ] Jira / Linear project access provisioned
- [ ] Windows installation key assigned
- [ ] Mr.Orchords code signing certificate (for engineering) — access request via Mr.Orchords
- [ ] Mr.Orchords internal beta build access (if applicable)
- [ ] NDA signed (Mr.Orchords)

### Welcome Package

- [ ] Welcome email sent with first-week schedule
- [ ] Team directory shared (names, roles, Slack handles)
- [ ] Onboarding buddy assigned

---

## Day One

### Morning (9:00 AM – 12:00 PM)

| Time | Activity | Owner |
|---|---|---|
| 9:00 AM | Welcome + office tour | Mr.Orchords |
| 9:30 AM | Accounts setup session (laptop, email, Slack, GitHub) | IT buddy |
| 10:30 AM | Meet the CTO — role overview, Q&A | Mr.Orchords |
| 11:30 AM | Meet direct manager — team-specific intro | Direct manager |
| 12:00 PM | Team lunch | Team |

### Afternoon (1:00 PM – 5:00 PM)

| Activity | Notes |
|---|---|
| Read [`docs/README.md`](../../docs/README.md) | Full documentation overview |
| Read the role's relevant docs | Manager assigns 3–5 key documents |
| Set up dev environment | See [`docs/engineering/BUILD_SYSTEM.md`](../../docs/engineering/BUILD_SYSTEM.md) |
| Join relevant Slack channels | `#engineering`, `#team-[name]`, `#releases` |
| Read [`MR_ORCHORDS_TEAM.md`](../../MR_ORCHORDS_TEAM.md) | Company and team structure |

---

## First Week Checklist

### All Team Members

- [ ] Slack profile complete (photo, title, timezone)
- [ ] GitHub profile complete with Mr.Orchords affiliation
- [ ] Read company handbook (if exists)
- [ ] Read role description in [`MR_ORCHORDS_TEAM.md`](../../MR_ORCHORDS_TEAM.md)
- [ ] Attend all daily standups for the first week
- [ ] 1:1 meeting with direct manager scheduled

### Engineering Team

- [ ] Read [`docs/engineering/BUILD_SYSTEM.md`](../../docs/engineering/BUILD_SYSTEM.md)
- [ ] Read [`docs/engineering/ARCHITECTURE_OVERVIEW.md`](../../docs/engineering/ARCHITECTURE_OVERVIEW.md)
- [ ] Read [`docs/engineering/TECHNICAL_STANDARDS.md`](../../docs/engineering/TECHNICAL_STANDARDS.md)
- [ ] Read [`docs/engineering/BRANCHING_STRATEGY.md`](../../docs/engineering/BRANCHING_STRATEGY.md)
- [ ] Dev environment builds successfully (run `cmake --preset dev`)
- [ ] First PR opened (can be a docs fix or test — just get the workflow familiar)
- [ ] Meet with domain lead for subsystem overview
- [ ] CI pipeline understood — run a build locally

### Product & Design Team

- [ ] Read [`docs/user/USER_GUIDE.md`](../../docs/user/USER_GUIDE.md)
- [ ] Read [`docs/product/ROADMAP.md`](../../docs/product/ROADMAP.md)
- [ ] Download and use Mr.Orchords (latest beta)
- [ ] Complete a small project in Mr.Orchords (basic edit → export)
- [ ] Explore Linear project (roadmap, current sprint, backlog)

### QA Team

- [ ] Read [`docs/engineering/TEST_STRATEGY.md`](../../docs/engineering/TEST_STRATEGY.md)
- [ ] Read [`docs/PERFORMANCE_BENCHMARKS.md`](../../docs/PERFORMANCE_BENCHMARKS.md)
- [ ] Access bug tracker at [dev.orchords.com](https://dev.orchords.com) and understand issue lifecycle
- [ ] Run the smoke test suite on the latest build
- [ ] Understand the severity scale (S0–S3)

### DevOps Team

- [ ] Read [`docs/engineering/CI_CD_PIPELINE.md`](../../docs/engineering/CI_CD_PIPELINE.md)
- [ ] Read [`docs/engineering/BACKUP_DISASTER_RECOVERY.md`](../../docs/engineering/BACKUP_DISASTER_RECOVERY.md)
- [ ] Access Azure portal and understand current infrastructure
- [ ] Review Forgejo Actions workflows (per the workflows/ index)
- [ ] Meet with Mr.Orchords to understand build pipeline

### Marketing & Community Team

- [ ] Read [`docs/BETA_PROGRAM_GUIDE.md`](../../docs/BETA_PROGRAM_GUIDE.md)
- [ ] Read the current user feedback backlog
- [ ] Join the Discord beta tester community
- [ ] Review current public roadmap on the website

---

## First Month

### Week 2: Contribute

- Begin working on assigned first tasks (small, achievable goals)
- Shadow a team member in a sprint ceremony (planning, review, retro)
- Read 2–3 subsystem-specific docs relevant to your role
- Attend team standups consistently

### Week 3: Own Something Small

- Take ownership of a small task or bug fix
- Open first PR or submit first piece of work
- Receive and act on feedback from code review or manager 1:1
- Start contributing to documentation

### Week 4: Review

- 1-month check-in with manager — what's going well, what's unclear
- Complete first full feature or deliverable (size depends on role)
- Review [`docs/README.md`](../../docs/README.md) — identify docs that are unclear or missing
- Share feedback on the onboarding experience with Mr.Orchords

---

## Key Contacts for New Hires

| Need Help With | Who to Ask |
|---|---|
| Dev environment setup | Mr.Orchords (DevOps) |
| Git / GitHub workflow | Mr.Orchords (DevOps) |
| Product questions | Mr.Orchords (PM) |
| Design questions | Mr.Orchords (UX Designer) |
| Bug tracking / testing | Mr.Orchords (QA) |
| Company operations | Mr.Orchords (Operations) |
| Technical architecture | Mr.Orchords (CTO) |
| Role-specific questions | Your direct manager |

---

## Useful Resources

| Resource | URL / Location |
|---|---|
| Company handbook | Shared in onboarding email |
| Team roster | [`MR_ORCHORDS_TEAM.md`](../../MR_ORCHORDS_TEAM.md) |
| Bug tracker | [dev.orchords.com](https://dev.orchords.com) |
| Git repos (Forgejo) | [dev.orchords.com](https://dev.orchords.com) |
| Documentation index | [`docs/README.md`](../../docs/README.md) |
| Mr.Orchords beta builds | Shared link in onboarding email |
| Slack workspace | orchords.slack.com |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial guide — aligned with ISO/IEC 12207:2017 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.3 (Human Resources), ISO/IEC 25010:2023 (Maintainability)*



---

## References

### Internal Documents

- [$title](./../../MR_ORCHORDS_TEAM.md)
- [$title](./../../docs/BETA_PROGRAM_GUIDE.md)
- [$title](./../../docs/engineering/ARCHITECTURE_OVERVIEW.md)
- [$title](./../../docs/engineering/BACKUP_DISASTER_RECOVERY.md)
- [$title](./../../docs/engineering/BRANCHING_STRATEGY.md)
- [$title](./../../docs/engineering/BUILD_SYSTEM.md)
- [$title](./../../docs/engineering/CI_CD_PIPELINE.md)
- [$title](./../../docs/engineering/TECHNICAL_STANDARDS.md)
- [$title](./../../docs/engineering/TEST_STRATEGY.md)
- [$title](./../../docs/PERFORMANCE_BENCHMARKS.md)
- [$title](./../../docs/product/ROADMAP.md)
- [$title](./../../docs/README.md)
- [$title](./../../docs/user/USER_GUIDE.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Mr.Orchords | Initial version |
| 1.0.1 | June 2026 | Mr.Orchords | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Mr.Orchords (Operations Manager)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type