# Beta Program Guide

**Project:** Beetle Studio  
**Owners:** Lisa Martinez (QA Lead — testing program), Rachel Green (Community Manager — beta community)  
**Reviewers:** Kirk Beka (CTO), Chris Taylor (Product Manager)  
**ISO Standards:** ISO/IEC 12207:2017 (validation), ISO/IEC 25010:2023 (reliability, usability)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Beta testing program structure, tiers, and feedback process |
| **Diátaxis form** | How-to guide |
| **Primary audience** | Lisa Martinez, Rachel Green, Chris Taylor, beta testers |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

The Beetle Studio Beta Program gives selected users early access to pre-release builds for real-world testing. Per **ISO/IEC 12207:2017 section 6.4**, validation is required to confirm the software meets intended use -- beta testing is our primary validation activity before each stable release.
## Contents

- [Beta Program Tiers](#beta-program-tiers)
- [Beta Qualification Criteria](#beta-qualification-criteria)
  - [Closed Beta Candidates](#closed-beta-candidates)
  - [Exclusion Criteria](#exclusion-criteria)
- [Beta Lifecycle](#beta-lifecycle)
  - [Phase 1: Recruitment](#phase-1-recruitment)
  - [Phase 2: Onboarding](#phase-2-onboarding)
  - [Phase 3: Testing](#phase-3-testing)
  - [Phase 4: Feedback Collection](#phase-4-feedback-collection)
- [Bug Reporting Requirements](#bug-reporting-requirements)
  - [For Beta Testers](#for-beta-testers)
  - [Severity Ratings](#severity-ratings)
  - [Required: Expected-vs-Actual + Before/After Images](#required-expected-vs-actual-beforeafter-images)
  - [Quick Template (for Slack / Discord quick reports)](#quick-template-for-slack-discord-quick-reports)
- [Beta Tester Benefits](#beta-tester-benefits)
- [Graduating from Beta](#graduating-from-beta)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---


---

## Beta Program Tiers

| Tier | Audience | Size | Access | Feedback Expectation |
|---|---|---|---|---|
| **Alpha** | Internal team + close partners | 5–10 | Pre-alpha builds | Immediate; Slack/daily |
| **Closed Beta** | Selected external power users | 50–100 | Release candidates | Weekly; structured feedback |
| **Public Beta** | Anyone who signs up | Unlimited | Stable beta builds | Optional; community forum |

---

## Beta Qualification Criteria

### Closed Beta Candidates

Users must meet **at least 3** of these:

- [ ] Regular user of professional video editing software (Premiere, DaVinci, After Effects)
- [ ] Owns hardware meeting Beetle Studio recommended specs
- [ ] Has participated in at least one previous beta program
- [ ] Active on community forum or Discord
- [ ] Can commit to weekly testing sessions during beta period

### Exclusion Criteria

- Users under 18 years old (legal liability)
- Users in embargoed countries (export compliance)
- Competitor employees

---

## Beta Lifecycle

```
Recruit → Select → Onboard → Test → Report → Retrospective → Graduate to Stable
```

### Phase 1: Recruitment

Rachel Green manages recruitment:
- Community posts on Discord and forum
- Application form (name, hardware, experience, availability)
- Lisa Martinez reviews and selects

### Phase 2: Onboarding

Each beta tester receives:

- [ ] Beta access agreement (non-disclosure, liability waiver)
- [ ] Download link and installation instructions
- [ ] Quick start guide for beta builds
- [ ] Feedback channel access (dedicated Discord channel)
- [ ] Bug report template

### Phase 3: Testing

| Activity | Frequency | Expected Time |
|---|---|---|
| **Feature testing** | Per feature iteration | 30–60 min per feature |
| **Regression testing** | Before each beta build | 15–20 min |
| **Feedback sessions** | Weekly async form | 20 min |
| **Community discussion** | Ongoing | As needed |

### Phase 4: Feedback Collection

Lisa Martinez collects and triages feedback:

| Feedback Type | Channel | Triage SLA |
|---|---|---|
| Bug reports | In-app report tool + Discord | Within 48 hours |
| Feature feedback | Beta forum thread | Within 1 week |
| Usability observations | Rachel Green → Lisa Martinez | Weekly review |

---

## Bug Reporting Requirements

### For Beta Testers

A good bug report includes:

1. **What happened** — one sentence
2. **Steps to reproduce** — numbered steps
3. **Expected behavior** — what should happen
4. **Actual behavior** — what actually happened
5. **Environment:**
   - Beetle Studio version
   - Windows version
   - GPU model
   - Project file (if shareable)
6. **Severity** — Critical / Major / Minor / Cosmetic

### Severity Ratings

| Severity | Definition | Example |
|---|---|---|
| **Critical** | Application crash, data loss | Crashes on launch, project file corrupted |
| **Major** | Core feature broken | Cannot export, timeline unresponsive |
| **Minor** | Feature impaired but usable | Color wheel slow to respond |
| **Cosmetic** | Visual issue, no functional impact | Misaligned pixel, typo in label |

### Required: Expected-vs-Actual + Before/After Images

**Every bug report — from beta testers, QA, or users — must follow the investigation loop and template defined in [`TEST_STRATEGY.md` -> Bug Investigation: Expected vs Actual + Before/After Loop](../engineering/TEST_STRATEGY.md#bug-investigation-expected-vs-actual--beforeafter-loop).**

The summary:

- **Before filing, ask yourself 5 self-questions** in order: what am I looking at, what is the app doing, what should it be doing, why is it wrong, can I capture it?
- **The full bug template** (in TEST_STRATEGY.md) requires an **8-section report** including a **before screenshot** and (for UI bugs) an **expected reference image**.
- **Files are stored at `tests/bugs/<BUG-ID>/before.png`** and `after-N.png` for fix iterations.
- **The fix loop terminates** only when a tester confirms the after image matches the expected description under the same repro conditions — "I think it's fixed" is not a fix.

Beta testers who submit reports using the full template + before/expected images get **priority triage** (see Benefits below).

### Quick Template (for Slack / Discord quick reports)

For casual reports in the beta Discord, the minimum viable is:

```markdown
**What I was doing:** [one line]
**Expected:** [one line]
**Actual:** [one line]
**Hypothesis:** [optional, one line]
**Before image:** [attach screenshot]
**Repro:** [1-2-3]
**Build / OS / GPU:** [Beetle Studio vX / Win 11 / RTX 3060]
```

Anything less than this is not actionable and will be deprioritized.

---

## Beta Tester Benefits

| Benefit | Details |
|---|---|
| **Early access** | New features before public release |
| **Direct influence** | Feedback directly shapes the product |
| **Beta badge** | Special badge on community profile |
| **Free Pro license** | Full Pro access during beta period |
| **Credit** | Listed in the Beetle Studio credits (opt-in) |
| **Invitation to v1.0 launch** | Beta alumni event |

---

## Graduating from Beta

Top-performing beta testers are:

- Offered spots in future beta programs
- Invited to the **Beetle Studio Insiders** group (long-term advisory)
- Given priority access to new features
- Compensated for extended testing engagement

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial guide — aligned with ISO/IEC 12207:2017 validation and ISO/IEC 25010:2023 |

---

*Grounded in: ISO/IEC 12207:2017 §6.4 (Validation Process), ISO/IEC 25010:2023 (Reliability, Usability)*


---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Unknown owner | Initial version |
| 1.0.1 | June 2026 | Unknown owner | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On each beta cycle
- **Reviewer:** Lisa Martinez (QA Lead — testing program)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type