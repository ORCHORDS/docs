---
title: "Beetle Studio Team"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Beetle Studio Team

**Project:** Beetle Studio
**Owner:** Mooned Dev (CEO)
**Reviewers:** Kirk Beka (CTO)
**ISO Standards:** ISO/IEC 12207:2017 (lifecycle), ISO/IEC 25010:2023 (quality model)
**Version:** 1.0.0
**Last Updated:** 2026-06-21

---

## Overview

This document provides the canonical reference for the Beetle Studio team's structure, schedule, and operations. It is grounded in ISO/IEC 12207:2017 (Software life cycle processes) and ISO/IEC 25010:2023 (Quality model).

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | This document covers beetle studio team for the Beetle Studio team. |
| **Diátaxis form** | Reference |
| **Primary audience** | All team members |
| **Secondary audience** | External partners and recruiters |

---

## Contents

- [Leadership](#leadership)
  - [1. Mooned Dev — Founder & CEO](#1-mooned-dev-founder-ceo)
  - [2. Kirk Beka — Co-Founder & CTO](#2-kirk-beka-cofounder-cto)
- [Engineering Department](#engineering-department)
  - [3. Alex Chen — Lead UI/UX Engineer](#3-alex-chen-lead-uiux-engineer)
  - [4. Maya Rodriguez — Senior Backend Developer](#4-maya-rodriguez-senior-backend-developer)
  - [5. James Park — Senior Graphics Engineer](#5-james-park-senior-graphics-engineer)
  - [6. Sophie Williams — Video Codec Engineer](#6-sophie-williams-video-codec-engineer)
  - [7. Daniel Kim — Effects & Compositing Engineer](#7-daniel-kim-effects-compositing-engineer)
  - [8. Emma Thompson — Timeline Engineer](#8-emma-thompson-timeline-engineer)
  - [9. Ryan Foster — Audio Engineer](#9-ryan-foster-audio-engineer)
  - [10. Lisa Martinez — Quality Assurance Lead](#10-lisa-martinez-quality-assurance-lead)
- [Product & Design](#product-design)
  - [11. Chris Taylor — Product Manager](#11-chris-taylor-product-manager)
  - [12. Nina Patel — UX Designer](#12-nina-patel-ux-designer)
  - [13. David Lee — Motion Graphics Designer](#13-david-lee-motion-graphics-designer)
- [DevOps & Infrastructure](#devops-infrastructure)
  - [14. Mike Johnson — DevOps Engineer](#14-mike-johnson-devops-engineer)
  - [15. Sarah Miller — Build & Release Engineer](#15-sarah-miller-build-release-engineer)
- [Marketing & Community](#marketing-community)
  - [16. Jason Wong — Marketing Manager](#16-jason-wong-marketing-manager)
  - [17. Rachel Green — Community Manager](#17-rachel-green-community-manager)
  - [18. Tom Anderson — Technical Writer](#18-tom-anderson-technical-writer)
- [Business & Operations](#business-operations)
  - [19. Amanda Clark — Operations Manager](#19-amanda-clark-operations-manager)
  - [20. Kevin Brown — Business Development](#20-kevin-brown-business-development)
- [Team Structure Overview](#team-structure-overview)
- [Hiring Priorities (In Order)](#hiring-priorities-in-order)

---
**Company:** Mooned Dev  
**Product:** Beetle Studio (Professional Video Editor)  
**Website:** www.mooned.dev  
**Founded:** 2025  

---

## Leadership

### 1. Mooned Dev — Founder & CEO
**Role:** Chief Executive Officer, Lead Graphics Engineer  
**Department:** Executive / Engineering  

**Bio:** Visionary founder driving the development of Beetle Studio. Leads the graphics engineering team and sets the technical direction for the core video editing engine.

**Responsibilities:**
- Company vision and strategy
- Core graphics engine architecture (DirectX 12 / Vulkan)
- Video decoding pipeline (FFmpeg integration)
- GPU-accelerated rendering systems
- Performance optimization and memory management
- Final decision-maker on technical direction

**Skills:** C++20, DirectX 12, Vulkan, FFmpeg, CUDA/OpenCL, Multi-threading, SIMD optimization

---

### 2. Kirk Beka — Co-Founder & CTO
**Role:** Chief Technology Officer  
**Department:** Engineering  

**Bio:** Co-founder and technical backbone of Beetle Studio. Bridges the gap between creative vision and technical implementation.

**Responsibilities:**
- Technical architecture and system design
- Cross-platform strategy (Windows primary, future macOS/Linux)
- Code review and quality standards
- Infrastructure and DevOps leadership
- Security and licensing systems
- Team technical mentorship

**Skills:** C++20, Qt6, CMake, System Architecture, CI/CD, Cloud Infrastructure

---

## Engineering Department

### 3. Alex Chen — Lead UI/UX Engineer
**Role:** UI/UX Lead  
**Department:** Engineering  

**Bio:** Builds the beautiful, responsive interfaces that make Beetle Studio intuitive. Passionate about smooth interactions and modern design.

**Responsibilities:**
- Qt6-based UI framework development
- Timeline component architecture
- Panel system (effects, properties, project)
- User experience optimization
- Accessibility standards compliance
- UI/UX feedback from beta testers

**Skills:** Qt6, C++, QML, UI/UX Design, Animation Systems, Multi-monitor support

---

### 4. Maya Rodriguez — Senior Backend Developer
**Role:** Backend Lead  
**Department:** Engineering / Backend  

**Bio:** Powers all cloud functionality — authentication, databases, and seamless user experiences across devices.

**Responsibilities:**
- Firebase authentication system (email, Google, SSO)
- Firestore database architecture
- Cloud functions for business logic
- User project sync and backup
- API design and documentation
- Rate limiting and security

**Skills:** Firebase, Cloud Functions, Node.js, REST APIs, Firestore, Security

---

### 5. James Park — Senior Graphics Engineer
**Role:** Graphics Engineer  
**Department:** Engineering  

**Bio:** Deep expertise in real-time rendering and GPU programming. Makes every frame look stunning.

**Responsibilities:**
- DirectX 12 rendering pipeline
- Vulkan backend implementation
- Shader development (HLSL/GLSL)
- Color management (HDR, LUT support)
- Preview viewport optimization
- GPU memory management

**Skills:** DirectX 12, Vulkan, HLSL, GLSL, GPU Architecture, Color Science

---

### 6. Sophie Williams — Video Codec Engineer
**Role:** Codec & Compression Specialist  
**Department:** Engineering  

**Bio:** FFmpeg wizard who ensures Beetle Studio can read and write any video format imaginable.

**Responsibilities:**
- FFmpeg integration and optimization
- Hardware encoding (NVENC, QuickSync, VCE)
- New format support (AV1, VVC)
- Frame-accurate seeking and scrubbing
- Color space conversion
- Deblocking and artifact reduction

**Skills:** FFmpeg/libavcodec, Video Codecs (H.264, HEVC, AV1), GPU Encoding, Signal Processing

---

### 7. Daniel Kim — Effects & Compositing Engineer
**Role:** Effects Engineer  
**Department:** Engineering  

**Bio:** Brings visual magic to life with GPU-accelerated effects and compositing systems.

**Responsibilities:**
- GPU-accelerated effect pipeline
- Layer compositing system
- Color correction (curves, levels, LUT)
- Blur, sharpen, noise reduction
- Custom shader support for plugins
- OpenFX plugin compatibility

**Skills:** GPU Computing, CUDA/OpenCL, Image Processing, OpenFX, Shader Programming

---

### 8. Emma Thompson — Timeline Engineer
**Role:** Timeline Systems Engineer  
**Department:** Engineering  

**Bio:** Architect of the timeline — the heart of any video editor. Makes complex editing feel effortless.

**Responsibilities:**
- Timeline data structures and algorithms
- Clip trimming, splitting, nesting
- Multi-track audio/video synchronization
- Undo/redo system
- Timeline caching and virtualization
- Keyboard shortcut system

**Skills:** Data Structures, C++, Real-time UI, Audio Sync, State Management

---

### 9. Ryan Foster — Audio Engineer
**Role:** Audio Systems Engineer  
**Department:** Engineering  

**Bio:** Crystal clear audio is half the video. Handles everything from playback to final mix.

**Responsibilities:**
- Audio playback engine
- Multi-track audio mixing
- Audio effects (EQ, compressor, reverb)
- VST plugin support
- Audio sync with video
- Waveform visualization

**Skills:** Audio DSP, C++, VST SDK, ASIO/WASAPI, FFT Analysis

---

### 10. Lisa Martinez — Quality Assurance Lead
**Role:** QA Lead  
**Department:** Engineering / QA  

**Bio:** Ensures every release is rock-solid. Catches bugs before users do.

**Responsibilities:**
- Test strategy and planning
- Automated testing pipelines
- Performance benchmarking
- Regression testing
- Beta program management
- Bug tracking and triaging

**Skills:** Test Automation, C++, Performance Profiling, Bug Tracking Systems, CI/CD

---

## Product & Design

### 11. Chris Taylor — Product Manager
**Role:** Product Manager  
**Department:** Product  

**Bio:** Translates user needs into features. Makes sure we're building the right things.

**Responsibilities:**
- Product roadmap planning
- User research and feedback analysis
- Feature prioritization
- Sprint planning
- Competitor analysis
- Documentation oversight

**Skills:** Product Management, User Research, Agile/Scrum, Analytics, Communication

---

### 12. Nina Patel — UX Designer
**Role:** UX Designer  
**Department:** Product / Design  

**Bio:** Designs intuitive workflows that make complex editing accessible to everyone.

**Responsibilities:**
- User interface design
- Interaction design
- User flow mapping
- Prototyping and testing
- Design system maintenance
- Accessibility auditing

**Skills:** Figma, User Research, Prototyping, Design Systems, Accessibility (WCAG)

---

### 13. David Lee — Motion Graphics Designer
**Role:** Motion Designer  
**Department:** Product / Design  

**Bio:** Creates stunning title templates and motion graphics that ship with Beetle Studio.

**Responsibilities:**
- Title template creation
- Motion graphics presets
- Transitions and effects templates
- Default project templates
- Tutorial content creation
- Brand asset development

**Skills:** After Effects, Motion Design, 3D Animation, Graphic Design, Video Production

---

## DevOps & Infrastructure

### 14. Mike Johnson — DevOps Engineer
**Role:** DevOps Lead  
**Department:** Engineering / DevOps  

**Bio:** Keeps the build pipeline running smoothly and deployments seamless.

**Responsibilities:**
- CI/CD pipeline management (Forgejo Actions, GitHub Actions–compatible syntax)
- Build system optimization
- Docker/containerization
- Cloud infrastructure (Azure)
- Release management
- Monitoring and alerting

**Skills:** Forgejo Actions (GitHub Actions–compatible YAML), Azure, Docker, CMake, Release Engineering, Monitoring

---

### 15. Sarah Miller — Build & Release Engineer
**Role:** Build Engineer  
**Department:** Engineering / DevOps  

**Bio:** Masters the art of packaging and distribution. Gets Beetle Studio to users worldwide.

**Responsibilities:**
- Installer development (Inno Setup / WiX)
- Code signing (Azure Artifact Signing)
- Multi-platform builds
- Update/patch distribution
- Windows Store submissions
- Version management

**Skills:** Inno Setup, WiX Toolset, Code Signing, Windows Installer, Packaging

---

## Marketing & Community

### 16. Jason Wong — Marketing Manager
**Role:** Marketing Lead  
**Department:** Marketing  

**Bio:** Spreads the word about Beetle Studio. Builds brand awareness and drives adoption.

**Responsibilities:**
- Marketing strategy
- Content marketing
- Social media management
- Press relations
- SEO/SEM
- Analytics and reporting

**Skills:** Digital Marketing, Content Strategy, SEO, Social Media, Analytics

---

### 17. Rachel Green — Community Manager
**Role:** Community Manager  
**Department:** Marketing  

**Bio:** Builds and nurtures the Beetle Studio community. Makes users feel heard.

**Responsibilities:**
- Discord community management
- Forum moderation
- User feedback collection
- Beta program coordination
- Tutorial community support
- Brand advocacy programs

**Skills:** Community Management, Social Media, Communication, Customer Support

---

### 18. Tom Anderson — Technical Writer
**Role:** Documentation Lead  
**Department:** Product  

**Bio:** Writes clear, comprehensive docs that help users master Beetle Studio.

**Responsibilities:**
- User documentation
- API documentation
- Tutorial creation
- Video script writing
- Help center management
- Knowledge base maintenance

**Skills:** Technical Writing, Video Editing, Instructional Design, Content Creation

---

## Business & Operations

### 19. Amanda Clark — Operations Manager
**Role:** Operations Lead  
**Department:** Operations  

**Bio:** Keeps the company running smoothly so engineers can focus on building.

**Responsibilities:**
- HR and recruitment
- Vendor management
- Legal and contracts
- Finance coordination
- Office/administration
- Compliance and contracts

**Skills:** Operations Management, HR, Finance, Legal Review, Vendor Management

---

### 20. Kevin Brown — Business Development
**Role:** Business Development  
**Department:** Business  

**Bio:** Forges partnerships and explores revenue opportunities for Beetle Studio.

**Responsibilities:**
- Partnership development
- OEM/bundling deals
- Enterprise sales
- Plugin marketplace strategy
- Licensing negotiations
- Market expansion

**Skills:** Business Development, Sales, Negotiation, Partnership Management, Market Analysis

---

## Team Structure Overview

```
Mooned Dev (CEO)
├── Kirk Beka (CTO)
│   ├── Engineering
│   │   ├── Alex Chen (UI/UX Lead)
│   │   │   └── Emma Thompson (Timeline Engineer)
│   │   ├── Maya Rodriguez (Backend Lead)
│   │   ├── James Park (Graphics Engineer)
│   │   ├── Sophie Williams (Codec Engineer)
│   │   ├── Daniel Kim (Effects Engineer)
│   │   ├── Ryan Foster (Audio Engineer)
│   │   ├── Lisa Martinez (QA Lead)
│   │   ├── Mike Johnson (DevOps Lead)
│   │   └── Sarah Miller (Build Engineer)
│   ├── Product
│   │   ├── Chris Taylor (Product Manager)
│   │   ├── Nina Patel (UX Designer)
│   │   ├── David Lee (Motion Designer)
│   │   └── Tom Anderson (Technical Writer)
│   ├── Marketing
│   │   ├── Jason Wong (Marketing Lead)
│   │   └── Rachel Green (Community Manager)
│   └── Operations
│       ├── Amanda Clark (Operations)
│       └── Kevin Brown (Business Dev)
```

---

## Hiring Priorities (In Order)

1. **Core Engine Team:** Graphics Engineer, Codec Engineer, Effects Engineer
2. **UI Team:** Senior UI Developer
3. **Backend:** Firebase Developer
4. **QA:** QA Engineers
5. **Marketing:** Community & Marketing
6. **Operations:** As company scales

---

**Last Updated:** June 2025  
**Version:** 1.0

---

## References

### Internal Documents

- [BEETLE_STUDIO_TEAM.md](./BEETLE_STUDIO_TEAM.md) â€” Team roster and roles
- [PROJECT_SCHEDULE.md](./PROJECT_SCHEDULE.md) â€” Project milestones and timeline
- [TEAM_OPERATIONS_MANUAL.md](./TEAM_OPERATIONS_MANUAL.md) â€” Day-to-day team operations

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [docs/STYLE_GUIDE.md](./docs/STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Mooned Dev | Initial structured version per STYLE_GUIDE.md. Added header block, Scope & Audience, Contents TOC, References, and Document Maintenance sections. |

### Review Cadence

- **Next review:** September 2026
- **Reviewer:** Kirk Beka (CTO)
- **Cadence:** Quarterly