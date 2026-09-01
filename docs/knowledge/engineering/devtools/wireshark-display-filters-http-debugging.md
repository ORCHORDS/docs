# Wireshark Display Filters for HTTP Debugging

Wireshark's capture filters decide what gets recorded; display filters decide what you see — and for HTTP debugging, display filters are the skill. A trace of a flaky web session can hold tens of thousands of frames; the debugging loop is forming precise questions ("show me only the 5xx responses and what requests produced them") and expressing them in Wireshark's display-filter language. This article covers the filter grammar, the HTTP-layer fields worth knowing, the patterns that answer common questions, and the workflow discipline that turns packet traces into evidence.

## Scope

This article addresses Wireshark display filters for HTTP/1.1 and HTTP/2 debugging: filter syntax (protocol fields, comparison operators, slices, membership, functions), HTTP-layer field names, conversation/context filtering, TLS interception context, and export/reporting workflow. It does not cover capture-filter (BPF) syntax beyond noting the distinction, TCP-level performance analysis in depth, or Wireshark's Lua scripting.

## Workflow or implementation guidance

Display filters use protocol.field names with C-like operators: `==`, `!=`, `>`, `<`, `contains`, `matches` (regex, case-sensitive by default), `in {…}` set membership, and boolean combination with `and`/`or`/`not`. Filters apply to the loaded capture without re-capturing, which is why the debugging pattern is: capture broadly (or at least on the right interface with a sane capture filter), then narrow repeatedly with display filters.

The fields that do the HTTP work:

- `http.request.method`, `http.request.uri`, `http.host` — request identity.
- `http.response.code` — status; ranges filter with `>= 500 && <= 599` or `in {500..599}` syntax variants (`http.response.code >= 500` is the robust form).
- `http.response_for.uri` (and `http.request_in`) — the response-to-request linkage: the killer feature for HTTP debugging, tying each response to the URI that produced it.
- `http.content_length`, `http.content_type` — body metadata.
- `http2.type`, `http2.flags`, `http2.headers.status` — HTTP/2 framing (streams, not sequential request/response pairs).
- `tcp.stream` — the TCP conversation index; filtering one stream isolates a whole connection.
- `http.time` — Wireshark's computed request-to-response latency.

Filter patterns for recurring questions:

1. **Only errors:** `http.response.code >= 500` — the first filter of every "the site is flaky" triage. Widen to `http.response.code >= 400` for client errors.
2. **Errors with their requests:** `http.response.code >= 500` shows frames; then use "Right-click → Follow → HTTP Stream" on a hit, or filter the conversation (`tcp.stream eq N`) to see the full exchange including the request. For a list view, `http.response.code >= 500` in a custom column layout with `http.response_for.uri` as a column gives "error ↔ URI" in one screen.
3. **One endpoint's traffic:** `http.request.uri contains "/api/checkout"` for requests; add responses via `http.response_for.uri contains "/api/checkout"` ORed in.
4. **Latency outliers:** `http.time > 1` shows exchanges slower than a second; sort the `http.time` column to rank them.
5. **One host:** `http.host == "api.example.com"` (exact) or `http.host contains "example"` (substring).
6. **A whole connection:** click a frame of interest, note `tcp.stream`, then `tcp.stream eq 42` — all frames of that conversation, every layer.
7. **HTTP/2 status:** `http2.headers.status >= 500` — remember HTTP/2 frames responses differently; the classic mistake is filtering `http.response.code` (HTTP/1.1 dissector fields) against an HTTP/2 trace and concluding "no responses".
8. **Redirection chains:** `http.response.code == 301 || http.response.code == 302` then following streams reveals redirect loops that browsers summarize away.

TLS context: most production HTTP is over TLS, and Wireshark sees ciphertext unless keys are available. Two legitimate debugging paths: (a) point the client at an explicit debugging proxy (mitmproxy-style) instead of decrypting in Wireshark; (b) export TLS session keys from the client (browsers/`SSLKEYLOGFILE`) and configure Wireshark's TLS protocol preferences to read the keylog — after which the HTTP dissectors see plaintext and everything in this article applies. Capture-side, `tls.handshake.type == 1` still shows ClientHellos (SNI visible), so `tls.handshake.extensions_server_name contains "example"` narrows to a host's connections even when encrypted.

Workflow discipline that makes traces evidence rather than vibes:

- **Filter incrementally, never destructively.** Apply display filters; do not delete unseen packets. Export filtered views ("File → Export Specified Packets → Displayed") for sharing; keep the full capture for re-analysis when the first hypothesis fails.
- **Save the filter with the finding.** Wireshark lets you name filters; when a triage filter proves out (`http.response.code >= 500 && http.host == "api.example.com"`), save it in the profile. Team-shared profiles carry institutional debugging knowledge.
- **Columns tell the story.** Configure columns: `http.request.method`, `http.request.uri` (or `http2.headers.path`), `http.response.code`, `http.time`, `http.host`. Most HTTP debugging is reading a table, not opening frames.
- **Time references for causality.** Toggle a time reference (`Ctrl+T`) at the user-visible failure moment; relative times after it localize related frames.
- **Export for reports.** "Statistics → HTTP → Packet Counter" and "Load Distribution" summarize by host; filtered CSV export (frame number, time, fields of interest) feeds tickets and postmortems with precise numbers instead of "it seemed slow".

A worked example: intermittent checkout failures reported by users. Capture on the load balancer during an incident window: 200k frames. `http.response.code >= 500` yields 14 frames across 3 conversations; the custom columns immediately show all 14 are `/api/checkout/payment` with code 502. `tcp.stream eq 7` on one shows the request sent, upstream connection reset mid-body (`tcp.flags.reset == 1` visible in the same stream), retry at +2.1s succeeding. The finding "upstream resets on payment calls under load, retries mask it at 2s cost" is written from the trace in ten minutes — with frame numbers as citations.

## Controls

- Capture with a stated scope (interface, host, capture-filter) and record it with the artifact; an undocumented capture is unauditable.
- Handle traces as sensitive data: they can contain credentials, tokens, PII in headers and bodies; store in access-controlled locations and purge per retention policy; decrypt only with key material handled under the same secrecy rules as the payloads themselves.
- Maintain a team Wireshark profile (columns, saved display filters for the service's endpoints and error classes) versioned alongside runbooks; new engineers inherit debugging capability, not just the tool.
- Prefer frame-number citations in incident reports (`frame 18341: 502 on /api/checkout`) so any reviewer with the capture can jump to the evidence.
- When TLS keylogging is used for debugging, the keylog file is credential-grade material: ephemeral, deleted after analysis, never committed or attached to tickets.

## Validation evidence

- Display-filter syntax (field names, operators, `contains`/`matches`, membership, slices), dissector field names (HTTP/1.1 and HTTP/2 fields), `tcp.stream` conversation semantics, "Follow Stream", statistics exports, and TLS preference configuration (including SSLKEYLOGFILE support) are documented in the official Wireshark User's Guide and the display-filter reference published at wireshark.org.
- The response-for-request linkage (`http.response_for`, `http.request_in`) is documented in the HTTP dissector field reference — the mechanism behind error-to-URI correlation.
- A reproducible exercise: capture a scripted session that includes a forced 500 (a local test endpoint), then confirm the triage chain — `http.response.code >= 500` finds it, columns show the URI, `tcp.stream` isolation shows the full exchange, and `http.time` quantifies the exchange — the entire loop validated against known ground truth.

## Failure modes and correction

- **HTTP/1.1 fields against HTTP/2 traffic.** Symptom: "no responses" in a trace full of them. Correct by using `http2.*` fields.
- **Display filter confused with capture filter.** Symptom: BPF syntax rejected (or worse, capturing nothing useful). Correct by keeping the languages straight: BPF at capture, display-filter language after.
- **Case-sensitive regex surprises.** Symptom: `matches "ERROR"` misses `error`. Correct with `matches "(?i)error"` where supported or `contains` where adequate.
- **Over-narrow first filter.** Symptom: empty view, wrong conclusion ("nothing happened"). Correct by widening to the conversation (`tcp.stream`) before concluding absence.
- **Trace leakage.** Symptom: captures with bearer tokens land in shared drives or tickets. Correct by treating traces as credentials, with purge automation and access-controlled storage.

## Limitations

- Encrypted traffic limits analysis to metadata (SNI, timing, sizes) unless key material is legitimately available.
- HTTP/3 (QUIC over UDP) dissector maturity and field coverage differ from TCP HTTP; filters and habits do not transfer wholesale.
- Huge captures strain the GUI; command-line dissection (tshark with the same display-filter syntax) scales better for automation.
- Wireshark shows what crossed the wire; application-internal causes need correlated logs, which the frame citations are designed to align with.

## Canonical sources

- Wireshark Foundation, Wireshark User's Guide (display filters, following streams, statistics): https://www.wireshark.org/docs/wsug_html/
- Wireshark Foundation, Display Filter Reference (HTTP and HTTP/2 field definitions): https://www.wireshark.org/docs/dfref/
