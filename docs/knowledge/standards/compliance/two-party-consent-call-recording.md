# two-party-consent-call-recording

**Issue:** Federal wiretap law (18 U.S.C. 2511) allows recording a conversation with one party's consent, but roughly a dozen states — including California, Florida, Illinois, Maryland, Massachusetts, Michigan, Montana, Nevada (effectively), Oregon, Pennsylvania, Washington, Connecticut, and Delaware — require all-party consent, and courts generally apply the stricter state's law when a call crosses state lines. The exposure stopped being theoretical for software teams in 2025: class actions were filed against AI notetaker vendors (Otter.ai in August 2025 in N.D. Cal., later consolidated with parallel suits, plus suits naming competitors like Fireflies.ai and Granola) alleging that meeting bots recorded participants without their consent, framing "the bot joined the call" as a wiretap. Any feature that records, transcribes, stores, or AI-processes calls, meetings, or screen shares needs consent plumbing designed in from the start; bolting on a disclaimer afterwards is what got the notetaker vendors sued.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Consent model basics

1. **Design to the strictest standard.** Determine participant location is unreliable at call time, so the safe architecture is all-party consent everywhere: a pre-recording disclosure plus affirmative consent (banner acceptance, verbal prompt on telephony, or join-flow acknowledgment) from every participant, with the recording state visibly indicated for the whole session.
2. **One-party states are not a free pass for bots.** The deploying user is a party, so one-party consent covers a user recording their own call in most states — but class actions against notetakers argue the bot is a third-party interceptor, and product trust suffers regardless; treat affirmative disclosure as the product floor.
3. **Consent must be captured, not assumed.** Store who consented, when, in what form (click, verbal "yes" recorded, DTMF), and to what version of the disclosure; "we had a beep on the line" defeats some claims but stores no evidence of consent by each participant in multi-party meetings.
4. **Re-consent on scope expansion.** Consent to "record for quality" does not cover AI training, sentiment analysis, or sharing transcripts with third parties; scope changes require a new consent event, and EU participants additionally need a GDPR lawful basis and disclosure, since call content is personal data.

## Engineering controls

1. **Gate recording at the media layer.** Recording and transcription must be impossible to enable server-side until the consent condition for the session is satisfied — enforce in the media pipeline, not just the UI, so a modified client cannot start a silent capture.
2. **Per-participant opt-out that actually works.** If any participant declines or hangs the consent flow, the fallback should be automatic: pause recording, or drop the bot from the meeting; the join flow needs a documented behavior for each outcome rather than blocking the meeting entirely.
3. **Bot identity and visibility.** The AI notetaker should join as a visibly named participant with an obvious avatar, and meeting platforms' built-in "recording in progress" indicators should be treated as complements, not substitutes, for your own consent record — passive indicators were specifically criticized in the 2025 complaints as insufficient notice.
4. **Retention and deletion aligned to consent.** Transcripts, summaries, and audio inherit the consent terms: per-recording deletion endpoints, expiration defaults, and deletion cascades to derived AI outputs (summaries, embeddings, search indexes) — a transcript deleted while its vector embedding survives is a hidden retention bug and a wiretap-adjacent liability.
5. **Telephony announcement requirements.** For phone systems, several states and the federal rules expect a periodic or pre-call beep/notification for recorded calls; modern VoIP stacks should emit a clear pre-call announcement and log its playback event.

## Litigation-driven risk areas

1. **The 2025 notetaker class actions define the threat model.** Claims against Otter.ai and peers allege recording and processing without all-party consent and inadequate disclosure of bot presence; the lesson for builders is that the recording party's knowledge is not attributed to other participants, and cross-state participant mixes bring all-party states into every deployment.
2. **HR and sales calls are the hot zone.** Recorded interviews, disciplinary calls, and outbound sales calls with AI transcription in two-party states require the same consent treatment as inbound support queues; sales teams enabling auto-record without disclosure are the most common corporate violation.
3. **Web tracking "wiretapping" claims rhyme.** Session-replay and third-party analytics pixels that capture user inputs have been pleaded under the same state wiretap statutes; treat input-capturing telemetry on sensitive pages as a sibling risk requiring disclosure and consent management, consistent with the cookie-consent program.
4. **Contract terms do not waive statute claims for consumers.** A terms-of-service clause saying "calls may be recorded" helps with disclosed business calls but does not cure unconsented recording of the other party in an all-party state; the recording feature itself must implement the consent gate.

## Policy plumbing

1. **Keep a recording disclosure register.** Version every disclosure string, where it is shown (IVR, app, email footer, meeting invite template), and who approved it; wiretap class actions turn on what the other party was told, and the register is your evidence.
2. **Jurisdiction table with a conservative default.** Maintain the list of all-party states for product and support documentation, but do not build per-state behavior toggles on participant geolocation guesses — the default must be the strictest path because participant location is usually unknowable mid-call.
3. **Vendor notetakers in your meetings are your exposure too.** If employees admit AI notetakers to internal meetings with external participants, your company is in the enforcement chain; make bot-admission policy part of the meeting-platform configuration and educate staff on the corporate default.
