# calendar-invite-ics-email

**Issue:** Product emails frequently need to put an event on the recipient's calendar — bookings, webinars, renewal reminders, scheduled flows. The standard mechanism is an iCalendar (RFC 5545) object carried in email per the iMIP profile (RFC 6047), but the details are unforgiving: the MIME part must be text/calendar with a method parameter matching the METHOD line inside the ICS body; updates and cancellations are keyed by UID and SEQUENCE rather than by sending "a new invite"; line endings must be CRLF with folded long lines; and clients (Gmail, Outlook, Apple Mail) each render the Accept/Decline/Tentative UI only when the structure is exactly right. A malformed invite shows up as a nameless .ics file or silently updates the wrong event, and the same auto-add behavior Gmail offers is actively abused for ICS phishing — so builders must also understand the abuse surface they are operating on.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## MIME structure for iMIP delivery

1. **Use a dedicated text/calendar part with matching method.** The MIME part is Content-Type: text/calendar; method=REQUEST; charset=UTF-8 and the ICS body must open with METHOD:REQUEST. A mismatch between the part parameter and the body line (or an application/ics attachment) renders as a plain downloadable file in Outlook instead of native buttons.
2. **Attach as both rendered part and application/ics.** The widely used pattern is a multipart/alternative containing text/plain (or text/html) plus the text/calendar part, and a separate application/ics attachment with Content-Disposition: attachment; filename="invite.ics". Gmail consumes the text/calendar part; Outlook desktop historically keys on the file attachment; the pair covers both.
3. **Never inline the ICS in an HTML body.** The calendar object is a first-class MIME part, not markup. UTF-8 charset declaration on the part is mandatory whenever summaries or locations contain non-ASCII text.
4. **Let the library fold lines.** ICS lines are limited to 75 octets with CRLF continuation folds; hand-built strings with raw long URLs or descriptions produce objects that strict parsers reject silently.

## ICS object requirements

1. **UID is the event's permanent identity.** Generate a globally unique id (e.g., event-uuid@yourdomain) at creation and reuse it for every subsequent update; a new UID creates a second calendar entry rather than updating the first.
2. **Bump SEQUENCE and DTSTAMP on every change.** Rescheduling requires incrementing SEQUENCE (a counter starting at 0) and refreshing DTSTAMP; clients treat equal-or-lower SEQUENCE as stale and ignore it. DTSTAMP must change monotonically or updates are dropped.
3. **Include the organizer and attendee with RSVP.** ORGANIZER;CN=...:mailto: and ATTENDEE;RSVP=TRUE:mailto: lines make the invite actionable and let REPLY traffic flow if you accept responses.
4. **Use UTC or explicit timezones.** Prefer UTC DTSTART/DTEND (suffix Z) for machine-generated events, or embed a VTIMEZONE block when the wall-clock timezone matters to humans. Floating times (no zone) get interpreted in each reader's local zone and drift.
5. **Provide VALARM only deliberately.** Reminder blocks are honored inconsistently and can be stripped by some clients; put the "we'll remind you" promise in your own notification flow instead of relying on client alarms.

## Update and cancellation flows

1. **Updates resend METHOD:REQUEST with the same UID.** Changed time, location, or description: reissue the request with SEQUENCE+1 and an updated DTSTAMP. Do not send a new UID — that duplicates the event on attendee calendars.
2. **Cancellations are METHOD:CANCEL with STATUS:CANCELLED.** Send the same UID, SEQUENCE+1, and the cancelled status so clients strike the event and notify the user. For events an attendee merely declines, that is a REPLY from their side, not a CANCEL from yours.
3. **Track event state server-side.** Store UID, current SEQUENCE, and the last DTSTAMP you emitted per (event, recipient); regenerating invites from templates without this state is the root cause of "my calendar shows three copies of the webinar" support tickets.
4. **Respect the 48-hour update reality.** Attendees' clients only poll and reconcile when they check mail; last-minute time changes should be paired with a plain notification email or SMS, not the ICS alone.

## Client compatibility and security

1. **Test the big four before shipping.** Gmail (web), Outlook (desktop and web), and Apple Mail each have quirks: Gmail renders the part and can auto-add events, Outlook desktop is the pickiest about METHOD matching, Apple Mail surfaces the .ics attachment with a tap-to-add sheet. Verify with real inboxes — see email-testing-local-catchall.md for the capture side.
2. **Gmail auto-add is a phishing vector — design your invites to be verifiable.** Attackers send METHOD:REQUEST invites that land directly on victim calendars with phishing links in location/description. Keep your descriptions short and link to your domain, and if you build an inbound pipeline, treat unsolicited ICS from outside parties with the same skepticism as links (see the Sublime Security write-ups on ICS phishing surges for detection ideas).
3. **Authenticate the surrounding email.** The invite inherits the deliverability of the message carrying it: SPF/DKIM/DMARC alignment on the sending domain, per email-authentication fundamentals, determines whether the ICS is ever seen at all.
4. **Do not hide critical info inside the ICS.** Some clients preview only the summary line; the confirmation email body should carry the full context (time in the recipient's timezone, join link, cancellation policy) so the calendar entry is a convenience layer, not the sole source of truth.
