> Auto-generated from `Launch Playbook.md` in the docs repo.

> Auto-generated from `docs/marketing/LAUNCH_PLAYBOOK.md` in the docs repo.

---
title: "Launch Playbook"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Launch Playbook

**Project:** Beetle Studio  
**Owner:** Jason Wong (Marketing Lead) — overall campaign; Sarah Miller (Build) — release execution  
**Reviewers:** Kirk Beka (CTO), Chris Taylor (PM), Rachel Green (Community), Mooned Dev (CEO)  
**ISO Standards:** ISO/IEC 12207:2017 (distribution/launch), ISO/IEC 25010:2023 (product quality at launch)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Pre-launch, launch day, and 30-day post-launch marketing playbook |
| **Diátaxis form** | How-to guide |
| **Primary audience** | Jason Wong, Sarah Miller, Rachel Green, Chris Taylor |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This playbook governs how Beetle Studio launches -- from pre-launch preparation through launch day and the 30-day post-launch period. Per **ISO/IEC 12207:2017 section 6.4**, distribution is a formal transition activity.
## Contents

- [Launch Types](#launch-types)
- [Launch Timeline (Major Stable Release)](#launch-timeline-major-stable-release)
  - [T-6 Weeks: Foundation](#t-6-weeks-foundation)
  - [T-4 Weeks: Testing & Verification](#t-4-weeks-testing-verification)
  - [T-2 Weeks: Pre-Launch Build-Up](#t-2-weeks-pre-launch-build-up)
  - [T-1 Week: Final Runway](#t-1-week-final-runway)
  - [Launch Day (T-0)](#launch-day-t-0)
- [Launch Day Monitoring](#launch-day-monitoring)
  - [Key Metrics to Track (Hourly)](#key-metrics-to-track-hourly)
  - [Hotfix Standby](#hotfix-standby)
- [Post-Launch (T+1 to T+30)](#post-launch-t1-to-t30)
  - [Week 1: Stabilization](#week-1-stabilization)
  - [Week 2–4: Impact Measurement](#week-24-impact-measurement)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Launch Types

| Launch Type | Scope | Example | Timeline |
|---|---|---|---|
| **Major Stable Release** | Full public launch | v1.0, v2.0 | 6-week campaign |
| **Feature Release** | New feature announced | Multi-camera tracks in v2.4 | 3-week campaign |
| **Hotfix** | Critical bug fix | Crash fix in v2.3.1 | 1-week fast release |
| **Beta Launch** | New beta program opening | v2.5 beta | 2-week campaign |

This playbook covers **Major Stable Release**. Feature releases and hotfixes use abridged versions.

---

## Launch Timeline (Major Stable Release)

### T-6 Weeks: Foundation

| Week | Owner | Deliverables |
|---|---|---|
| **Marketing assets** | Jason Wong | Launch video (2–3 min), key art, screenshots, press kit |
| **Website update** | Jason Wong + Tom Anderson | Landing page redesign, feature pages, pricing page |
| **Press kit** | Jason Wong | Press release, fact sheet, logo package, screenshots |
| **Social media plan** | Jason Wong | 30-day content calendar for launch week |
| **Release notes draft** | Tom Anderson | First draft of release notes for review |
| **Pre-launch blog post** | Jason Wong | "What to expect from Beetle Studio vX.Y" teaser post |
| **Sales enablement** | Kevin Brown | Pitch deck, FAQ for enterprise prospects |

### T-4 Weeks: Testing & Verification

| Week | Owner | Deliverables |
|---|---|---|
| **Store submission** | Sarah Miller | MSIX package, Store listing, age rating, privacy declaration |
| **Store certification** | Sarah Miller | Awaiting Microsoft certification (typically 3–5 days) |
| **Legal review** | Amanda Clark | EULA, ToS, privacy policy — final review |
| **Final QA pass** | Lisa Martinez | Regression tests, exploratory testing, performance benchmarks |
| **Support preparation** | Rachel Green | Support FAQ updated, Rachel briefed on new features |
| **Pricing finalized** | Kevin Brown | Pricing confirmed and configured in Store and website |

### T-2 Weeks: Pre-Launch Build-Up

| Week | Owner | Deliverables |
|---|---|---|
| **Press outreach** | Jason Wong | Embargoed press preview sent to select outlets |
| **Beta alumni outreach** | Rachel Green | Invitation to launch-day preview for top beta testers |
| **Social media teaser** | Jason Wong | Countdown posts, feature hints, behind-the-scenes content |
| **Community post** | Rachel Green | Discord announcement — what the team has been building |
| **Email to newsletter** | Jason Wong | "Something big is coming" email to subscriber list |
| **Influencer outreach** | Jason Wong | Review units sent to selected YouTube reviewers |
| **Final release checklist** | Sarah Miller | All items in [`RELEASE_CHECKLIST.md`](../releases/RELEASE_CHECKLIST.md) complete |

### T-1 Week: Final Runway

| Day | Owner | Deliverables |
|---|---|---|
| **T-7** | Sarah Miller | Final release build, signing, artifacts uploaded |
| **T-5** | Lisa Martinez | Final smoke tests pass; post launch hotfix plan ready |
| **T-3** | Jason Wong | Press release finalized; approved by Mooned Dev |
| **T-2** | All leads | Launch readiness review meeting |
| **T-1** | Jason Wong | Social media posts scheduled; email blast scheduled |
| **T-1** | Sarah Miller | Installer live on download server (hidden until launch) |

### Launch Day (T-0)

| Time | Activity | Owner | Status |
|---|---|---|---|
| **6:00 AM** | Wake-up check — all systems online | Mike Johnson | |
| **8:00 AM** | Publish press release | Jason Wong | |
| **8:00 AM** | Discord announcement | Rachel Green | |
| **8:00 AM** | Twitter/X thread posted | Jason Wong | |
| **8:00 AM** | Email blast to subscribers | Jason Wong | |
| **8:00 AM** | Website updated (landing page live) | Jason Wong | |
| **8:00 AM** | Download link live | Sarah Miller | |
| **8:00 AM** | Store submission approved and live | Sarah Miller | |
| **9:00 AM** | Team Slack: all hands — launch day monitoring | Kirk Beka | |
| **Ongoing** | Monitor social mentions | Jason Wong + Rachel Green | |
| **Ongoing** | Monitor crash reports | Lisa Martinez | |
| **Ongoing** | Monitor support tickets | Rachel Green | |
| **End of day** | Launch metrics roundup | Jason Wong | |

---

## Launch Day Monitoring

### Key Metrics to Track (Hourly)

| Metric | Where to Watch | Target |
|---|---|---|
| Download count | Azure Blob Storage + Store dashboard | Growing |
| Install success rate | Crash reporting (Firebase Crashlytics) | ≥ 95% |
| Crash rate (first 1 hour) | Crashlytics | < 0.1% of installs |
| Sign-up / activation rate | Firebase Auth dashboard | Monitor baseline |
| Social mentions | Twitter/X, Reddit | Growing positive sentiment |
| Press coverage | Google Alerts, mentions | Coverage starting |
| Support ticket volume | Support inbox | Manageable queue |

### Hotfix Standby

| Role | Action If Issues Found |
|---|---|
| **Lisa Martinez** | Log critical bug; notify Kirk Beka immediately |
| **Kirk Beka** | Assess severity; decide if hotfix is needed |
| **Sarah Miller** | Standby to build and sign hotfix within 4 hours |
| **Rachel Green** | Post community update acknowledging issue if public |

---

## Post-Launch (T+1 to T+30)

### Week 1: Stabilization

| Day | Owner | Activity |
|---|---|---|
| T+1 | All leads | Post-launch review meeting — what went well, what's broken |
| T+1–T+3 | Lisa Martinez | Monitor crash reports; triage critical bugs |
| T+1–T+3 | Sarah Miller | If hotfix needed, build and ship within 48 hours |
| T+1–T+3 | Rachel Green | Community Q&A, support triage |
| T+7 | Chris Taylor | Collect user feedback; identify top 10 pain points |

### Week 2–4: Impact Measurement

| Week | Owner | Deliverables |
|---|---|---|
| Week 2 | Jason Wong | First download + revenue report |
| Week 2 | Lisa Martinez | Bug trend analysis — are crashes declining? |
| Week 3 | Chris Taylor | User feedback synthesis — what do new users love? What frustrates them? |
| Week 3 | Jason Wong | Media coverage summary |
| Week 4 | Kirk Beka | Engineering retro — what should we improve for the next release? |
| Week 4 | All | Roadmap updated based on launch learnings |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial playbook — aligned with ISO/IEC 12207:2017 §6.4 and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Distribution), ISO/IEC 25010:2023 (Product Quality at Launch)*



---

## References

### Internal Documents

- [$title](./../releases/RELEASE_CHECKLIST.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Jason Wong | Initial version |
| 1.0.1 | June 2026 | Jason Wong | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Per launch campaign
- **Reviewer:** Jason Wong (Marketing Lead) — overall campaign
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type