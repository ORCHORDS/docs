# Community Management Guide

**Project:** Beetle Studio  
**Owner:** Rachel Green (Community Manager)  
**Reviewers:** Chris Taylor (Product Manager), Kirk Beka (CTO)  
**ISO Standards:** ISO/IEC 25010:2023 (usability, user satisfaction), ISO/IEC 12207:2017 (requirements feedback loop)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Discord/forum management, feedback triage, and community guidelines |
| **Diátaxis form** | How-to guide |
| **Primary audience** | Rachel Green, Chris Taylor, Kirk Beka |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines how Mooned Dev manages the Beetle Studio community -- the Discord server, forums, beta program, and social channels where users interact with each other and with the team. Per **ISO/IEC 25010:2023**, user satisfaction is a measurable quality characteristic.
## Contents

- [Community Channels](#community-channels)
- [Discord Server Structure](#discord-server-structure)
  - [Roles](#roles)
  - [Channels](#channels)
- [Community Guidelines](#community-guidelines)
  - [Core Rules](#core-rules)
  - [Enforcement](#enforcement)
- [Feedback Triage Process](#feedback-triage-process)
  - [Feedback Categories](#feedback-categories)
- [Beta Program Coordination](#beta-program-coordination)
- [Social Media](#social-media)
  - [Social Media Guidelines](#social-media-guidelines)
- [Metrics](#metrics)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Community Channels

| Channel | Purpose | Managed By | Frequency |
|---|---|---|---|
| **Discord** | Real-time discussion, beta feedback, support | Rachel Green | Daily |
| **Community Forums** | Long-form Q&A, feature discussions, tutorials | Rachel Green | Daily |
| **Twitter / X** | Product announcements, community highlights | Jason Wong | Daily |
| **YouTube Comments** | Tutorial feedback, feature questions | Rachel Green | Daily |
| **Reddit** | Community discussions, reviews | Jason Wong + Rachel Green | Weekly |
| **GitHub Issues** | Bug reports, feature requests | Lisa Martinez (bug triage) | Daily |

---

## Discord Server Structure

### Roles

| Role | Color | Permissions | Who Has It |
|---|---|---|---|
| **Founder** | Gold | Full admin access | Mooned Dev |
| **Team** | Blue | Read, write, beta access | All Mooned Dev employees |
| **Insider** | Green | Beta access, early announcements | Top community contributors |
| **Beta Tester** | Purple | Access to beta channels | Active beta program members |
| **Member** | Gray | Read and write in public channels | General community |
| **New Member** | White | Read-only for first 24 hours | New joiners |

### Channels

| Channel | Purpose | Moderation |
|---|---|---|
| `#welcome` | Introduction thread for new members | Auto-welcome bot |
| `#announcements` | Product updates, releases, news | Team-only posting |
| `#general` | Open chat for all members | Basic civility rules |
| `#help` | User-to-user technical help | Community support; team monitors |
| `#feedback` | Feature requests and product feedback | Rachel Green reviews weekly |
| `#beta-access` | Beta program discussion | Beta testers only |
| `#showcase` | Members share their work | Encouraged; no self-promotion rules |
| `#bugs` | Community bug reports | Rachel Green triages to Lisa Martinez |

---

## Community Guidelines

### Core Rules

1. **Be respectful** — treat everyone with courtesy; debate ideas, not people
2. **Stay on topic** — channel-specific rules apply (posted in each channel topic)
3. **No piracy or crack tools** — immediate permanent ban
4. **No harassment** — zero tolerance for harassment, hate speech, or threats
5. **English only** — in public channels; language-specific channels may be added later
6. **No spam or self-promotion** — unless in `#showcase` with moderator approval
7. **No sharing of beta builds** — beta builds are NDA-covered; sharing = instant removal from beta program

### Enforcement

| Violation | First Offense | Repeat Offense |
|---|---|---|
| Uncivil behavior | Warning | 1-day mute |
| Spam | Message deleted + warning | 7-day mute |
| Piracy | Immediate ban | — |
| Harassment | Immediate ban | — |
| Beta NDA breach | Beta access revoked | Permanent ban |

---

## Feedback Triage Process

Per **ISO/IEC 12207:2017**, user feedback is an input to requirements and planning. Rachel Green triages community feedback into the product feedback pipeline:

```
Community Feedback
       │
       ▼
┌──────────────────┐
│ Rachel Green     │  ← First touch — acknowledge, categorize
│ Initial Triage  │
└───────┬──────────┘
        │
        ▼
┌──────────────────┐
│ Feedback Triage  │  Weekly meeting: Rachel + Chris Taylor
│ Weekly Review    │
└───────┬──────────┘
        │
        ▼
┌──────────────────┐
│ Chris Taylor     │  ← Feature requests → Roadmap
│ Product Review   │     Bug reports → Lisa Martinez
└───────┬──────────┘     Questions → Tom Anderson (docs)
        │
        ▼
┌──────────────────┐
│ Product Pipeline  │  Added to Linear backlog with priority
│ (Linear)         │  Label: `community-feedback`
└──────────────────┘
```

### Feedback Categories

| Category | Route | SLA |
|---|---|---|
| Bug report | Rachel → `#bugs` → Lisa Martinez (bug triage) | Within 48 hours |
| Feature request | Rachel → `#feedback` → Chris Taylor weekly review | Within 1 week |
| How-to question | Rachel → `#help` community answer | Community response within 4 hours |
| Documentation gap | Rachel → Tom Anderson | Within 1 week |
| Security vulnerability | Rachel → Kirk Beka (immediate) | Within 24 hours |

---

## Beta Program Coordination

The beta program is managed jointly by Rachel Green and Lisa Martinez.

| Task | Owner | Details |
|---|---|---|
| Recruit beta testers | Rachel Green | Discord posts, forum announcements |
| Qualify beta candidates | Rachel Green + Lisa Martinez | Application review, hardware survey |
| Onboard beta testers | Rachel Green | Welcome message, install guide, feedback channel |
| Collect bug reports | Rachel Green → Lisa Martinez | Triage within 48 hours |
| Collect feature feedback | Rachel Green → Chris Taylor | Weekly synthesis |
| Graduate beta testers | Rachel Green + Lisa Martinez | Based on participation quality |

See [`BETA_PROGRAM_GUIDE.md`](../BETA_PROGRAM_GUIDE.md) for the full beta program structure.

---

## Social Media

| Platform | Managed By | Content Focus | Frequency |
|---|---|---|---|
| Twitter / X | Jason Wong | Announcements, release notes, community highlights | 3–5 posts/week |
| YouTube | Jason Wong + David Lee | Tutorials, showcase videos | 1–2 videos/month |
| Reddit | Jason Wong + Rachel Green | Community AMAs, release discussions | As needed |

### Social Media Guidelines

- Product announcements must be approved by Chris Taylor before posting
- Bug complaints are acknowledged but not diagnosed publicly — direct to support
- Community highlights and user work are shared with creator permission
- No teasing unannounced features without leadership approval

---

## Metrics

Rachel Green tracks these community health metrics monthly:

| Metric | Target | Why |
|---|---|---|
| Discord active members (monthly) | Growing month-over-month | Community health |
| Beta feedback response rate | ≥ 80% acknowledged within 48 hours | Engagement |
| Bug reports routed to QA within 48 hours | 100% | Process efficiency |
| Feature requests added to backlog within 1 week | ≥ 80% | Feedback loop health |
| User satisfaction (post-support) | ≥ 85% | Quality of support |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial guide — aligned with ISO/IEC 25010:2023 and ISO/IEC 12207:2017 |

---

*Grounded in: ISO/IEC 25010:2023 (User Satisfaction, Usability), ISO/IEC 12207:2017 §6.1 (Feedback Loop)*



---

## References

### Internal Documents

- [$title](./../BETA_PROGRAM_GUIDE.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Rachel Green | Initial version |
| 1.0.1 | June 2026 | Rachel Green | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Monthly
- **Reviewer:** Rachel Green (Community Manager)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type