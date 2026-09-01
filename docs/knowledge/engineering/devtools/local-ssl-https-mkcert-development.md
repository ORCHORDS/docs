# Local HTTPS Development with mkcert

Browsers treat `http://localhost` and `https://localhost` as different origins, and a growing set of web platform features — service workers, HTTP/2, secure-context-only APIs, cookies with `Secure` attributes — behave differently or refuse to work over plain HTTP. Developing against real TLS locally means either disabling verification (training bad habits, breaking some APIs outright) or generating certificates that browsers reject. mkcert solves this properly: it creates a local certificate authority, adds it to the system (and browser) trust stores, and issues certificates from that CA for your development hostnames. This article covers how mkcert works, correct usage for multi-developer and CI contexts, and the security boundaries that keep a convenience tool from becoming a liability.

## Scope

This article addresses mkcert for local HTTPS: the local-CA model, installation, certificate issuance for localhost and custom dev domains, trust-store mechanics across platforms, sharing setups across a team, revocation and cleanup, and what mkcert deliberately does not do (public certificates, production use). It does not cover public CA issuance (ACME/Let's Encrypt), mTLS design, or reverse-proxy configuration beyond the dev-server context.

## Workflow or implementation guidance

mkcert's model: a certificate is trusted by a browser if the browser trusts the chain to a root CA. Public sites buy/obtain this from public CAs; mkcert makes *you* a (local-only) CA. `mkcert -install` generates a root key pair, then inserts the root certificate into the system trust store (macOS Keychain, Windows cert store, Linux varies by distro) and, for Firefox, into the NSS database (Firefox keeps its own store on some platforms). Thereafter `mkcert localhost 127.0.0.1 ::1 dev.example.test` issues leaf certificates that every browser on that machine trusts — real TLS, real padlock, real `Secure` cookie behavior, no verification warnings.

Standard workflow:

1. **Install once per developer machine:** `mkcert -install` (the root CA lands in trust stores; keep the root key where mkcert puts it — `$(mkcert -CAROOT)`).
2. **Issue per-project certificates:** run `mkcert localhost 127.0.0.1 ::1 myapp.test` in the project; it writes `myapp.test+3.pem` (cert) and `myapp.test+3-key.pem` (key). Point the dev server at them (`vite --https cert=... key=...`, webpack-dev-server options, or a local proxy). SANs matter: modern clients ignore CN and validate Subject Alternative Names, so include every hostname/IP the app will be visited by, including `127.0.0.1` and `::1` or the LAN IP when testing from a phone.
3. **Custom dev domains:** for multi-service setups, use reserved-for-testing domains (`*.test` is RFC 2606 reserved; `.localhost` also works with implicit loopback semantics in many resolvers) mapped in `/etc/hosts` or a local resolver, then issue one certificate covering the wildcard-adjacent list (`mkcert app.test api.test admin.test`). Wildcards (`*.test`) work with mkcert but over-broad local wildcards encourage lazy scoping; enumerate the few hostnames you actually run.
4. **CI and ephemeral environments:** mkcert's CA-in-trust-store model is wrong for shared CI machines (a trusted root on a shared box is an attack surface). Instead, CI runs the server with a self-signed cert and configures the *test client* (Playwright/`NODE_TLS_REJECT_UNAUTHORIZED=0` never in production code, but properly: pass the CA to the client, or use browser launch args `--ignore-certificate-errors-spki-list` with the cert's SPKI hash) so verification is scoped to exactly that cert, not globally disabled.
5. **Team sharing:** do *not* commit the mkcert root key or share one team CA (`mkcert -CAROOT` copied around); each developer generates their own CA. Shared setups turn one laptop's compromise into everyone's TLS interception primitive. What *is* shareable: the scripts — a `make certs` target that runs mkcert with the project's canonical hostname list, so every developer's certs cover the same names.
6. **Cleanup and rotation:** `mkcert -uninstall` removes the root from trust stores; delete the CAROOT directory to destroy the CA entirely. Rotate the same way (uninstall, remove, reinstall) if a root ever leaks or periodically per policy.

Boundaries to keep crisp: mkcert certificates carry a CA marked for local use (key usage and name constraints are basic — the tool's own docs are explicit that it is not for production, not for public hostnames reachable by others, and the root CA must never leave the machine). A leaf from your local CA presented to a visitor's browser fails validation (their machine doesn't trust your CA) — which is the system working. Treat the root key with the care of any CA private key: if exfiltrated, an attacker can MITM the *developer's* browsing for any site by issuing certs for real domains — the reason team-shared roots are forbidden and why the CAROOT must never be committed, synced to cloud drives with broad sharing, or baked into images.

A worked example: a team develops a Progressive Web App with service workers and `Secure` cookies; plain-HTTP localhost hides cookie and SW behavior differences that break staging. Each developer runs `mkcert -install` once; a repo script issues `app.test` certs for the enumerated dev hostnames; the dev server serves real TLS; service workers register, Secure cookies attach, HTTP/2 multiplexing behaves like production. CI runs the same server with its own throwaway cert and a test client pinned to that cert's SPKI — same behavior guarantees, no shared CA anywhere.

## Controls

- Per-developer local CAs only; a repo hygiene check rejects any file under the mkcert CAROOT naming pattern (`rootCA.pem`/`rootCA-key.pem`) or obvious leaf+key pairs from commits (a pre-commit scan for `BEGIN RSA PRIVATE KEY`/`BEGIN PRIVATE KEY` plus `.pem` pairs catches accidents).
- Canonical hostname list lives in one script (`scripts/dev-certs.sh`) invoked by a documented make target; PRs adding dev hostnames update the list so everyone's certs stay complete.
- CI uses scoped trust (client trusts exactly the ephemeral cert), never global TLS-verification disables; a lint on CI config rejects `NODE_TLS_REJECT_UNAUTHORIZED` and `--ignore-certificate-errors` (the unscoped variant).
- Document uninstall/rotation (`mkcert -uninstall`, delete CAROOT) in the same onboarding page that documents install, so offboarding includes CA removal on returned machines.
- Certificates include all loopback forms (`localhost`, `127.0.0.1`, `::1`) plus LAN IP when mobile testing is expected; a quick `openssl s_client` sanity check in the onboarding script proves the chain resolves to the local root.

## Validation evidence

- mkcert's local-CA model, `-install`/`-uninstall` trust-store behavior (system store and Firefox NSS), SAN-based certificate issuance with IPs and multiple hostnames, the CAROOT location, and the explicit production-unsuitability guidance are documented in the official mkcert README at GitHub (FiloSottile/mkcert).
- Browser certificate validation against Subject Alternative Names and trust chains follows the TLS/HTTP platform behavior specified by RFC 5280 (certificate profile) and enforced by browsers; RFC 2606 reserves `.test` and `.example` for documentation/testing use, which is why dev domains should draw from them.
- A reproducible check: after `mkcert -install` and issuing certs for `localhost`, `curl -v https://localhost:8443` (against a TLS dev server) completes without `-k`; rerun from a machine without the CA installed (or after `-uninstall`) and the same curl fails verification — demonstrating both the convenience and the machine-local boundary in one experiment.

## Failure modes and correction

- **Committed or shared root CA.** Symptom: a repo or drive contains `rootCA-key.pem`. Correct immediately: rotate (uninstall, delete CAROOT, reinstall) and review access history; treat as a credential leak.
- **Global TLS-verification disables in CI.** Symptom: `rejectUnauthorized: false` sprinkled in test code masking real chain problems. Correct by client-scoped trust of the ephemeral cert.
- **Missing SANs for real access paths.** Symptom: phone on LAN gets NET::ERR_CERT_COMMON_NAME_INVALID. Correct by including LAN IP/hostname at issuance (SAN, not CN).
- **Stale certs after hostname list grows.** Symptom: new `admin.test` fails on old certs. Correct by regenerating via the canonical script rather than ad hoc `mkcert` invocations.
- **Firefox mismatch on Linux setups.** Symptom: system store trusted, Firefox still warns (separate NSS DB). Correct by rerunning `mkcert -install` with Firefox present or importing the root into NSS explicitly.

## Limitations

- Local-only by design: no public trust, no ACME automation, no wildcard public names — production needs a real CA.
- The root CA is a powerful local credential; environments with strict endpoint policy (some enterprises forbid user-installed roots) may block `-install`, requiring policy exceptions or alternative local-HTTPS strategies.
- Certificates carry validity windows; long-lived checkouts occasionally hit expiry and need reissuance via the same script.
- mkcert does not manage revocation infrastructure (no production CRL/OCSP semantics); revocation is delete-and-retrust.

## Canonical sources

- mkcert project (FiloSottile), README — local CA creation, trust stores, SAN issuance, limitations: https://github.com/FiloSottile/mkcert
- IETF, RFC 5280: Internet X.509 Public Key Infrastructure Certificate and CRL Profile (SAN and chain validation semantics): https://www.rfc-editor.org/rfc/rfc5280
