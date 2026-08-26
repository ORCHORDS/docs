# phishing-simulation-before-incident

**Issue:** Staff who have never encountered a phishing simulation are easy targets when real phishing attacks arrive
**Date:** 2026-08-11
**Status:** documented

## What happened
A finance team member received a spoofed CEO email requesting an urgent wire transfer. Having never been trained or tested on phishing, they processed the transfer without verification. The company lost $340k. A phishing simulation and awareness training would have cost $2k and half a day.

## The lesson
Run phishing simulations before a real incident tests your team. Make simulations realistic (internal spoofing, not obviously fake domains) and frequent (quarterly). Follow each simulation with immediate, non-punitive training for those who clicked. Track click rates over time as a security metric.

## Why it matters
Phishing is the entry vector in the majority of ransomware and business email compromise incidents. Training that is only done once at onboarding is forgotten. Simulations create muscle memory and measurable improvement.

## How to apply
- [ ] Run quarterly phishing simulations using a tool (GoPhish, KnowBe4) that measures click and report rates.
- [ ] Vary simulation types: credential harvesting, malicious attachment, urgent wire request, IT impersonation.
- [ ] Never punish employees who click — follow up immediately with a short (5-minute) awareness reminder.
- [ ] Report simulation results to leadership quarterly and track trend improvement.
- [ ] Combine simulations with a clear "report phishing" button in the email client to train the correct response (report, don't click).

## Related
- `social-engineering-beats-tech-controls.md`
- `insider-threat-is-real.md`
