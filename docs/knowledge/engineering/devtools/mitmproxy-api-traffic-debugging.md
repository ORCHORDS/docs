# mitmproxy-api-traffic-debugging

**Issue:** When an integration breaks between a frontend, a mobile app, and a backend API, the bug usually lives in the exact bytes on the wire: a header that is silently dropped, a token that expires mid-session, a redirect that strips a query parameter, or a certificate handshake that only fails on a real device. Browser devtools only show what the browser sees, and server logs only show what the server parsed after the damage is done. A scriptable man-in-the-middle proxy closes this gap by capturing, inspecting, rewriting, and replaying traffic from any client, including emulators, CLI tools, and IoT SDKs, which makes it a core devtool skill for anyone debugging distributed systems.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing a capture mode

1. **Regular proxy mode.** The default `mitmproxy` and `mitmweb` commands start an explicit HTTP proxy on port 8080. Point the client at it with environment variables or OS proxy settings. This is the right mode for curl, Node, Python, and browsers, and it is the least surprising option when you control the client.
2. **Transparent proxy mode.** Use `--mode transparent` when the client cannot be configured to use a proxy, for example an Android emulator or a device on a test network routed through your machine. Traffic is intercepted with iptables or a hotspot instead of client settings.
3. **Reverse proxy mode.** Run `--mode reverse:https://api.example.com` to pose as a single upstream origin. This is ideal for debugging one API without touching anything else, and for pointing a staging-locked mobile build at a local backend by changing only the host it dials.
4. **Local capture mode.** On Linux, `--mode local` intercepts traffic from the local machine without any proxy configuration, which is convenient for capturing what a build tool or CLI secretly phones home to do.
5. **Web UI when pairing.** `mitmweb` renders flows in a browser tab and is far easier to walk teammates through than the TUI during a shared debugging session. Keep `mitmproxy` for keyboard-driven solo work.

## TLS trust and certificate pain

1. **Install the generated CA.** mitmproxy writes its certificate authority to the `~/.mitmproxy` directory on first run. Every client that should see decrypted HTTPS must trust that CA, otherwise you get cryptic TLS handshake failures that look like the API being down.
2. **Respect Android 7+ restrictions.** Modern Android ignores user-installed CAs for app traffic by default. Use an emulator with a writable system image and push the cert to the system store, or add a debug network security config to the app under test. Budget time for this; it is the single most common reason mobile capture fails.
3. **Trust the CA for CLI tools.** Export the cert with `mitmproxy` and point clients at it through env vars like `NODE_EXTRA_CA_CERTS` for Node, `REQUESTS_CA_BUNDLE` for Python, or `SSL_CERT_FILE` for generic OpenSSL-based tools. This avoids the temptation to disable verification globally.
4. **Detect certificate pinning early.** If traffic still fails after trusting the CA, the app pins certificates. Options are a Frida unpinning script, a debug build with pinning disabled, or capturing the unpinned traffic on a different layer such as the backend logs.
5. **Prefer an emulator loopback alias.** Android emulators reach the host proxy at `10.0.2.2`, not `localhost`. Hardcoding this wrong address wastes an entire debugging session on connection refused errors.

## Scripting with addons

1. **Think in events, not loops.** Addons are Python classes that hook events such as `request`, `response`, `load`, and `error`. Official guidance is to react to hooks rather than poll, because the event model keeps scripts composable with mitmproxy's own internals, much of which are addons themselves.
2. **Configure through options.** Use `ctx.options` and `load` to read settings rather than hardcoding values or wiring argparse into a script. Options integrate with `--set` on the command line, so a script becomes configurable without new CLI code.
3. **Avoid recursive network calls.** An addon that makes its own HTTP request through the proxy will intercept its own traffic and can loop forever or corrupt the capture. Mark internal requests, skip them in the hook, or make the call outside the proxy.
4. **Start from the official examples.** The examples in the mitmproxy docs cover reading saved dumps, modifying form submissions, and adding custom commands. Study them before writing a bespoke addon, because they encode the maintainers' intended patterns.
5. **Log into the flow, not stdout.** Use `ctx.log.info` and friends so your diagnostics appear inside the proxy UI next to the flow they concern, with timestamps and colors, instead of interleaving with unrelated terminal output.

## Filtering and replay

1. **Narrow the firehose with limit expressions.** `--set flow_detail` plus intercept filters such as `~u api.example.com` or `~t json` keep the view readable. A capture without filters produces a dump nobody will actually read.
2. **Save flows as fixtures.** Save interesting exchanges with the save command and commit them as test fixtures. A saved flow can be replayed later in client-replay mode to reproduce a bug against a fixed backend, which turns a one-time capture into a regression test.
3. **Use map-local for offline work.** Map a URL prefix to a local file so the app behaves as if the backend responded. This lets you develop against realistic payload shapes without a working server or network access.
4. **Set breakpoints for surgical edits.** Intercept a request or response, edit headers or bodies by hand, and continue. This is the fastest way to answer "what happens if the server returns 429 here" without touching backend code.
5. **Export the truth.** Export flows as curl commands or HAR when reporting bugs, so the receiver can reproduce the exact request including headers and cookies instead of guessing from a screenshot.

## Team safety practices

1. **Redact before sharing captures.** Flow dumps contain live tokens, cookies, and personal data. Scrub authorization headers with an addon or a post-processing step before attaching a capture to a ticket.
2. **Keep capture configs in the repo.** A short addon plus a documented launch command, stored next to the service it debugs, means any teammate can reproduce the interception instead of rebuilding it from memory.
3. **Never point production clients at a proxy.** Intercepting real user traffic is both an ethical and legal hazard. Restrict interception to emulators, test accounts, and staging environments, and make that boundary explicit in the documented setup.
4. **Re-check the certificate story after OS updates.** OS and browser updates periodically change CA handling rules. Verify the trust setup still works after upgrading the emulator image or the host OS rather than discovering it mid-incident.
