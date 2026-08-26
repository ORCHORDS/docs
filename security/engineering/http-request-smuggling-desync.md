# http-request-smuggling-desync

**Issue:** A reverse proxy or CDN sits in front of the application and reuses a single back-end connection for many users' requests. HTTP/1.1 has two conflicting ways to state where a message ends (`Content-Length` and `Transfer-Encoding: chunked`), and HTTP/2-to-HTTP/1.1 downgrades reintroduce that ambiguity. An attacker sends one request that the front end and back end parse differently; the leftover bytes get prepended to the next user's request on the shared connection. The result is request smuggling: bypassing front-end access controls, capturing other users' requests (including session tokens), poisoning caches, and hijacking other users' responses — often rated critical because it crosses user boundaries without touching application code.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the desync happens

1. **CL.TE variant.** The front end honors `Content-Length`, the back end honors `Transfer-Encoding: chunked`. A body of `0\r\n\r\nSMUGGLED` with `Content-Length` covering it means the back end stops at the zero-length chunk and treats `SMUGGLED` as the start of the next victim's request.
2. **TE.CL variant.** The front end honors chunked encoding, the back end honors `Content-Length`. A truncated `Content-Length` makes the back end stop mid-body, and the remainder of the attacker's chunked body is interpreted as a fresh request.
3. **TE.TE variant.** Both servers support chunked encoding, but one is tricked into ignoring it via obfuscation: `Transfer-Encoding: xchunked`, odd spacing or tabs, duplicated headers, or line-break tricks. The attack then reduces to CL.TE or TE.CL.
4. **H2.CL and H2.TE.** When the front end accepts HTTP/2 but downgrades to HTTP/1.1 for the back end, injecting a `Content-Length` or `Transfer-Encoding` header into the HTTP/2 request (where length framing is binary and unambiguous) makes the two layers disagree about message boundaries after translation.
5. **CRLF injection via pseudo-headers.** Newlines injected into HTTP/2 pseudo-headers such as `:path` split one request into two on the downgraded side. Because browsers and Burp default to HTTP/2 when offered, testers must manually switch protocols in Burp Repeater to reproduce this class.
6. **CL.0 and browser-powered desync.** Some front ends treat a request as body-less (`Content-Length: 0` semantics) while the back end reads a body, or the victim's own browser connection is desynchronized (pause-based desync), enabling client-side cache poisoning even on sites the attacker cannot reach directly.

## Impact to assume in a threat model

1. **Security-control bypass.** The smuggled prefix is not inspected by the front end's WAF, IP allowlist, or client-TLS authentication, so internal endpoints become reachable as if the front end did not exist.
2. **Capture of other users' requests.** A smuggled request whose body swallows the next user's request bytes (e.g., a POST to a reflected endpoint) can exfiltrate the victim's headers, session cookies, and credentials to attacker-controlled storage.
3. **Response queue poisoning.** Desynchronizing the response ordering means the attacker receives the response meant for the next user — full account takeover material when that response carries a one-time token or personal data.
4. **Request tunnelling.** Smuggled requests can leak internal rewriting headers added by the front end (internal auth headers, real client IP), or pivot toward internal infrastructure the proxy fronts.
5. **Force multiplier for other bugs.** Smuggling converts reflected input into XSS that fires without victim interaction, turns root-relative redirects into open redirects, and enables both web cache poisoning and web cache deception.

## Detection and testing

1. **Differential timing.** Send an ambiguous request followed by a normal one; if the second response hangs or the connection stalls, the back end is waiting for bytes the front end already consumed — the classic CL.TE/TE.CL tell.
2. **Differential responses.** Compare the response to a crafted second request versus a normal second request; a changed status or error page confirms the smuggled prefix altered parsing.
3. **Protocol downgrades in the lab.** Test the site over both HTTP/1.1 and HTTP/2 explicitly, and verify whether the edge rewrites/normalizes headers before forwarding — the two paths often behave differently.
4. **Automated scanning with skepticism.** Burp Scanner finds many desyncs, but confirm by hand: false positives are common with keep-alive reuse, and a "detected" issue must be reproducible against the real front-end/back-end pairing.

## Defenses that actually close it

1. **Run HTTP/2 end to end and disable downgrading.** HTTP/2 has a single, binary, unambiguous length mechanism, so end-to-end HTTP/2 removes the root cause entirely; this is the strongest available fix.
2. **Validate rewritten requests before forwarding.** If downgrading is unavoidable, the front end must validate the translated HTTP/1.1 request: reject newlines in header values, colons in header names, and spaces in the request method.
3. **Normalize at the front, reject at the back.** The front end should normalize ambiguous requests (strip conflicting `Transfer-Encoding`, settle on one framing) and the back end should reject any remaining ambiguity and close the TCP connection rather than guess.
4. **Never assume a request lacks a body.** Frameworks and proxies that treat methods like GET or HEAD as inherently body-less are the root cause of CL.0 and client-side desync; parse framing from headers, not from method conventions.
5. **Discard desynchronized connections.** On any server-level parsing exception, drop the connection instead of reusing it, so leftover bytes cannot poison the next user.
6. **Reduce blast radius.** Disabling back-end connection reuse limits classic smuggling (but not request tunnelling); confining front-end-added trust headers to specific routes limits what a smuggled request can reach.

## Sources

1. **PortSwigger Web Security Academy — Request smuggling.** https://portswigger.net/web-security/request-smuggling (variants, H2 techniques, response queue poisoning, prevention).
2. **OWASP community pages on HTTP request smuggling.** https://owasp.org/www-community/attacks/ (search "request smuggling" for the community entry).
